"""Describe and bind a task to inventory IDs. This module performs no calculation."""
from copy import deepcopy

from .catalog import available_from, validate_catalog
from .contracts_v2 import (CHECKED, VERSION, ClarificationRequired, boundary,
    digest, identifier, instant, need, period, period_end, shape, text, unit)

OPERATIONS = {"direct_fact_v1": 1, "absolute_change_v1": 2, "annual_growth_v1": 2}
FIELDS = "schema_version task_id original_question operation_id organization_id consolidation accounting_standard metric_id definition_id periods documents version_policy result_unit mode as_of"


@boundary
def validate_task(task):
    need(type(task) is dict, "invalid_task")
    need(not (set(task) - set(FIELDS.split())), "fields_mismatch")
    need(task.get("schema_version") == VERSION, "unsupported_schema_version")
    for key in ("task_id", "original_question"):
        need(key in task, "fields_mismatch")
        identifier(task[key]) if key == "task_id" else text(task[key])
    missing = [key for key in FIELDS.split() if key not in {"schema_version", "task_id", "original_question", "as_of"}
               and (key not in task or task[key] is None or task[key] == "" or task[key] == [])]
    if missing:
        raise ClarificationRequired("missing_fields", missing)
    shape(task, FIELDS)
    for key in ("operation_id", "organization_id", "metric_id", "definition_id"):
        identifier(task[key])
    need(task["operation_id"] in OPERATIONS, "unsupported_operation")
    need(task["consolidation"] in {"group", "legal_entity"}, "invalid_consolidation")
    need(task["accounting_standard"] in {"IFRS", "RAS"}, "invalid_standard")
    need(type(task["periods"]) is list and len(task["periods"]) == OPERATIONS[task["operation_id"]], "wrong_period_count")
    for p in task["periods"]:
        period(p)
    if len(task["periods"]) == 2:
        previous, current = task["periods"]
        need(previous["kind"] == current["kind"] == "duration"
             and previous["duration_type"] == current["duration_type"], "incompatible_periods")
        need(previous["duration_type"] != "custom", "incompatible_periods")
        need(period_end(previous) < period_end(current) and previous["end"] < current["start"], "reversed_or_overlapping_periods")
        if previous["duration_type"] in {"full_year", "year_to_date"}:
            need(previous["start"][5:] == current["start"][5:] and previous["end"][5:] == current["end"][5:], "incompatible_periods")
        if task["operation_id"] == "annual_growth_v1":
            need(previous["duration_type"] == "full_year"
                 and int(current["start"][:4]) == int(previous["start"][:4]) + 1, "incompatible_periods")
    need(type(task["documents"]) is list and bool(task["documents"]), "documents_required")
    seen = set()
    for doc in task["documents"]:
        shape(doc, "document_id version_id")
        identifier(doc["document_id"]); identifier(doc["version_id"])
        need(doc["document_id"] not in seen, "duplicate_document_selection")
        seen.add(doc["document_id"])
    need(task["version_policy"] in {"explicit_versions", "original_period_documents"}, "invalid_version_policy")
    unit(task["result_unit"])
    need(task["mode"] in {"snapshot", "historical"}, "invalid_analysis_mode")
    if task["mode"] == "historical":
        if task["as_of"] is None:
            raise ClarificationRequired("missing_fields", ["as_of"])
        instant(task["as_of"])
    else:
        need(task["as_of"] is None, "as_of_requires_historical")


@boundary
def bind_task(catalog, task):
    """Fail closed; ready means selected inputs, never an answered financial task."""
    validate_catalog(catalog); validate_task(task)
    orgs = {o["organization_id"]: o for o in catalog["organizations"]}
    metrics = {m["metric_id"]: m for m in catalog["metrics"]}
    docs = {d["document_id"]: d for d in catalog["documents"]}
    org = orgs.get(task["organization_id"])
    need(org is not None, "unknown_organization_id")
    metric = metrics.get(task["metric_id"])
    need(metric is not None, "unknown_metric_id")
    need(task["definition_id"] == metric["definition_id"], "unknown_metric_definition")
    chosen = []
    for ref in task["documents"]:
        doc = docs.get(ref["document_id"])
        need(doc is not None, "unknown_document_id")
        need(doc["version_id"] == ref["version_id"], "document_version_mismatch")
        chosen.append(doc)
    result = {"schema_version": VERSION, "task_id": task["task_id"], "binding_status": "ready",
              "reason_code": "ok", "fact_ids": [], "candidate_fact_ids": [],
              "calculations_performed": False, "catalog_digest": digest(catalog)}
    def stop(status, code):
        result.update(binding_status=status, reason_code=code, fact_ids=[])
        return result
    if org["consolidation"] != task["consolidation"] or task["accounting_standard"] not in org["accounting_standards"]:
        return stop("conflict", "entity_or_standard_mismatch")
    if any(doc["organization_id"] != task["organization_id"] or
           doc["accounting_standard"] != task["accounting_standard"] for doc in chosen):
        return stop("conflict", "entity_or_standard_mismatch")
    if any(p["kind"] not in metric["period_kinds"] for p in task["periods"]):
        return stop("conflict", "metric_period_mismatch")
    if task["mode"] == "historical":
        stamps = [available_from(doc) for doc in chosen]
        if any(stamp is None for stamp in stamps):
            return stop("missing", "publication_unknown")
        if any(instant(task["as_of"]) < stamp for stamp in stamps):
            return stop("missing", "not_yet_available")
    if any(doc["preparation_status"] == "conflict" for doc in chosen):
        return stop("conflict", "document_conflict")
    if any(doc["preparation_status"] not in {"checked", "ready"} or doc["provenance"]["status"] not in CHECKED for doc in chosen):
        return stop("missing", "document_unchecked")
    evidence = {e["evidence_id"]: e for e in catalog["evidence"]}
    chosen_ids = {d["document_id"] for d in chosen}
    selected = []
    for p in task["periods"]:
        candidates = [f for f in catalog["facts"] if f["document_id"] in chosen_ids
                      and f["metric_id"] == task["metric_id"] and f["definition_id"] == task["definition_id"] and f["period"] == p]
        if task["version_policy"] == "original_period_documents":
            candidates = [f for f in candidates if f["origin_role"] == "reported_period"
                          and (docs[f["document_id"]]["report_period"] == p or
                               (p["kind"] == "instant" and period_end(p) == period_end(docs[f["document_id"]]["report_period"])))]
        result["candidate_fact_ids"].extend(f["fact_id"] for f in candidates)
        if len(candidates) > 1:
            return stop("conflict", "duplicate_candidates")
        if not candidates:
            return stop("missing", "original_version_missing" if task["version_policy"] == "original_period_documents" else "value_missing")
        f = candidates[0]
        if f["value"] is None:
            return stop("missing", "value_missing")
        if f["provenance"]["status"] not in CHECKED or f["evidence_id"] is None or evidence[f["evidence_id"]]["provenance"]["status"] not in CHECKED:
            return stop("missing", "unverified_candidate")
        if {k: f[k] for k in ("currency", "scale")} != task["result_unit"]:
            return stop("conflict", "incompatible_units")
        selected.append(f["fact_id"])
    result["fact_ids"] = selected
    return deepcopy(result)
