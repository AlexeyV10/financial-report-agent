"""Step12 offline grading of the bounded structured renderer, not general text QA.

No answering/model/retrieval/simulation imports: replay uses saved records and gold.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

VERSION = "step12-structured-grader-v1"
FINANCIAL_IDS = ["QA03", "QA06", "QA07"]
UNSUPPORTED_IDS = ["QA01", "QA02", "QA04", "QA05", "QA08"]
WARNING_PHRASES = {
    "manual_annotation": "Финансовые факты подготовлены вручную",
    "source_checked_by_assistant": "проверка пользователем не заявляется",
    "rights_for_public_copy_unconfirmed": "Право распространять копию отчёта и его страницы не подтверждено",
    "auditor_qualified_opinion_segment_disclosure": "Аудиторское мнение с оговоркой",
    "snapshot_only_publication_unknown": "историческая доступность не подтверждена",
    "source_rounding_limits_precision": "дополнительные внутренние знаки не повышают точность отчёта",
}


def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def same(a, b):
    return canonical(a) == canonical(b)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError("duplicate_key")
            obj[k] = v
        return obj
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def num_equal(a, b):
    pattern = r"-?(?:0|[1-9]\d*)(?:\.\d+)?"
    if not all(isinstance(v, str) and re.fullmatch(pattern, v) for v in (a, b)):
        return False
    try:
        return Decimal(a) == Decimal(b)
    except InvalidOperation:
        return False


def shown(v, signed=False):
    n = Decimal(v)
    return ("+" if signed and n > 0 else "") + format(n, ",f").replace(",", " ").replace(".", ",")


def normalized_claims(fin, asset_sha):
    """Only actual payload fields; receives no case or expected values."""
    a = fin["answer"]
    fs = fin["inputs"]
    calc = a["calculation"]
    if fin["status"] != "answered" or len(fs) != 2 or not calc:
        return []
    p, c = fs
    base = {"entity_id": p["entity_id"], "consolidation": p["consolidation"],
            "accounting_standard": p["accounting_standard"], "document_version": a["document_version"],
            "analysis_mode": a["analysis_mode"], "as_of": a["as_of"], "asset_sha256": asset_sha}
    def claim(measure, value, currency, scale, facts):
        return dict(base, measure=measure, value=value, currency=currency, scale=scale,
                    periods=[f["period"] for f in facts], evidence_ids=[f["evidence_id"] for f in facts])
    return [claim("previous_revenue", p["value"], p["currency"], p["scale"], [p]),
            claim("current_revenue", c["value"], c["currency"], c["scale"], [c]),
            claim("delta", calc["delta"], calc["delta_currency"], calc["delta_scale"], fs),
            claim("growth_pct", calc["growth_pct_display"], None, 1, fs)]


def claim_ok(actual, target, context):
    for key in ("entity_id", "consolidation", "accounting_standard", "document_version", "analysis_mode", "as_of", "asset_sha256"):
        if not same(actual.get(key), context[key]):
            return False
    return (all(same(actual.get(k), target[k]) for k in ("measure", "currency", "scale", "periods", "evidence_ids"))
            and num_equal(actual.get("value"), target["value"]))


def text_claim_audit(text, fin):
    """Small grammar of existing RUB/annual renderer; extra numeric lines fail.

    Repeated formula substitution is checked, not counted as extra independent claims.
    """
    p, c = fin["inputs"]
    calc = fin["answer"]["calculation"]
    def fact_line(f):
        period = f["period"]
        date = lambda d: ".".join(reversed(d.split("-")))
        return date(period["start"]) + "–" + date(period["end"]) + ": " + shown(f["value"]) + " млн руб."
    lines = [fact_line(p), fact_line(c),
             "Изменение: " + shown(calc["delta"], True) + " млн руб.; " + shown(calc["growth_pct_display"], True) + "%.",
             "Формула: (текущее / предыдущее − 1) × 100%.",
             "Подстановка: (" + shown(c["value"]) + " / " + shown(p["value"]) + " − 1) × 100% = " + shown(calc["growth_pct_display"], True) + "%."]
    # Source captions contain a year and a unit, but do not assert an amount.
    lines += ["  Таблица: " + s["table_title"] + ". Строка: «" + s["row_label"] + "»; единица: " + s["unit_header"]
              for s in fin["sources"]]
    actual = [s for s in text.splitlines() if re.search(r"\d", s) and re.search(r"руб\.|долл\.|%", s)]
    return same(actual, lines)


def grade_financial(record, case):
    issues, confirmed, checked = [], 0, 0
    expected, ctx = case["expected"], case["context"]
    if record.get("availability") != "executed":
        return {"passed": False, "issues": ["not_run"], "confirmed": 0, "checked": 0}
    try:
        output = record["output"]
        agent = record["variant"] == "C/LLM"
        if agent and output["status"] != "completed":
            issues.append("agent_execution_" + output["status"] + ":" + output["reason_code"])
        view = output["user_response"] if agent else output
        fin = view["financial_result"]
        if not fin:
            issues.append("no_financial_payload")
        else:
            if (view["status"], view["reason_code"]) != (expected["status"], expected["reason_code"]):
                issues.append("user_outcome_mismatch")
            if (fin["status"], fin["reason_code"]) != (expected["status"], expected["reason_code"]):
                issues.append("financial_outcome_mismatch")
            inp = record["input"]
            if inp["asset_sha256"] != ctx["asset_sha256"] or not same(inp["reproduction"], case["reproduction"]):
                issues.append("input_context_mismatch")
            doc = inp["document"]
            for k, ck in (("entity_id", "entity_id"), ("consolidation", "consolidation"), ("accounting_standard", "accounting_standard"), ("version_id", "document_version"), ("sha256", "document_sha256")):
                if doc[k] != ctx[ck]:
                    issues.append("document_" + k)
            if not (fin["document_id"] == ctx["document_id"] and fin["metric_id"] == ctx["metric_id"] and fin["accounting_standard"] == ctx["accounting_standard"]):
                issues.append("financial_context_mismatch")
            if not same(fin["requested_periods"], dict(zip(("previous", "current"), ctx["periods"]))):
                issues.append("requested_period_mismatch")
            if (fin["request"]["mode"], fin["request"]["as_of"]) != (ctx["analysis_mode"], ctx["as_of"]):
                issues.append("financial_mode_mismatch")
            warnings = set(fin["warnings"]) | set(record.get("origin_notices", []))
            if not set(expected["mandatory_warnings"]) <= warnings:
                issues.append("mandatory_warning_missing")
            if record["variant"] != "finance_component" and any(
                    WARNING_PHRASES[k] not in view["text"] for k in expected["mandatory_warnings"] if k in WARNING_PHRASES):
                issues.append("mandatory_warning_not_rendered")
            a = fin["answer"]
            if a is not None and ((a["analysis_mode"], a["as_of"], a["document_version"]) !=
                                  (ctx["analysis_mode"], ctx["as_of"], ctx["document_version"]) or
                                  (a["status"], a["reason_code"]) != (fin["status"], fin["reason_code"])):
                issues.append("answer_context_mismatch")
            if expected["status"] == "answered":
                claims = normalized_claims(fin, inp["asset_sha256"])
                checked = len(claims)
                sources = {s["evidence_id"]: s for s in fin["sources"]}
                source_ok = {}
                for loc in case["locators"]:
                    s = sources.get(loc["evidence_id"], {})
                    source_ok[loc["evidence_id"]] = (all(same(s.get(k), v) for k, v in loc.items()) and
                        s.get("url") == ctx["document_url"] + "#page=" + str(loc["pdf_page"]))
                targets = {o["measure"]: o for o in expected["outputs"]}
                facts_ok = all(all(f[k] == ctx[k] for k in ("entity_id", "consolidation", "accounting_standard", "metric_id"))
                               and f["version_id"] == ctx["document_version"] for f in fin["inputs"])
                calc = a["calculation"]
                formula_ok = (calc["formula_id"] == expected["formula_id"] and calc["formula"] == "(current / previous - 1) * 100"
                    and calc["input_fact_ids"] == [f["fact_id"] for f in fin["inputs"]]
                    and calc["rounding"] == "ROUND_HALF_UP" and type(calc["decimal_places"]) is int and calc["decimal_places"] == 2)
                expected_claims = [{"kind":"input_fact", "fact_id":f["fact_id"], "evidence_ids":[f["evidence_id"]]} for f in fin["inputs"]]
                expected_claims.append({"kind":"calculation", "formula_id":calc["formula_id"], "evidence_ids":[f["evidence_id"] for f in fin["inputs"]]})
                binding_ok = same(a["claims"], expected_claims) and a["fact_ids"] == calc["input_fact_ids"]
                text_ok = text_claim_audit(view["text"], fin)
                if not text_ok:
                    issues.append("numeric_text_not_supported_by_payload")
                for cl in claims:
                    ok = (cl["measure"] in targets and claim_ok(cl, targets[cl["measure"]], ctx) and facts_ok and binding_ok
                          and all(source_ok.get(e, False) for e in cl["evidence_ids"]) and text_ok)
                    if cl["measure"] in {"delta", "growth_pct"}:
                        ok = ok and formula_ok
                    confirmed += int(ok)
                if checked != 4 or confirmed != 4:
                    issues.append("numeric_claim_context_or_source_mismatch")
                if any(s["url"] not in view["text"] for s in fin["sources"]) or a["document_version"] not in view["text"]:
                    issues.append("source_not_in_user_text")
            else:
                no_numbers = (not fin["inputs"] and not fin["sources"] and
                              (a is None or (a["calculation"] is None and a["claims"] == [] and a["fact_ids"] == [])))
                if not no_numbers:
                    issues.append("refusal_contains_financial_payload")
                if record["variant"] != "finance_component" and ("Ответ с числом не сформирован." not in view["text"] or
                        re.search(r"Изменение:|Подстановка:|\d[\d ,]*%|\d[\d ,]* млн руб\.", view["text"])):
                    issues.append("refusal_text_contains_number_or_lacks_notice")
    except (KeyError, TypeError, ValueError, InvalidOperation):
        issues.append("malformed_actual_payload")
    return {"passed": not issues, "issues": issues, "confirmed": confirmed, "checked": checked}


def grade_record(record, case, controls):
    if record.get("availability") != "executed":
        return {"passed": False, "issues": ["not_run"], "confirmed": 0, "checked": 0}
    if case["suite"] == "financial_qa":
        return grade_financial(record, case)
    issues = []
    try:
        output = record["output"]
        if case["suite"] == "interface":
            view = output["user_response"] if record["variant"] == "C/LLM" else output
            if (view["status"], view["reason_code"]) != ("clarification", "period_needs_clarification") or view["financial_result"] is not None:
                issues.append("wrong_clarification")
            if record["variant"] == "C/LLM" and (output["trace"]["events"] or output["status"] != "clarification"):
                issues.append("clarification_used_agent_or_tools")
        else:
            if record["input"]["asset_sha256"] != case["context"]["asset_sha256"]:
                issues.append("scenario_asset_mismatch")
            if output["status"] != "completed" or output["reason_code"] != "signal_true":
                issues.append("scenario_not_completed")
            sc = output["scenario"]
            for target in case["expected"]["outputs"]:
                k = "fees" if target["measure"] == "total_fees" else target["measure"]
                if not num_equal(sc[k], target["value"]):
                    issues.append("scenario_" + k)
            control = controls[case["case_id"]]
            for key in ("entry_at", "exit_at", "final_quantity"):
                if not same(sc[key], control[key]):
                    issues.append("scenario_" + key)
            trades = [e for e in sc["ledger"] if e["event"] in {"buy", "sell"}]
            if len(trades) != 2:
                issues.append("scenario_trade_count")
            else:
                for trade, expected_trade in zip(trades, control["trades"]):
                    for key, val in expected_trade.items():
                        match = num_equal(trade.get(key), val) if key in {"execution_price", "cash", "notional", "fee"} else same(trade.get(key), val)
                        if not match:
                            issues.append("ledger_" + key)
            if output["eligibility"]["source_kind"] != "self_created_synthetic" or "synthetic_only_not_market_performance" not in output["warnings"]:
                issues.append("synthetic_origin_missing")
            if output["eligibility"]["decision_at"] != case["context"]["as_of"]:
                issues.append("scenario_decision_mismatch")
            if any(type(e["quantity"]) is not int or Decimal(e["cash"]) < 0 or e["quantity"] < 0 for e in sc["ledger"]):
                issues.append("scenario_negative_or_invalid_balance")
            if output["eligibility"]["legacy_gate"]["status"] != "blocked":
                issues.append("legacy_gate_changed")
    except (KeyError, TypeError, ValueError):
        issues.append("malformed_actual_payload")
    return {"passed": not issues, "issues": issues, "confirmed": 0, "checked": 0}


def ratio(x, n):
    return {"correct": x, "total": n, "fraction": f"{x}/{n}" if n else None, "status": "measured" if n else "not_measured"}


def summarize(rows):
    out = {}
    for variant in ("B", "C/LLM"):
        selected = [r for r in rows if r["variant"] == variant and r["suite"] == "financial_qa"]
        numeric = [r for r in selected if r["case_id"] == "QA03"]
        refusals = [r for r in selected if r["case_id"] in {"QA06", "QA07"}]
        claims = [r for r in selected if r["checked"]]
        out[variant] = {"numeric_accuracy": ratio(sum(r["passed"] for r in numeric), len(numeric)),
                        "correct_refusals": ratio(sum(r["passed"] for r in refusals), len(refusals)),
                        "claim_confirmation": ratio(sum(r["confirmed"] for r in claims), sum(r["checked"] for r in claims)),
                        "reserved_financial": ratio(0, 0), "supported_financial_coverage": "3/10",
                        "failed_answerable_cases": [r["case_id"] for r in numeric if not r["passed"]]}
    for variant, suite in (("B", "interface"), ("C/LLM", "interface"), ("finance_component", "financial_qa"), ("simulator", "scenario")):
        selected = [r for r in rows if r["variant"] == variant and r["suite"] == suite]
        out[variant + "/" + suite] = ratio(sum(r["passed"] for r in selected), len(selected))
    return out
