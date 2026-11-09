"""Versioned financial tool over the existing reference implementation.

No new formula or extraction: numbers come exclusively from the supplied,
validated manual Fact registry. Retrieval only locates that existing evidence.
"""
from copy import deepcopy

from .contracts import ContractError, answer, require, shape, text, validate_answer, validate_bundle


def tool_request(previous_fact_id, current_fact_id, operation_id="annual_growth_v1",
                 mode="document_snapshot", as_of=None):
    return {"operation_id": operation_id, "previous_fact_id": previous_fact_id,
            "current_fact_id": current_fact_id, "mode": mode, "as_of": as_of}


def _refuse(result, status, reason, message):
    result.update(status=status, reason_code=reason, message=message, answer=None,
                  inputs=[], sources=[])
    return result


def calculate_metric(bundle, request):
    validate_bundle(bundle)
    shape(request, "operation_id previous_fact_id current_fact_id mode as_of")
    for field in ("operation_id", "previous_fact_id", "current_fact_id", "mode"):
        text(request[field])
    require(request["previous_fact_id"] != request["current_fact_id"], "Two distinct fact IDs are required")
    facts = {f["fact_id"]: f for f in bundle["facts"]}
    ids = [request["previous_fact_id"], request["current_fact_id"]]
    require(all(x in facts for x in ids), "Unknown fact ID; this is a tool input error")
    working = deepcopy(bundle)
    working["request"].update(formula_id=request["operation_id"], mode=request["mode"], as_of=request["as_of"])
    # Keep the complete registry: conflicting facts must not disappear when
    # a caller supplies a convenient pair of IDs.
    canonical = answer(working)
    validate_answer(canonical, working)
    result = {"financial_tool_schema_version": "0.1", "request": deepcopy(request),
              "status": canonical["status"], "reason_code": canonical["reason_code"],
              "message": canonical["message"], "basis": "preverified_manual_fact_registry",
              "document_id": bundle["document"]["document_id"],
              "entity_name": bundle["document"]["entity_name"],
              "accounting_standard": bundle["document"]["accounting_standard"],
              "metric_id": bundle["request"]["metric_id"],
              "requested_periods": {"previous": deepcopy(bundle["request"]["previous_period"]),
                                    "current": deepcopy(bundle["request"]["current_period"])},
              "answer": canonical, "inputs": [], "sources": [],
              "warnings": list(canonical["warnings"]), "retrieval_resolution": None}
    if canonical["status"] != "answered":
        return result
    for field, fact_id in zip(("previous_period", "current_period"), ids):
        fact = facts[fact_id]
        if fact["period"] != working["request"][field] or fact["metric_id"] != working["request"]["metric_id"]:
            return _refuse(result, "conflict", "input_fact_context_mismatch",
                           "ID фактов не соответствуют показателю и порядку периодов запроса.")
    if canonical["fact_ids"] != ids:
        return _refuse(result, "conflict", "input_fact_selection_mismatch",
                       "Калькулятор выбрал другой набор фактов; автоматическая подмена ID запрещена.")
    evidence = {ev["evidence_id"]: ev for ev in bundle["evidence"]}
    for fact_id in ids:
        f = facts[fact_id]
        result["inputs"].append(deepcopy(f))
        ev = evidence[f["evidence_id"]]
        # Minimal locator, not the source page or full retrieved text.
        result["sources"].append({k: deepcopy(ev[k]) for k in (
            "evidence_id", "document_id", "version_id", "document_sha256", "pdf_page",
            "printed_page", "statement_page", "page_region", "table_title", "row_label",
            "column_label", "period", "currency", "scale", "unit_header", "raw_value", "review")})
        result["sources"][-1]["url"] = bundle["document"]["document_url"] + f"#page={ev['pdf_page']}"
    return result


def calculate_from_retrieval(bundle, request, retrieval):
    result = calculate_metric(bundle, request)
    # Preserve the calculator's financial/temporal refusal. Nothing retrieved
    # can make an unavailable or incompatible fact eligible.
    if result["status"] != "answered":
        return result
    require(isinstance(retrieval, dict) and retrieval.get("retrieval_schema_version") == "0.1",
            "Unsupported retrieval envelope")
    require(retrieval.get("status") in {"found", "not_found", "missing"}, "Invalid retrieval status")
    require(isinstance(retrieval.get("results"), list), "Retrieval results must be a list")
    if retrieval["status"] != "found":
        require(not retrieval["results"], "A retrieval refusal cannot contain hits")
        return _refuse(result, "missing", "retrieval_context_missing",
                       "Поиск не предоставил контекст для обоих ранее проверенных фактов.")
    doc = bundle["document"]
    evs = {e["evidence_id"]: e for e in bundle["evidence"]}
    needed = {f["evidence_id"] for f in result["inputs"]}
    covered, seen, trace = set(), {}, []
    for rank, hit in enumerate(retrieval["results"], 1):
        require(isinstance(hit, dict), "Malformed retrieval hit")
        for field, expected in (("document_id", doc["document_id"]), ("entity_id", doc["entity_id"]),
                                ("version_id", doc["version_id"]), ("document_sha256", doc["sha256"])):
            require(hit.get(field) == expected, "Retrieval hit document/entity/version/hash mismatch: " + field)
        require(type(hit.get("pdf_page")) is int and 1 <= hit["pdf_page"] <= doc["pdf_pages"], "Invalid hit page")
        require(hit.get("page_region") in {"left_half_of_spread", "right_half_of_spread"}, "Invalid hit region")
        require(hit.get("verification_status") == "candidate", "Retrieval must not upgrade verification status")
        fid = f"{doc['sha256']}:{hit['pdf_page']}:{hit['page_region']}"
        require(hit.get("fragment_id") == fid, "Fragment ID does not match its locator")
        require(hit.get("source_url") == doc["document_url"] + f"#page={hit['pdf_page']}", "Hit source URL mismatch")
        refs = hit.get("existing_manual_evidence_ids")
        require(isinstance(refs, list) and all(isinstance(x, str) for x in refs), "Malformed evidence references")
        if fid in seen:
            if seen[fid] != hit:
                return _refuse(result, "conflict", "retrieval_duplicate_conflict", "Противоречивые копии поискового фрагмента.")
            continue
        seen[fid] = hit
        matched = []
        for ref in set(refs):
            require(ref in evs, "Unknown manual evidence ID in retrieval")
            ev = evs[ref]
            for key in ("document_id", "version_id", "document_sha256", "pdf_page", "page_region", "printed_page"):
                require(hit.get(key) == ev[key], "Retrieval/evidence locator mismatch: " + key)
            if ref in needed:
                covered.add(ref)
                matched.append(ref)
        if matched:
            trace.append({"rank": rank, "fragment_id": fid, "evidence_ids": sorted(matched)})
    if covered != needed:
        return _refuse(result, "missing", "verified_evidence_not_retrieved",
                       "В выдаче нет ссылок на оба нужных доказательства из проверенного реестра.")
    result["retrieval_resolution"] = {"method": "match_existing_manual_evidence_locators",
                                      "used_hits": trace, "extraction_mode": retrieval.get("extraction_mode"),
                                      "new_facts_created": False}
    result["warnings"].append("retrieval_only_locates_prior_verified_facts")
    return result


def validate_financial_result(result, bundle, request, retrieval=None):
    """Bind all fields to an external request, not just IDs inside the result."""
    expected = calculate_metric(bundle, request) if retrieval is None else calculate_from_retrieval(bundle, request, retrieval)
    require(result == expected, "Financial tool result differs from validated inputs and deterministic output")
