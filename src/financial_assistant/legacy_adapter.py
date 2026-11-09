"""Explicit v0.1 -> v0.2 migration. Never edits legacy input or calculates a metric."""
from copy import deepcopy

from .catalog import validate_catalog
from .contracts import validate_bundle
from .contracts_v2 import VERSION, boundary, digest, need, validate_outcome
from .tasks import validate_task


def _period(old):
    return {**deepcopy(old), "duration_type": "full_year" if old["start"][5:] == "01-01"
            and old["end"][5:] == "12-31" and old["start"][:4] == old["end"][:4] else "custom"}


@boundary
def catalog_from_v01(bundle):
    need(type(bundle) is dict and bundle.get("schema_version") == "0.1", "unsupported_schema_version")
    validate_bundle(bundle)
    old = bundle["document"]
    publication = old["publication"]
    pub = {"precision": publication["precision"], "value": publication["value"],
           "timezone": publication["timezone"], "binding": publication["version_binding"],
           "record_id": None if publication["precision"] == "unknown" else old["document_id"] + ":publication",
           "source_url": publication["source_url"],
           "version_id": old["version_id"] if publication["version_binding"] == "document_version" else None,
           "document_sha256": old["sha256"] if publication["version_binding"] == "document_version" else None}
    metrics = {}
    for f in bundle["facts"]:
        metrics[f["metric_id"]] = {"metric_id": f["metric_id"], "definition_id": f["metric_id"] + ":legacy-row-v1",
                                   "label": f["original_label"], "period_kinds": ["duration"]}
    doc = {"document_id": old["document_id"], "organization_id": old["entity_id"],
           **{k: deepcopy(old[k]) for k in ("accounting_standard", "document_type", "version_id", "sha256", "byte_length", "pdf_pages", "document_url", "fetched_at", "rights", "audit", "related_release")},
           "report_period": _period(old["report_period"]), "source_url": old["source_page_url"],
           "approved_on": old["approval_date"], "signed_on": None, "publication": pub,
           "availability": {"local_resource_id": old["document_id"], "file_status": "not_checked", "extraction_status": "not_run"},
           "preparation_status": "checked" if old["review"]["status"] in {"assistant_checked", "human_reviewed"} else "candidates",
           "provenance": deepcopy(old["review"]), "data_origin": "real"}
    evidence = []
    for ev in bundle["evidence"]:
        metric_ids = {f["metric_id"] for f in bundle["facts"] if f["evidence_id"] == ev["evidence_id"]}
        need(len(metric_ids) == 1, "ambiguous_legacy_evidence_metric")
        metric_id = next(iter(metric_ids))
        evidence.append({"evidence_id": ev["evidence_id"], **{k: deepcopy(ev[k]) for k in ("document_id", "version_id", "document_sha256", "currency", "scale", "raw_value", "numeric_encoding")},
            "locator": {"kind": "pdf", **{k: ev[k] for k in ("pdf_page", "printed_page", "statement_page", "page_region", "table_title", "row_label", "column_label", "unit_header")}},
            "metric_id": metric_id,
            "definition_id": metrics[metric_id]["definition_id"],
            "period": _period(ev["period"]), "provenance": deepcopy(ev["review"])})
    by_id = {e["evidence_id"]: e for e in evidence}
    facts = [{**{k: deepcopy(f[k]) for k in ("fact_id", "evidence_id", "version_id", "metric_id", "value", "original_label", "currency", "scale")},
              "organization_id": f["entity_id"], "document_id": old["document_id"],
              "definition_id": metrics[f["metric_id"]]["definition_id"], "period": _period(f["period"]),
              "evidence_digest": digest(by_id[f["evidence_id"]]), "provenance": deepcopy(f["review"]),
              "origin_role": "reported_period" if f["period"] == old["report_period"] else "comparative_period"} for f in bundle["facts"]]
    result = {"schema_version": VERSION, "catalog_id": old["document_id"] + ":catalog-v02",
              "organizations": [{"organization_id": old["entity_id"], "name": old["entity_name"],
                                 "aliases": [old["entity_id"]], "consolidation": old["consolidation"],
                                 "accounting_standards": [old["accounting_standard"]]}],
              "metrics": list(metrics.values()), "documents": [doc], "evidence": evidence, "facts": facts}
    validate_catalog(result)
    return result


@boundary
def task_from_v01(bundle):
    catalog = catalog_from_v01(bundle)
    req = bundle["request"]
    units = {(f["currency"], f["scale"]) for f in bundle["facts"] if f["metric_id"] == req["metric_id"]}
    need(len(units) == 1, "incompatible_units")
    currency, scale = next(iter(units))
    task = {"schema_version": VERSION, "task_id": req["request_id"], "original_question": req["question"],
            "operation_id": req["formula_id"], "organization_id": req["entity_id"], "consolidation": req["consolidation"],
            "accounting_standard": req["accounting_standard"], "metric_id": req["metric_id"],
            "definition_id": req["metric_id"] + ":legacy-row-v1", "periods": [_period(req[k]) for k in ("previous_period", "current_period")],
            "documents": [{k: catalog["documents"][0][k] for k in ("document_id", "version_id")}],
            "version_policy": "explicit_versions", "result_unit": {"currency": currency, "scale": scale},
            "mode": "snapshot" if req["mode"] == "document_snapshot" else "historical", "as_of": req["as_of"]}
    validate_task(task)
    return task


@boundary
def outcome_from_legacy(value, *, run_id, task_id):
    """Adapt a validated legacy user response or agent envelope, retaining failure class."""
    need(type(value) is dict, "invalid_legacy_outcome")
    agent = "agent_schema_version" in value
    if agent:
        need(value["agent_schema_version"] == "0.1", "unsupported_schema_version")
    view = value["user_response"] if agent else value
    status = value["status"] if agent else ("completed" if view["status"] in {"answered", "missing", "conflict", "unsupported"} else view["status"])
    if status == "preflight_refusal":
        status = "completed"
    reason = value["reason_code"] if agent else view["reason_code"]
    result = {"schema_version": VERSION, "run_id": run_id, "task_id": task_id,
              "execution_status": status, "financial_status": None, "reason_code": reason,
              "clarification_fields": [], "financial_result": None}
    if status == "completed":
        result.update(financial_status=view["status"], reason_code=view["reason_code"],
                      financial_result=deepcopy(view.get("financial_result")) if view["status"] == "answered" else None)
    elif status == "clarification":
        # Old views have prose but no normalized field list. Do not invent fields.
        need(False, "legacy_clarification_fields_required")
    elif status == "error":
        result["reason_code"] = {"source_missing": "source_missing", "registry_missing": "registry_invalid",
            "registry_invalid": "registry_invalid", "model_unavailable": "model_unavailable",
            "save_failed": "save_failed"}.get(reason, "protocol_error")
    validate_outcome(result)
    return result
