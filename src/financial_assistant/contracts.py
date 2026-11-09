"""Narrow, fail-closed v0.1 contracts for manually annotated annual revenue.

This module does not download, search, or automatically verify source documents.
Validation establishes internal consistency, not truth or legal permission.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
import re

VERSION = "0.1"
FORMULA = "annual_growth_v1"
MSK = timezone(timedelta(hours=3))
CHECKED = {"assistant_checked", "human_reviewed"}


class ContractError(ValueError):
    """A malformed record, distinct from a valid financial refusal."""


def require(condition, message):
    if not condition:
        raise ContractError(message)


def shape(obj, fields):
    require(isinstance(obj, dict), "Expected an object")
    require(set(obj) == set(fields.split()), f"Fields mismatch: {set(obj) ^ set(fields.split())}")


def text(value):
    require(isinstance(value, str) and bool(value.strip()), "Expected nonempty text")


def decimal(value):
    require(isinstance(value, str) and len(value) <= 30, "Decimal must be a short string")
    require(re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is not None,
            "Decimal must use a point, no grouping, no exponent or NaN")
    result = Decimal(value)
    require(result == 0 or Decimal("0.000001") <= result.copy_abs() <= Decimal("1000000000000000000"),
            "Value outside the explicitly supported numeric range")
    return result


def day(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
            "Expected ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError("Invalid date") from exc


def instant(value):
    require(isinstance(value, str) and "T" in value, "Expected ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("Invalid timestamp") from exc
    require(result.utcoffset() is not None, "Timestamp needs a timezone")
    return result


def period(value):
    shape(value, "kind start end")
    require(value["kind"] == "duration", "Only duration facts supported")
    require(day(value["start"]) <= day(value["end"]), "Reversed period")


def publication(value):
    shape(value, "precision value source_url timezone version_binding")
    require(value["precision"] in {"unknown", "date", "timestamp"}, "Invalid precision")
    require(value["version_binding"] in {"unproven", "document_version"}, "Invalid binding")
    if value["precision"] == "unknown":
        require(value["value"] is None and value["source_url"] is None,
                "Unknown publication must not invent a value/source")
    else:
        url(value["source_url"])
        if value["precision"] == "date":
            day(value["value"])
            require(value["timezone"] == "Europe/Moscow", "Date policy needs a known timezone")
        else:
            instant(value["value"])


def url(value):
    require(isinstance(value, str) and value.startswith("https://") and " " not in value,
            "Expected an HTTPS URL")


def review(value):
    shape(value, "status method human_reviewer")
    require(value["status"] in CHECKED | {"candidate"}, "Invalid review status")
    text(value["method"])
    require(value["human_reviewer"] is None or isinstance(value["human_reviewer"], str),
            "Invalid reviewer")
    if value["status"] == "human_reviewed":
        text(value["human_reviewer"])


def source_number(raw):
    """Only the explicitly chosen comma-as-thousands document notation."""
    require(isinstance(raw, str), "Raw source number must be text")
    negative = raw.startswith("(") and raw.endswith(")")
    body = raw[1:-1] if negative else raw
    require(re.fullmatch(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)", body) is not None,
            "Ambiguous source number; manual interpretation required")
    return Decimal(("-" if negative else "") + body.replace(",", ""))


def validate_bundle(bundle):
    shape(bundle, "schema_version document evidence facts request scenario")
    require(bundle["schema_version"] == VERSION, "Unsupported schema version")
    doc = bundle["document"]
    shape(doc, "document_id entity_id entity_name consolidation accounting_standard document_type report_period source_page_url document_url version_id sha256 byte_length pdf_pages fetched_at approval_date publication related_release rights audit review")
    for field in ("document_id", "entity_id", "entity_name", "version_id", "document_type"):
        text(doc[field])
    require(doc["consolidation"] == "group", "Only a consolidated group is supported")
    require(doc["accounting_standard"] == "IFRS", "Only IFRS is supported")
    period(doc["report_period"])
    for field in ("source_page_url", "document_url"):
        url(doc[field])
    require(isinstance(doc["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", doc["sha256"]), "Invalid SHA-256")
    for field in ("byte_length", "pdf_pages"):
        require(type(doc[field]) is int and doc[field] > 0, "Invalid document size/pages")
    instant(doc["fetched_at"])
    day(doc["approval_date"])
    publication(doc["publication"])
    shape(doc["related_release"], "url displayed_date binds_pdf_version")
    url(doc["related_release"]["url"])
    day(doc["related_release"]["displayed_date"])
    require(type(doc["related_release"]["binds_pdf_version"]) is bool, "Invalid release binding")
    shape(doc["rights"], "status public_copy_allowed note checked_on")
    require(doc["rights"]["status"] in {"unconfirmed", "confirmed"}, "Invalid rights status")
    require(type(doc["rights"]["public_copy_allowed"]) is bool, "Invalid permission")
    require(not doc["rights"]["public_copy_allowed"] or doc["rights"]["status"] == "confirmed",
            "Unconfirmed rights cannot permit public copies")
    text(doc["rights"]["note"])
    day(doc["rights"]["checked_on"])
    shape(doc["audit"], "opinion limitation")
    text(doc["audit"]["opinion"])
    text(doc["audit"]["limitation"])
    review(doc["review"])
    require(isinstance(bundle["evidence"], list) and isinstance(bundle["facts"], list), "Expected lists")
    evidence = {}
    for ev in bundle["evidence"]:
        shape(ev, "evidence_id document_id version_id document_sha256 pdf_page printed_page statement_page page_region table_title row_label column_label period currency scale unit_header raw_value numeric_encoding review")
        text(ev["evidence_id"])
        require(ev["evidence_id"] not in evidence, "Duplicate evidence ID")
        require(ev["document_id"] == doc["document_id"] and ev["version_id"] == doc["version_id"]
                and ev["document_sha256"] == doc["sha256"], "Evidence points to another document/version/hash")
        require(type(ev["pdf_page"]) is int and 1 <= ev["pdf_page"] <= doc["pdf_pages"], "Page out of range")
        for field in ("printed_page", "statement_page", "page_region", "table_title", "row_label", "column_label", "unit_header"):
            text(ev[field])
        period(ev["period"])
        require(ev["column_label"] == ev["period"]["end"][:4], "Column and period differ")
        require(ev["currency"] in {"RUB", "USD"}, "Unsupported currency")
        require(type(ev["scale"]) is int and ev["scale"] in {1, 1000, 1000000, 1000000000}, "Invalid scale")
        require(ev["numeric_encoding"] == "comma_thousands_integer", "Unsupported raw notation")
        if ev["raw_value"] is not None:
            source_number(ev["raw_value"])
        review(ev["review"])
        evidence[ev["evidence_id"]] = ev
    ids = set()
    for fact in bundle["facts"]:
        shape(fact, "fact_id evidence_id entity_id consolidation accounting_standard metric_id original_label value currency scale period version_id review")
        text(fact["fact_id"])
        require(fact["fact_id"] not in ids, "Duplicate fact ID")
        ids.add(fact["fact_id"])
        ev = evidence.get(fact["evidence_id"])
        require(ev is not None, "Missing evidence reference")
        for field in ("entity_id", "consolidation", "accounting_standard", "version_id"):
            require(fact[field] == doc[field], f"Fact/document mismatch: {field}")
        for field in ("period", "currency", "scale"):
            require(fact[field] == ev[field], f"Fact/evidence mismatch: {field}")
        require(fact["original_label"] == ev["row_label"], "Row label mismatch")
        text(fact["metric_id"])
        period(fact["period"])
        review(fact["review"])
        if fact["value"] is None:
            require(ev["raw_value"] is None, "Null fact contradicts a source value")
        else:
            require(ev["raw_value"] is not None and decimal(fact["value"]) == source_number(ev["raw_value"]),
                    "Value or sign does not match manual source annotation")
    req = bundle["request"]
    shape(req, "request_id question entity_id consolidation accounting_standard metric_id current_period previous_period mode as_of formula_id")
    for field in ("request_id", "question", "entity_id", "metric_id", "formula_id"):
        text(req[field])
    for field in ("current_period", "previous_period"):
        period(req[field])
    require(req["mode"] in {"document_snapshot", "historical_as_of"}, "Invalid analysis mode")
    if req["mode"] == "historical_as_of":
        instant(req["as_of"])
    else:
        require(req["as_of"] is None, "Snapshot mode must not claim a historical cutoff")
    scenario = bundle["scenario"]
    shape(scenario, "rule_id rule_version condition threshold_pct data_mode signal_at calendar_id price_snapshot_id execution_at")
    require(scenario["data_mode"] == "synthetic_only", "Only future synthetic modelling is planned")
    require(scenario["condition"] == "growth_pct_gt", "Unsupported condition")
    decimal(scenario["threshold_pct"])
    text(scenario["rule_id"])
    text(scenario["rule_version"])
    for field in ("signal_at", "execution_at"):
        if scenario[field] is not None:
            instant(scenario[field])
    require(scenario["calendar_id"] is None and scenario["price_snapshot_id"] is None,
            "A real simulator and its inputs are not implemented in this contract check")


def available_from(doc):
    """Conservative historical cutoff. Never infer publication from retrieval."""
    pub = doc["publication"]
    publication(pub)
    if pub["precision"] == "unknown" or pub["version_binding"] != "document_version":
        return None
    if pub["precision"] == "timestamp":
        return instant(pub["value"])
    return datetime.combine(day(pub["value"]) + timedelta(days=1), time(), MSK)


def annual_pair(previous, current):
    p0, p1 = day(previous["start"]), day(previous["end"])
    c0, c1 = day(current["start"]), day(current["end"])
    # Calendar years: leap years remain comparable despite 365/366 days.
    return (p0.month, p0.day, p1.month, p1.day) == (1, 1, 12, 31) and p0.year == p1.year \
        and (c0.month, c0.day, c1.month, c1.day) == (1, 1, 12, 31) \
        and c0.year == c1.year == p0.year + 1


def answer(bundle):
    validate_bundle(bundle)
    req, doc = bundle["request"], bundle["document"]
    result = {"schema_version": VERSION, "request_id": req["request_id"], "status": "missing",
              "reason_code": None, "message": None, "fact_ids": [], "claims": [],
              "calculation": None, "warnings": ["manual_annotation"],
              "analysis_mode": req["mode"], "as_of": req["as_of"],
              "document_version": doc["version_id"], "availability_from": None,
              "scenario_gate": {"status": "blocked", "reasons": []}}
    reviews = [doc["review"]] + [x["review"] for x in bundle["facts"] + bundle["evidence"]]
    if any(x["status"] != "human_reviewed" for x in reviews):
        result["warnings"].append("source_checked_by_assistant")
    if doc["rights"]["status"] == "unconfirmed":
        result["warnings"].append("rights_for_public_copy_unconfirmed")
    if doc["audit"]["opinion"] == "qualified":
        result["warnings"].append("auditor_qualified_opinion_segment_disclosure")

    def finish(status, reason, message):
        result.update(status=status, reason_code=reason, message=message)
        gates = []
        if available_from(doc) is None:
            gates.append("publication_of_exact_version_unknown")
        if status != "answered":
            gates.append("no_valid_calculation")
        gates.extend(["calendar_and_prices_missing", "simulation_not_implemented"])
        result["scenario_gate"]["reasons"] = gates
        return result

    if req["formula_id"] != FORMULA or req["metric_id"] != "revenue":
        return finish("unsupported", "unsupported_operation", "Поддерживается только годовое изменение выручки.")
    for field in ("entity_id", "consolidation", "accounting_standard"):
        if req[field] != doc[field]:
            return finish("conflict", "entity_or_standard_mismatch", "Запрос и документ относятся к разным границам или стандартам.")
    if not annual_pair(req["previous_period"], req["current_period"]):
        return finish("conflict", "incompatible_periods", "Нужны два последовательных полных календарных года.")
    cutoff = available_from(doc)
    result["availability_from"] = cutoff.isoformat() if cutoff else None
    if req["mode"] == "historical_as_of":
        if cutoff is None:
            return finish("missing", "publication_unknown", "Дата доступности этой версии не подтверждена; исторический ответ запрещён.")
        if instant(req["as_of"]) < cutoff:
            return finish("missing", "not_yet_available", "Документ недоступен на выбранный момент по принятой политике.")
    elif cutoff is None:
        result["warnings"].append("snapshot_only_publication_unknown")
    if doc["review"]["status"] not in CHECKED:
        return finish("missing", "document_unchecked", "Документ ещё не проверен.")
    ev_by_id = {ev["evidence_id"]: ev for ev in bundle["evidence"]}
    selected = []
    for target in (req["previous_period"], req["current_period"]):
        candidates = [f for f in bundle["facts"] if f["period"] == target and f["metric_id"] == req["metric_id"]]
        if len(candidates) > 1:
            return finish("conflict", "duplicate_candidates", "Несколько фактов для одного входа; требуется явный выбор версии.")
        if not candidates or candidates[0]["value"] is None:
            return finish("missing", "value_missing", "Отсутствует одно из двух необходимых значений выручки.")
        f = candidates[0]
        if f["review"]["status"] not in CHECKED or ev_by_id[f["evidence_id"]]["review"]["status"] not in CHECKED:
            return finish("missing", "unverified_candidate", "Найденная ячейка ещё не проверена.")
        selected.append(f)
    previous, current = selected
    if previous["currency"] != current["currency"] or previous["scale"] != current["scale"]:
        return finish("conflict", "incompatible_units", "Валюта или масштаб различаются; автоматическая конвертация не поддерживается.")
    old, new = decimal(previous["value"]), decimal(current["value"])
    if old <= 0:
        return finish("unsupported", "nonpositive_base", "Процентное изменение поддерживается только при положительной базе.")
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.rounding = ROUND_HALF_UP
        delta = new - old
        growth = (new / old - 1) * 100
        shown = growth.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    result["fact_ids"] = [f["fact_id"] for f in selected]
    result["claims"] = [{"kind": "input_fact", "fact_id": f["fact_id"], "evidence_ids": [f["evidence_id"]]}
                        for f in selected]
    result["calculation"] = {"formula_id": FORMULA, "formula": "(current / previous - 1) * 100",
                             "input_fact_ids": result["fact_ids"], "delta": str(delta),
                             "delta_currency": current["currency"], "delta_scale": current["scale"],
                             "growth_pct": str(growth), "growth_pct_display": str(shown),
                             "precision": 50, "rounding": "ROUND_HALF_UP", "decimal_places": 2}
    result["claims"].append({"kind": "calculation", "formula_id": FORMULA,
                              "evidence_ids": [f["evidence_id"] for f in selected]})
    result["warnings"].append("source_rounding_limits_precision")
    return finish("answered", "ok", "Изменение выручки рассчитано по вручную проверенной версии документа.")


def validate_answer(result, bundle):
    """Validate structure and deterministic outcome, without proving source truth."""
    shape(result, "schema_version request_id status reason_code message fact_ids claims calculation warnings analysis_mode as_of document_version availability_from scenario_gate")
    require(result["schema_version"] == VERSION, "Answer schema version mismatch")
    require(result["request_id"] == bundle["request"]["request_id"], "Answer request mismatch")
    require(result["document_version"] == bundle["document"]["version_id"], "Answer version mismatch")
    require(result["analysis_mode"] == bundle["request"]["mode"] and result["as_of"] == bundle["request"]["as_of"], "Answer mode/cutoff mismatch")
    require(result["status"] in {"answered", "missing", "conflict", "unsupported"}, "Invalid answer status")
    text(result["reason_code"])
    text(result["message"])
    require(isinstance(result["warnings"], list), "Warnings must be a list")
    for warning in result["warnings"]:
        text(warning)
    shape(result["scenario_gate"], "status reasons")
    require(result["scenario_gate"]["status"] == "blocked" and bool(result["scenario_gate"]["reasons"]),
            "This stage cannot permit simulation")
    for reason in result["scenario_gate"]["reasons"]:
        text(reason)
    if result["availability_from"] is not None:
        instant(result["availability_from"])
    require(isinstance(result["fact_ids"], list) and isinstance(result["claims"], list), "Invalid answer lists")
    # A downstream formatter must not change the calculator's decision or conceal
    # a temporal/review limitation while retaining structurally valid JSON.
    # This reuses the pure reference calculation; Fraction tests independently
    # check its arithmetic. It is not an independent audit of the source facts.
    expected_result = answer(bundle)
    for field in ("status", "reason_code", "fact_ids", "availability_from", "scenario_gate"):
        require(result[field] == expected_result[field], f"Answer outcome mismatch: {field}")
    require(set(expected_result["warnings"]).issubset(result["warnings"]),
            "Answer hides a required limitation")
    if result["status"] != "answered":
        require(result["calculation"] is None and result["fact_ids"] == [] and result["claims"] == [],
                "A refusal must not contain a numeric calculation or claims")
        return
    facts = {f["fact_id"]: f for f in bundle["facts"]}
    evs = {e["evidence_id"]: e for e in bundle["evidence"]}
    require(len(result["fact_ids"]) == 2 and len(set(result["fact_ids"])) == 2,
            "Annual growth requires two distinct input facts")
    require(all(f in facts for f in result["fact_ids"]), "Unknown answer fact ID")
    calc = result["calculation"]
    shape(calc, "formula_id formula input_fact_ids delta delta_currency delta_scale growth_pct growth_pct_display precision rounding decimal_places")
    require(calc == expected_result["calculation"], "Calculation differs from the deterministic result")
    require(calc["formula_id"] == FORMULA and calc["formula"] == "(current / previous - 1) * 100", "Invalid formula")
    require(calc["input_fact_ids"] == result["fact_ids"], "Calculation inputs differ")
    current = facts[result["fact_ids"][1]]
    require(calc["delta_currency"] == current["currency"] and calc["delta_scale"] == current["scale"],
            "Result units differ from the source facts")
    require(calc["precision"] == 50 and calc["rounding"] == "ROUND_HALF_UP" and calc["decimal_places"] == 2, "Unexpected rounding policy")
    for key in ("delta", "growth_pct", "growth_pct_display"):
        require(isinstance(calc[key], str), "Calculation numbers must be strings")
        try:
            require(Decimal(calc[key]).is_finite(), "Nonfinite result")
        except ArithmeticError as exc:
            raise ContractError("Malformed result number") from exc
    require(len(result["claims"]) == 3, "Expected two input claims and one calculation claim")
    for claim, fact_id in zip(result["claims"][:2], result["fact_ids"]):
        shape(claim, "kind fact_id evidence_ids")
        require(claim["kind"] == "input_fact" and claim["fact_id"] == fact_id
                and claim["evidence_ids"] == [facts[fact_id]["evidence_id"]], "Input claim references differ")
    claim = result["claims"][2]
    shape(claim, "kind formula_id evidence_ids")
    expected = [facts[f]["evidence_id"] for f in result["fact_ids"]]
    require(claim["kind"] == "calculation" and claim["formula_id"] == FORMULA
            and claim["evidence_ids"] == expected, "Calculation lacks both input sources")
    require(all(e in evs for e in expected), "Unknown evidence ID")
