"""A deterministic, synthetic-only simulator. No model, broker, prices API or new growth formula."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, localcontext
import hashlib
import json

from .contracts import ContractError, MSK, available_from, decimal, instant, validate_bundle
from .finance import calculate_metric, tool_request, validate_financial_result

VERSION = "0.1"
LABEL = "ИСКУССТВЕННЫЕ ДАННЫЕ / ВИРТУАЛЬНЫЙ СЦЕНАРИЙ"


class ScenarioError(ValueError):
    def __init__(self, code, blocked=False):
        self.code, self.blocked = code, blocked
        super().__init__(code)


def need(condition, code, blocked=False):
    if not condition:
        raise ScenarioError(code, blocked)


def fields(value, names):
    need(isinstance(value, dict) and set(value) == set(names.split()), "invalid_schema")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def stamp(value):
    try:
        return instant(value)
    except (ContractError, TypeError, ValueError):
        raise ScenarioError("invalid_timestamp") from None


def amount(value):
    try:
        return decimal(value)
    except (ContractError, TypeError, ValueError):
        raise ScenarioError("invalid_decimal") from None


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def checked_inputs(s):
    fields(s, "scenario_schema_version scenario_id data_mode provenance financial_bundle inputs decision_at rule portfolio instrument window calendar prices")
    need(s["scenario_schema_version"] == VERSION and s["scenario_id"] == "synthetic-revenue-scenario-v1", "invalid_scenario_version")
    need(s["data_mode"] == "synthetic_only", "synthetic_only")
    p = s["provenance"]
    fields(p, "kind label source_text note")
    need(p["kind"] == "self_created_synthetic" and p["label"] == LABEL, "synthetic_provenance_required")
    need(isinstance(p["note"], str) and 0 < len(p["note"]) <= 1000, "invalid_provenance")
    need(isinstance(p["source_text"], str) and 0 < len(p["source_text"]) <= 4000, "invalid_provenance")
    b = s["financial_bundle"]
    validate_bundle(b)
    doc = b["document"]
    need(doc["entity_id"] == "synthetic_example_group" and doc["document_id"] == "synthetic-revenue-document-v1"
         and doc["document_type"] == "synthetic_contract_fixture_not_a_pdf"
         and doc["document_url"] == "https://example.invalid/synthetic/revenue-v1"
         and doc["source_page_url"] == doc["document_url"], "real_synthetic_mixing_forbidden")
    raw = p["source_text"].encode("utf-8")
    need(doc["sha256"] == hashlib.sha256(raw).hexdigest() and doc["byte_length"] == len(raw)
         and doc["version_id"] == "sha256:" + doc["sha256"], "source_version_mismatch")
    cutoff = available_from(doc)
    if cutoff is not None:
        need(cutoff.astimezone(MSK).date().isoformat() > doc["report_period"]["end"], "publication_before_period_end")
    fields(s["inputs"], "previous_fact_id current_fact_id operation_id")
    need(s["inputs"] == {"previous_fact_id": "synthetic-revenue-2023", "current_fact_id": "synthetic-revenue-2024", "operation_id": "annual_growth_v1"}, "invalid_financial_inputs")
    need(all(f["fact_id"].startswith("synthetic-") and f["evidence_id"].startswith("synthetic-") for f in b["facts"]), "real_synthetic_mixing_forbidden")
    # The source is an authored table, never a claimed PDF extraction.
    for ev in b["evidence"]:
        need(f"{ev['column_label']}|revenue|{ev['raw_value']}|{ev['currency']}|{ev['scale']}" in p["source_text"].splitlines(), "synthetic_source_row_mismatch")
    decision = stamp(s["decision_at"])
    r = s["rule"]
    fields(r, "rule_id version condition threshold_pct execution_policy close_policy")
    need((r["rule_id"], r["version"], r["condition"], r["execution_policy"], r["close_policy"]) ==
         ("synthetic-revenue-threshold", "1", "growth_pct_gt", "next_session_open", "window_last_close"), "unsupported_rule")
    threshold = amount(r["threshold_pct"])
    need(0 <= threshold <= 100, "invalid_threshold")
    p = s["portfolio"]
    fields(p, "currency initial_cash max_notional_fraction lot_size fee_fixed slippage_bps")
    need(p["currency"] == "RUB", "currency_mismatch")
    cash, fraction, fee, slip = [amount(p[k]) for k in ("initial_cash", "max_notional_fraction", "fee_fixed", "slippage_bps")]
    need(0 < cash <= 1000000000 and cash == money(cash), "invalid_capital")
    need(0 < fraction <= 1, "invalid_fraction")
    need(0 <= fee <= 1000000000 and fee == money(fee), "invalid_fee")
    need(0 <= slip <= 1000, "invalid_slippage")
    need(type(p["lot_size"]) is int and 1 <= p["lot_size"] <= 1000000, "invalid_lot")
    fields(s["instrument"], "instrument_id currency corporate_actions")
    need(s["instrument"] == {"instrument_id": "SYNTH_ASSET", "currency": "RUB", "corporate_actions": "none_in_fixture"}, "unsupported_instrument_or_actions")
    fields(s["window"], "start end")
    start, end = [stamp(s["window"][k]) for k in ("start", "end")]
    need(start < end and end - start <= timedelta(days=366) and start <= decision <= end, "invalid_window")
    c = s["calendar"]
    fields(c, "calendar_id timezone synthetic sessions")
    need(c["calendar_id"] == "synthetic-sessions-v1" and c["timezone"] == "Europe/Moscow" and c["synthetic"] is True, "invalid_calendar")
    need(isinstance(c["sessions"], list) and 2 <= len(c["sessions"]) <= 64, "invalid_calendar")
    sessions, endpoints, previous = [], set(), None
    for row in c["sessions"]:
        fields(row, "open close")
        opened, closed = stamp(row["open"]), stamp(row["close"])
        need(start <= opened < closed <= end and (previous is None or opened > previous), "invalid_calendar_order")
        local_day = opened.astimezone(MSK).date()
        need(local_day == closed.astimezone(MSK).date() and local_day.weekday() < 5, "invalid_calendar_day")
        sessions.append((opened, closed)); endpoints.update((opened, closed)); previous = closed
    need(sessions[0][0] == start and sessions[-1][1] == end, "calendar_window_mismatch")
    need(len({opened.astimezone(MSK).date() for opened, _ in sessions}) == len(sessions), "duplicate_session_day")
    prices = s["prices"]
    fields(prices, "snapshot_id synthetic instrument_id currency observations")
    need(prices["snapshot_id"] == "synthetic-prices-v1" and prices["synthetic"] is True, "invalid_price_provenance")
    need(prices["instrument_id"] == s["instrument"]["instrument_id"], "instrument_mismatch")
    need(prices["currency"] == p["currency"], "currency_mismatch")
    need(isinstance(prices["observations"], list) and len(prices["observations"]) <= 128, "invalid_prices")
    values, previous = {}, None
    for row in prices["observations"]:
        fields(row, "at price")
        at, value = stamp(row["at"]), amount(row["price"])
        need(at not in values, "duplicate_price")
        need(previous is None or at > previous, "invalid_price_order")
        need(value > 0, "nonpositive_price")
        need(at in endpoints, "price_outside_calendar")
        values[at] = value; previous = at
    need(set(values) == endpoints, "missing_price", True)
    return b, decision, threshold, cash, fraction, fee, slip, sessions, values


def ledger_path(s, decision, cash, fraction, fee, slip, sessions, prices, buy, decision_event=None):
    entry = next((opened for opened, _ in sessions if opened > decision), None)
    need(entry is not None and entry < sessions[-1][1], "no_eligible_session", True)
    end = sessions[-1][1]
    capital, quantity, fees, slip_cost = cash, 0, Decimal(0), Decimal(0)
    ledger = []
    def record(at, kind, raw=None, effective=None, traded=0, nominal=Decimal(0), paid=Decimal(0), adverse=Decimal(0)):
        equity = money(cash + quantity * raw) if raw is not None else cash
        need(cash >= 0 and quantity >= 0, "negative_balance")
        ledger.append({"at": at.isoformat(), "event": kind, "traded_quantity": traded,
                       "raw_price": None if raw is None else str(raw), "execution_price": None if effective is None else str(effective),
                       "notional": str(nominal), "fee": str(paid), "slippage_cost": str(adverse),
                       "cash": str(cash), "quantity": quantity, "equity": str(equity)})
    record(sessions[0][0], "initial")
    events = sorted([(decision, 0, None)] + [(t, 1, p) for t, p in prices.items()])
    opened_once = False
    for at, order, raw in events:
        if order == 0:
            record(at, decision_event or ("signal_true" if buy else "signal_false"))
        elif at == entry and buy:
            need(not opened_once and quantity == 0, "duplicate_buy")
            effective = raw * (1 + slip / 10000)
            budget = (capital * fraction).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            lot = s["portfolio"]["lot_size"]
            quantity = int((budget / (effective * lot)).to_integral_value(rounding=ROUND_FLOOR)) * lot
            need(quantity > 0, "zero_lot", True)
            nominal = money(quantity * effective)
            need(nominal <= budget, "notional_limit")
            need(nominal + fee <= cash, "insufficient_cash", True)
            adverse = nominal - money(quantity * raw)
            cash -= nominal + fee; fees += fee; slip_cost += adverse; opened_once = True
            record(at, "buy", raw, effective, quantity, nominal, fee, adverse)
        elif at == end and quantity:
            traded = quantity
            effective = raw * (1 - slip / 10000)
            nominal = money(traded * effective)
            need(cash + nominal - fee >= 0, "insufficient_cash", True)
            adverse = money(traded * raw) - nominal
            cash += nominal - fee; quantity = 0; fees += fee; slip_cost += adverse
            record(at, "sell", raw, effective, traded, nominal, fee, adverse)
        else:
            record(at, "mark", raw)
    need(quantity == 0, "position_not_closed")
    return {"entry_at": entry.isoformat(), "exit_at": end.isoformat(), "ledger": ledger,
            "final_cash": str(cash), "final_quantity": quantity, "final_equity": str(cash),
            "pnl": str(cash - capital), "return_pct": str(money((cash / capital - 1) * 100)),
            "fees": str(fees), "slippage_cost": str(slip_cost)}


def simulate(s):
    """Atomic virtual plan: blocked/error results contain no partial deals or returns."""
    result = {"scenario_result_schema_version": VERSION, "scenario_id": None, "label": LABEL,
              "status": "error", "reason_code": "invalid_schema", "request_sha256": None,
              "financial_result": None, "eligibility": None, "scenario": None, "comparisons": None,
              "warnings": ["synthetic_only_not_market_performance", "no_broker_or_model", "legacy_gate_is_not_scenario_admission"]}
    try:
        result["request_sha256"] = fingerprint(s)
        with localcontext() as ctx:
            ctx.prec, ctx.rounding = 50, ROUND_HALF_UP
            b, decision, threshold, cash, fraction, fee, slip, sessions, prices = checked_inputs(s)
            result["scenario_id"] = s["scenario_id"]
            req = tool_request(**s["inputs"], mode="historical_as_of", as_of=s["decision_at"])
            fin = calculate_metric(b, req)
            validate_financial_result(fin, b, req)
            result["financial_result"] = fin
            cutoff = available_from(b["document"])
            result["eligibility"] = {"publication_available_from": None if cutoff is None else cutoff.isoformat(),
                                     "decision_at": decision.isoformat(), "rule_id": s["rule"]["rule_id"], "rule_version": s["rule"]["version"],
                                     "legacy_gate": deepcopy(fin["answer"]["scenario_gate"]) if fin["answer"] else None,
                                     "admission_contract": "SyntheticScenarioResult-0.1", "source_kind": "self_created_synthetic"}
            if fin["status"] != "answered":
                raise ScenarioError(fin["reason_code"], True)
            need(cutoff is not None and decision >= cutoff, "publication_unknown", True)
            signal = Decimal(fin["answer"]["calculation"]["growth_pct"]) > threshold
            main = ledger_path(s, decision, cash, fraction, fee, slip, sessions, prices, signal)
            hold = ledger_path(s, decision, cash, fraction, fee, slip, sessions, prices, True, "benchmark_entry_scheduled")
            money_path = ledger_path(s, decision, cash, fraction, fee, slip, sessions, prices, False, "cash_reference")
            result.update(status="completed", reason_code="signal_true" if signal else "signal_false", scenario=main,
                          comparisons={"cash_no_interest": money_path, "buy_and_hold_same_allocation": hold})
    except ScenarioError as exc:
        result.update(status="blocked" if exc.blocked else "error", reason_code=exc.code)
    except (ContractError, KeyError, TypeError, ValueError, ArithmeticError):
        result.update(status="error", reason_code="invalid_financial_or_scenario_data")
    return result


def validate_scenario_result(result, request):
    try:
        equal = fingerprint(result) == fingerprint(simulate(request))
    except (ValueError, TypeError):
        equal = False
    # Canonical JSON distinguishes False/0 and 1/1.0, unlike Python equality.
    need(equal, "tampered_scenario_result")


def assess_real_source(bundle, decision_at):
    """Real document diagnostic only. Never accepts or invents a price/calendar."""
    validate_bundle(bundle)
    stamp(decision_at)
    request = bundle["request"]
    ids = []
    for key in ("previous_period", "current_period"):
        matches = [f for f in bundle["facts"] if f["period"] == request[key] and f["metric_id"] == request["metric_id"]]
        need(len(matches) == 1, "ambiguous_or_missing_fact")
        ids.append(matches[0]["fact_id"])
    req = tool_request(*ids, mode="historical_as_of", as_of=decision_at)
    fin = calculate_metric(bundle, req)
    validate_financial_result(fin, bundle, req)
    return {"scenario_result_schema_version": VERSION, "label": "ПРОВЕРКА НАСТОЯЩЕГО ИСТОЧНИКА — ТОРГОВЛИ НЕТ",
            "status": "blocked", "reason_code": fin["reason_code"] if fin["status"] != "answered" else "real_simulation_not_supported",
            "document_id": bundle["document"]["document_id"], "document_version": bundle["document"]["version_id"],
            "decision_at": decision_at, "ledger": [], "return_pct": None,
            "legacy_gate": fin["answer"]["scenario_gate"] if fin["answer"] else None}
