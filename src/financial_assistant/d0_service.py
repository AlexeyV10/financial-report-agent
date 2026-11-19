"""Five fixed D0 operations delegated to the unchanged service B and prepared search."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from tempfile import TemporaryDirectory
from threading import Lock
from uuid import uuid4

from . import retrieval_v2, service_b
from .application_paths import ApplicationPaths, WorkspaceContext, WorkspacePathError
from .application_paths import _directory, _inspect, _require_disjoint, _root
from .contracts_v2 import ContractError
from .fact_admission import CalculationContext
from .service_contracts import validate_answer
from .vault_storage import VaultStore, VaultStorageError


SCHEMA = "win10-d0-1"
SOURCE_ID = "d0-own-v1"
VERSION_ID = "d0-own-v1-report"
SOURCE_SHA256 = "ebabc9e49fbde3063f63f98393a271734bc16d0686ea035938ccd8d90db2caf0"
MAX_FRAME_BYTES = 65536
MAX_QUESTION_BYTES = 4096
OPERATIONS = {"direct": "direct_fact_v1", "delta": "absolute_change_v1", "relative": "relative_change_v1",
              "scale": "scale_v1", "margin": "operating_margin_v1"}

_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_ASSETS = "app/assets/d0/"
_HEADERS = ["OWN D0 FICTIONAL GROUP", "IFRS / consolidated nonfinancial group",
            "Full years: 01 Jan - 31 Dec 2025 / 2024", "Currency and scale: RUB million"]
_CELLS = {"d0-revenue-2024": [331, 143, 388, 165], "d0-revenue-2025": [246, 143, 303, 165],
          "d0-operating-profit-2025": [246, 116, 303, 138]}
_B_BOUNDARY = Lock()


class D0ServiceError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def valid_run_id(value):
    return type(value) is str and _RUN_ID.fullmatch(value) is not None


def reply(status, operation, run_id, reason, *, trace=None, display=None, source_sha256=None, source_page=None):
    code = reason if type(reason) is str and _CODE.fullmatch(reason) else "d0_failed"
    return {"schema": SCHEMA, "status": status, "operation": operation, "run_id": run_id,
            "display": display, "reason": code, "trace": trace if trace is not None else [],
            "source_sha256": source_sha256, "source_page": source_page}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("nonfinite number")


def _read_bytes(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise D0ServiceError("artifact_too_large")
    return raw


@dataclass(frozen=True)
class _Fixture:
    manifest: dict
    catalog: dict
    dictionary: dict
    admission: dict
    config: dict
    lexicon: dict
    guards: dict


def _fixture(paths):
    values, guards = [], {}
    for name in ("manifest", "catalog", "dictionary", "admission", "retrieval_config", "search_lexicon"):
        path = paths.asset(_ASSETS + name + ".json")
        raw = _read_bytes(path, 1024 * 1024)
        values.append(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite))
        guards[str(path)] = _sha(raw)
    fixture = _Fixture(*values, guards)
    doc, = fixture.catalog["documents"]
    if (fixture.manifest != {"schema": "win10-own-fixture-1", "resource_id": SOURCE_ID, "sha256": SOURCE_SHA256,
                             "bytes": 1445, "page": 1, "cells": _CELLS, "headers": _HEADERS}
            or doc["document_id"] != SOURCE_ID or doc["version_id"] != VERSION_ID
            or doc["availability"]["local_resource_id"] != SOURCE_ID or doc["sha256"] != SOURCE_SHA256
            or doc["byte_length"] != fixture.manifest["bytes"] or doc["pdf_pages"] != 1
            or doc["data_origin"] != "synthetic" or doc["accounting_standard"] != "IFRS"
            or doc["publication"]["precision"] != "unknown"
            or fixture.admission["data_origin"] != "synthetic"):
        raise D0ServiceError("invalid_own_fixture")
    return fixture


def _source_text(data, fixture):
    if len(data) != fixture.manifest["bytes"] or _sha(data) != SOURCE_SHA256:
        raise D0ServiceError("source_hash_mismatch")
    expected = {"d0-revenue-2024": ("revenue", 2024, "comparative_period"),
                "d0-revenue-2025": ("revenue", 2025, "reported_period"),
                "d0-operating-profit-2025": ("operating_profit", 2025, "reported_period")}
    facts = {fact["fact_id"]: fact for fact in fixture.catalog["facts"]}
    if facts.keys() != expected.keys() or len(facts) != len(fixture.catalog["facts"]):
        raise D0ServiceError("invalid_own_fixture")
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(data) as pdf:
        if len(pdf) != 1:
            raise D0ServiceError("source_pages")
        page = pdf[0]
        try:
            text = page.get_textpage()
            try:
                page_text = text.get_text_bounded()
                if not all(header in page_text for header in _HEADERS):
                    raise D0ServiceError("source_header")
                for fact_id, (metric, year, role) in expected.items():
                    fact = facts[fact_id]
                    period = {"kind": "duration", "duration_type": "full_year",
                              "start": f"{year}-01-01", "end": f"{year}-12-31"}
                    if (fact["metric_id"] != metric or fact["period"] != period or fact["origin_role"] != role
                            or fact["currency"] != "RUB" or fact["scale"] != 1000000
                            or text.get_text_bounded(*_CELLS[fact_id]).strip() != fact["value"]):
                        raise D0ServiceError("source_cell")
            finally:
                text.close()
        finally:
            page.close()
    return page_text


def _source_input(fixture, operation, run_id, historical, question):
    if question is not None:
        if (type(question) is not str or not 0 < len(question.strip()) <= 4000
                or "\0" in question or len(question.encode("utf-8")) > MAX_QUESTION_BYTES):
            raise D0ServiceError("invalid_question")
        return {"kind": "text", "input_id": run_id, "question": question}
    doc, = fixture.catalog["documents"]
    facts = {fact["fact_id"]: fact for fact in fixture.catalog["facts"]}
    previous, current = facts["d0-revenue-2024"]["period"], facts["d0-revenue-2025"]["period"]
    fields = {"organization": doc["organization_id"], "consolidation": "group", "accounting_standard": "IFRS",
              "operation_id": OPERATIONS[operation],
              "metric_ids": ["operating_profit", "revenue"] if operation == "margin" else ["revenue"],
              "periods": [previous, current] if operation in {"delta", "relative"} else [current],
              "documents": [{"document_id": SOURCE_ID, "version_id": VERSION_ID}],
              "version_policy": "explicit_versions", "mode": "historical" if historical else "snapshot"}
    if operation == "scale":
        fields["result_unit"] = {"kind": "amount", "currency": "RUB", "scale": 1000000000}
    if historical:
        fields["as_of"] = "2038-01-01T23:59:59+03:00"
    return {"kind": "form", "form": {"schema_version": "kp3-form-0.1", "input_id": run_id,
                                      "original_question": "Явная собственная учебная форма.",
                                      "fields": fields, "assumptions": []}}


def _scratch(workspace, run_id):
    vault = str(workspace.vault_root).casefold()
    parent = _root(workspace.paths.cache_root / "win10-jobs", create_later=True)
    parent.mkdir(parents=True, exist_ok=True)
    _directory(parent)
    key = json.dumps([vault, run_id.lower()], ensure_ascii=True, separators=(",", ":")).encode("ascii")
    job = parent / _sha(key)
    old_parent = parent / _sha(vault.encode("utf-8"))
    if _inspect(old_parent) is not None and _inspect(old_parent / _sha(run_id.lower().encode("ascii"))) is not None:
        raise D0ServiceError("duplicate_run")
    try:
        job.mkdir()
    except FileExistsError:
        raise D0ServiceError("duplicate_run") from None
    return _directory(job)


def _windows_path_limit(error):
    # Workspace checks may replace the raw OS error with a safe code.
    return any(getattr(exc, "winerror", None) == 206 for exc in (error, error.__context__))


@contextmanager
def _prepared_boundary(index, job_root):
    """Confine legacy path guards to one checked scratch index in the one-request worker."""
    def private_index(candidate):
        path = Path(candidate)
        if not path.is_absolute() or path != index:
            raise retrieval_v2.RetrievalError("private_path_required")
        _directory(index.parent)
        for artifact in (index, index.with_name(index.name + ".manifest.json")):
            info = _inspect(artifact)
            if info is not None and not stat.S_ISREG(info.st_mode):
                raise retrieval_v2.RetrievalError("private_path_required")
        return index

    with _B_BOUNDARY:
        previous_path, previous_root = retrieval_v2.private_path, service_b.ROOT
        retrieval_v2.private_path, service_b.ROOT = private_index, job_root
        try:
            yield
        finally:
            retrieval_v2.private_path, service_b.ROOT = previous_path, previous_root


def _execute_b(workspace, request, run_id, fixture, data):
    root = _scratch(workspace, run_id)
    scratch = root / "tmp"
    scratch.mkdir()
    staged_pdf = scratch / "report.pdf"
    with staged_pdf.open("xb") as stream:
        stream.write(data)
    resources = {SOURCE_ID: str(staged_pdf)}
    index = scratch / "prepared.sqlite"
    gate = {"db_path": index, "config": fixture.config, "lexicon": fixture.lexicon, "export_paths": None}
    context = CalculationContext(fixture.catalog, fixture.dictionary, fixture.admission,
                                 resources=resources, file_guards=fixture.guards)
    with _prepared_boundary(index, root):
        retrieval_v2.build_index(index, context.catalog, resources, fixture.config, fixture.lexicon, "prepared")
        legacy = service_b.ServiceContext(context, gate, scratch / "runs")
        answer = service_b.execute(request, "B", legacy, run_id=run_id)
        validate_answer(answer)
    saved = scratch / "runs" / (_sha(run_id.encode("utf-8")) + ".json")
    try:
        info = saved.lstat()
    except FileNotFoundError:
        raise D0ServiceError("trace_not_saved") from None
    if not stat.S_ISREG(info.st_mode) or json.loads(_read_bytes(saved, 2 * 1024 * 1024)) != answer:
        raise D0ServiceError("trace_not_saved")
    return answer


def run_d0(workspace: WorkspaceContext, run_id: str, operation: str, *, historical=False, question=None) -> dict:
    from .document_viewer import DocumentViewerError
    from .d0_viewer import record_d0_source

    if type(operation) is not str or operation not in OPERATIONS:
        return reply("error", None, None, "invalid_operation")
    if not valid_run_id(run_id):
        return reply("error", operation, None, "invalid_run_id")
    if type(historical) is not bool or (historical and question is not None):
        return reply("error", operation, run_id, "invalid_arguments")
    trace = []
    try:
        try:
            workspace.read_receipt(run_id)
        except WorkspacePathError as error:
            if error.code != "receipt_missing":
                raise
        else:
            raise D0ServiceError("duplicate_run")

        fixture = _fixture(workspace.paths)
        source = _source_input(fixture, operation, run_id, historical, question)
        pdf = workspace.resolve_resource(SOURCE_ID)
        data = _read_bytes(pdf, fixture.manifest["bytes"])
        _source_text(data, fixture)
        with VaultStore(workspace) as store:
            matches = [version for version in store.list_versions(SOURCE_ID) if version["sha256"] == SOURCE_SHA256]
            if len(matches) != 1 or store.read_original(SOURCE_SHA256) != data:
                raise D0ServiceError("source_binding_mismatch")
        answer = _execute_b(workspace, source, run_id, fixture, data)
        trace = [item["stage"] for item in answer["trace"] if item["status"] != "skipped"]
        execution, reason = answer["execution_status"], answer["reason_code"]
        if execution in {"error", "limit"}:
            return reply("error", operation, run_id, reason, trace=trace)
        if execution == "awaiting_clarification":
            return reply("clarify", operation, run_id, reason, trace=trace)
        if answer["financial_status"] != "answered":
            return reply("blocked", operation, run_id, reason, trace=trace)
        result = answer["financial_result"]
        if result["operation_id"] != OPERATIONS[operation]:
            return reply("blocked", operation, run_id, "operation_mismatch", trace=trace)
        locator = record_d0_source(workspace, answer, OPERATIONS[operation])
        return reply("answered", operation, run_id, "ok", trace=trace, display=result["display_value"],
                     source_sha256=locator["source_sha256"], source_page=locator["source_page"])
    except (D0ServiceError, WorkspacePathError, VaultStorageError, DocumentViewerError,
            ContractError, retrieval_v2.RetrievalError) as error:
        reason = "workspace_path_too_long" if _windows_path_limit(error) else error.code
        return reply("error", operation, run_id, reason, trace=trace)
    except OSError as error:
        reason = "workspace_path_too_long" if _windows_path_limit(error) else "d0_failed"
        return reply("error", operation, run_id, reason, trace=trace)
    except Exception:
        return reply("error", operation, run_id, "d0_failed", trace=trace)


def provision_d0(paths: ApplicationPaths, target_path: Path) -> None:
    """Publish a fully initialized new vault only inside this app's own workspace parent."""
    container = _root(paths.app_data_root.parent, create_later=True)
    target = _root(target_path, create_later=True)
    expected_parent = container / "workspaces"
    if os.name != "nt" or target.parent != expected_parent:
        raise D0ServiceError("invalid_provision_target")
    _require_disjoint(target, paths.install_root)
    _require_disjoint(target, paths.app_data_root)
    if _inspect(target) is not None:
        raise D0ServiceError("vault_already_exists")
    fixture = _fixture(paths)
    data = _read_bytes(paths.asset(_ASSETS + "report.pdf"), fixture.manifest["bytes"])
    text = _source_text(data, fixture)
    _directory(container.parent)
    container.mkdir(exist_ok=True)
    parent = _root(expected_parent, create_later=True)
    parent.mkdir(exist_ok=True)
    _directory(parent)
    with TemporaryDirectory(prefix="win10-own-", dir=parent) as temporary:
        staging = _directory(Path(temporary))
        draft = staging / "draft"
        draft.mkdir()
        with (draft / "report.pdf").open("xb") as stream:
            stream.write(data)
        marker = {"schema": "workspace-context-1", "workspace_id": "win10-" + uuid4().hex,
                  "resources": [{"id": SOURCE_ID, "path": "report.pdf", "bytes": len(data), "sha256": SOURCE_SHA256}]}
        with (draft / "workspace.json").open("x", encoding="utf-8") as stream:
            json.dump(marker, stream, ensure_ascii=True)
        workspace = WorkspaceContext.open(paths, draft)
        with VaultStore(workspace, create=True) as store:
            store.import_revision(SOURCE_ID, data, expected_sha256=SOURCE_SHA256, text=text, extractor="pdfium-d0-v1")
        _directory(parent)
        try:
            draft.rename(target)
        except FileExistsError:
            raise D0ServiceError("vault_already_exists") from None
