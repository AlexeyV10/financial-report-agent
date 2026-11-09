"""Versioned runtime inventory, independent of a question or evaluation gold."""
from datetime import datetime, time, timedelta, timezone
from copy import deepcopy
import unicodedata

from .contracts_v2 import (CHECKED, VERSION, STANDARDS, ClarificationRequired,
    ContractError, boundary, day, digest, https, identifier, instant, need, number,
    period, period_end, provenance, sha, shape, text, unit)


def normalized(value):
    text(value)
    return " ".join(unicodedata.normalize("NFKC", value).casefold().replace("ё", "е").split())


def _indexed(rows, key):
    need(type(rows) is list, "expected_list")
    result = {}
    for row in rows:
        need(type(row) is dict and key in row, "missing_id")
        identifier(row[key])
        need(row[key] not in result, "duplicate_id")
        result[row[key]] = row
    return result


def _publication(pub, doc):
    shape(pub, "precision value timezone binding record_id source_url version_id document_sha256")
    need(pub["precision"] in {"unknown", "date", "timestamp"} and pub["binding"] in {"unproven", "document_version"}, "invalid_publication")
    need(pub["timezone"] in {"Europe/Moscow", "UTC"}, "unsupported_publication_timezone")
    if pub["precision"] == "unknown":
        need(pub["binding"] == "unproven" and all(pub[k] is None for k in
             ("value", "record_id", "source_url", "version_id", "document_sha256")), "invented_publication")
    else:
        (day if pub["precision"] == "date" else instant)(pub["value"])
        identifier(pub["record_id"])
        if doc["data_origin"] == "real":
            https(pub["source_url"])
        elif pub["source_url"] is not None:
            https(pub["source_url"])
        if pub["binding"] == "document_version":
            need(doc["sha256"] is not None and pub["version_id"] == doc["version_id"]
                 and pub["document_sha256"] == doc["sha256"], "publication_version_mismatch")
        else:
            need(pub["version_id"] is None and pub["document_sha256"] is None, "unproven_binding")


@boundary
def available_from(doc):
    """Bound publication only. A date becomes available next midnight in its zone."""
    _publication(doc["publication"], doc)
    pub = doc["publication"]
    if pub["precision"] == "unknown" or pub["binding"] != "document_version":
        return None
    if pub["precision"] == "timestamp":
        return instant(pub["value"])
    zone = timezone.utc if pub["timezone"] == "UTC" else timezone(timedelta(hours=3))
    return datetime.combine(day(pub["value"]) + timedelta(days=1), time(), zone)


@boundary
def validate_catalog(catalog):
    shape(catalog, "schema_version catalog_id organizations metrics documents evidence facts")
    need(catalog["schema_version"] == VERSION, "unsupported_schema_version")
    identifier(catalog["catalog_id"])
    orgs = _indexed(catalog["organizations"], "organization_id")
    metrics = _indexed(catalog["metrics"], "metric_id")
    docs = _indexed(catalog["documents"], "document_id")
    evidence = _indexed(catalog["evidence"], "evidence_id")
    facts = _indexed(catalog["facts"], "fact_id")
    for org in orgs.values():
        shape(org, "organization_id name aliases consolidation accounting_standards")
        text(org["name"])
        need(org["consolidation"] in {"group", "legal_entity"}, "invalid_consolidation")
        need(type(org["aliases"]) is list and bool(org["aliases"]), "aliases_required")
        names = [normalized(x) for x in org["aliases"]]
        need(len(names) == len(set(names)), "duplicate_alias")
        standards = org["accounting_standards"]
        need(type(standards) is list and standards and len(set(standards)) == len(standards)
             and set(standards) <= STANDARDS, "invalid_standard")
    for metric in metrics.values():
        shape(metric, "metric_id definition_id label period_kinds")
        identifier(metric["definition_id"]); text(metric["label"])
        need(type(metric["period_kinds"]) is list and bool(metric["period_kinds"])
             and len(metric["period_kinds"]) == len(set(metric["period_kinds"]))
             and set(metric["period_kinds"]) <= {"duration", "instant"}, "invalid_metric_period_kind")
    for doc in docs.values():
        shape(doc, "document_id organization_id accounting_standard document_type report_period version_id sha256 byte_length pdf_pages source_url document_url fetched_at signed_on approved_on publication availability preparation_status provenance rights audit data_origin related_release")
        org = orgs.get(doc["organization_id"])
        need(org is not None, "unknown_organization_id")
        need(doc["accounting_standard"] in org["accounting_standards"], "document_standard_mismatch")
        identifier(doc["version_id"]); identifier(doc["document_type"])
        period(doc["report_period"])
        need(doc["data_origin"] in {"real", "synthetic"}, "invalid_data_origin")
        for key in ("sha256", "byte_length", "pdf_pages"):
            if doc[key] is not None:
                sha(doc[key]) if key == "sha256" else need(type(doc[key]) is int and doc[key] > 0, "invalid_document_size")
        if doc["version_id"].startswith("sha256:"):
            need(doc["version_id"] == "sha256:" + (doc["sha256"] or ""), "hash_version_mismatch")
        for key in ("source_url", "document_url"):
            if doc[key] is not None:
                https(doc[key])
        if doc["fetched_at"] is not None:
            instant(doc["fetched_at"])
        for key in ("signed_on", "approved_on"):
            if doc[key] is not None:
                day(doc[key])
        shape(doc["availability"], "local_resource_id file_status extraction_status")
        if doc["availability"]["local_resource_id"] is not None:
            identifier(doc["availability"]["local_resource_id"])
        need(doc["availability"]["file_status"] in {"not_checked", "missing", "available", "hash_mismatch"}, "invalid_file_status")
        need(doc["availability"]["extraction_status"] in {"not_run", "extracted", "unsupported_layout", "error"}, "invalid_extraction_status")
        need(doc["preparation_status"] in {"registered", "candidates", "checked", "ready", "conflict"}, "invalid_preparation_status")
        provenance(doc["provenance"])
        if doc["preparation_status"] in {"checked", "ready"}:
            need(doc["provenance"]["status"] in CHECKED and doc["sha256"] is not None, "document_not_checked")
        if doc["data_origin"] == "real" and doc["preparation_status"] == "ready":
            need(all(doc[k] is not None for k in ("sha256", "byte_length", "pdf_pages", "document_url", "source_url")), "incomplete_document_metadata")
        _publication(doc["publication"], doc)
        shape(doc["rights"], "status public_copy_allowed note checked_on")
        need(doc["rights"]["status"] in {"unconfirmed", "confirmed"}
             and type(doc["rights"]["public_copy_allowed"]) is bool, "invalid_rights")
        need(not doc["rights"]["public_copy_allowed"] or doc["rights"]["status"] == "confirmed", "unconfirmed_public_copy")
        text(doc["rights"]["note"]); day(doc["rights"]["checked_on"])
        shape(doc["audit"], "opinion limitation")
        text(doc["audit"]["opinion"]); text(doc["audit"]["limitation"])
        if doc["related_release"] is not None:
            shape(doc["related_release"], "url displayed_date binds_pdf_version")
            https(doc["related_release"]["url"]); day(doc["related_release"]["displayed_date"])
            need(type(doc["related_release"]["binds_pdf_version"]) is bool, "invalid_release_binding")
    for ev in evidence.values():
        shape(ev, "evidence_id document_id version_id document_sha256 locator metric_id definition_id period currency scale raw_value numeric_encoding provenance")
        doc = docs.get(ev["document_id"])
        need(doc is not None, "unknown_document_id")
        need(ev["version_id"] == doc["version_id"] and ev["document_sha256"] == doc["sha256"] and doc["sha256"] is not None, "evidence_document_mismatch")
        metric = metrics.get(ev["metric_id"])
        need(metric is not None and ev["definition_id"] == metric["definition_id"], "unknown_metric_definition")
        period(ev["period"]); unit({k: ev[k] for k in ("currency", "scale")})
        need(ev["period"]["kind"] in metric["period_kinds"], "metric_period_mismatch")
        locator = ev["locator"]
        if doc["data_origin"] == "real":
            shape(locator, "kind pdf_page printed_page statement_page page_region table_title row_label column_label unit_header")
            need(locator["kind"] == "pdf" and type(locator["pdf_page"]) is int and type(doc["pdf_pages"]) is int
                 and 1 <= locator["pdf_page"] <= doc["pdf_pages"], "invalid_page")
            for key in ("printed_page", "statement_page", "page_region", "table_title", "row_label", "column_label", "unit_header"):
                text(locator[key])
        else:
            shape(locator, "kind record_id row_label column_label unit_header")
            need(locator["kind"] == "synthetic", "invalid_synthetic_locator")
            for key in ("record_id", "row_label", "column_label", "unit_header"):
                text(locator[key])
        need(ev["numeric_encoding"] in {"decimal_string", "comma_thousands_integer", "space_thousands_integer"}, "unsupported_numeric_encoding")
        if ev["raw_value"] is not None:
            _raw_number(ev)
        provenance(ev["provenance"])
    for fact in facts.values():
        shape(fact, "fact_id organization_id document_id version_id metric_id definition_id value original_label currency scale period evidence_id evidence_digest provenance origin_role")
        doc = docs.get(fact["document_id"])
        need(doc is not None, "unknown_document_id")
        need(fact["organization_id"] == doc["organization_id"] and fact["version_id"] == doc["version_id"], "fact_document_mismatch")
        metric = metrics.get(fact["metric_id"])
        need(metric is not None and fact["definition_id"] == metric["definition_id"], "unknown_metric_definition")
        text(fact["original_label"]); period(fact["period"])
        need(fact["period"]["kind"] in metric["period_kinds"], "metric_period_mismatch")
        unit({k: fact[k] for k in ("currency", "scale")}); provenance(fact["provenance"])
        if fact["value"] is not None:
            number(fact["value"])
        role = fact["origin_role"]
        need(role in {"reported_period", "comparative_period"}, "invalid_origin_role")
        if role == "reported_period":
            need(fact["period"] == doc["report_period"] or (fact["period"]["kind"] == "instant"
                 and period_end(fact["period"]) == period_end(doc["report_period"])), "reported_period_mismatch")
        else:
            need(period_end(fact["period"]) < period_end(doc["report_period"]), "comparative_period_mismatch")
        if fact["evidence_id"] is None:
            need(fact["provenance"]["status"] not in CHECKED and fact["evidence_digest"] is None, "checked_fact_needs_evidence")
            continue
        ev = evidence.get(fact["evidence_id"])
        need(ev is not None, "unknown_evidence_id")
        need(fact["evidence_digest"] == digest(ev), "evidence_digest_mismatch")
        for key, other in (("document_id", "document_id"), ("version_id", "version_id"),
                           ("metric_id", "metric_id"), ("definition_id", "definition_id"),
                           ("period", "period"), ("currency", "currency"), ("scale", "scale")):
            need(fact[key] == ev[other], "fact_evidence_context_mismatch")
        need(fact["original_label"] == ev["locator"]["row_label"], "row_label_mismatch")
        need((fact["value"] is None and ev["raw_value"] is None) or
             (fact["value"] is not None and ev["raw_value"] is not None and number(fact["value"]) == _raw_number(ev)), "source_value_or_sign_mismatch")


def _raw_number(ev):
    if ev["numeric_encoding"] == "decimal_string":
        return number(ev["raw_value"])
    if ev["numeric_encoding"] == "space_thousands_integer":
        # Explicit source notation, not locale guessing or PDF extraction.
        import re
        raw = ev["raw_value"]
        need(isinstance(raw, str) and len(raw) <= 60, "invalid_raw_number")
        negative = raw.startswith("(") and raw.endswith(")")
        body = raw[1:-1] if negative else raw
        need(re.fullmatch(r"(?:[0-9]{1,3}(?: [0-9]{3})+|[0-9]+)", body) is not None,
             "invalid_raw_number")
        return number(("-" if negative else "") + body.replace(" ", ""))
    from .contracts import source_number, ContractError as LegacyError
    try:
        return source_number(ev["raw_value"])
    except LegacyError:
        raise ContractError("invalid_raw_number") from None


@boundary
def resolve_organization(catalog, alias):
    validate_catalog(catalog)
    if alias is None or (isinstance(alias, str) and not alias.strip()):
        raise ClarificationRequired("missing_fields", ["organization_id"])
    target = normalized(alias)
    matches = [o["organization_id"] for o in catalog["organizations"]
               if target in {normalized(x) for x in [o["organization_id"], o["name"], *o["aliases"]]}]
    if len(matches) > 1:
        raise ClarificationRequired("ambiguous_alias", ["organization_id"])
    need(len(matches) == 1, "unknown_organization_id")
    return matches[0]


@boundary
def fact_by_id(catalog, fact_id):
    """Inventory lookup, not a financial eligibility check or a new verification."""
    validate_catalog(catalog)
    identifier(fact_id)
    facts = {f["fact_id"]: f for f in catalog["facts"]}
    need(fact_id in facts, "unknown_fact_id")
    return deepcopy(facts[fact_id])
