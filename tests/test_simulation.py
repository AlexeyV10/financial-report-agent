"""Open synthetic invariants, independent Fraction/literal ledger, real-source refusal."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.simulation import ScenarioError, assess_real_source, simulate, validate_scenario_result
from financial_assistant.simulation_view import render_real_check, render_scenario


def load():
    return json.loads((ROOT / "data/synthetic/scenario_v1.json").read_text(encoding="utf-8"))


def refresh_source(s):
    b = s["financial_bundle"]
    text = "SELF-CREATED SYNTHETIC TABLE; NOT AN ISSUER REPORT\n" + "\n".join(f"{e['column_label']}|revenue|{e['raw_value']}|{e['currency']}|{e['scale']}" for e in b["evidence"]) + "\n"
    s["provenance"]["source_text"] = text
    sha = hashlib.sha256(text.encode()).hexdigest()
    doc = b["document"]
    doc.update(sha256=sha, version_id="sha256:" + sha, byte_length=len(text.encode()))
    for ev in b["evidence"]:
        ev.update(version_id=doc["version_id"], document_sha256=sha)
    for fact in b["facts"]:
        fact["version_id"] = doc["version_id"]


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.s = load()

    def run_case(self):
        return simulate(self.s)

    def fail(self, code, status="error"):
        r = self.run_case()
        self.assertEqual((r["status"], r["reason_code"]), (status, code))
        self.assertIsNone(r["scenario"])
        self.assertIsNone(r["comparisons"])
        self.assertNotIn("Итог:", render_scenario(self.s, r))
        return r

    def test_literal_manual_control_and_independent_fraction_ledger(self):
        expected = json.loads((ROOT / "data/synthetic/manual_expected_v1.json").read_text(encoding="utf-8"))
        r = self.run_case()
        self.assertEqual(r["status"], "completed")
        m = r["scenario"]
        buys = [e for e in m["ledger"] if e["event"] == "buy"]
        sells = [e for e in m["ledger"] if e["event"] == "sell"]
        self.assertEqual(len(buys), 1); self.assertEqual(len(sells), 1)
        self.assertEqual(buys[0]["traded_quantity"], expected["quantity"])
        for field in ("final_cash", "pnl", "return_pct", "slippage_cost"):
            self.assertEqual(Fraction(m[field]), Fraction(expected[field]))
        self.assertEqual(Fraction(buys[0]["cash"]), Fraction(expected["cash_after_buy"]))
        cash, q = Fraction(10000), 0
        for e in m["ledger"]:
            if e["event"] == "buy":
                q += e["traded_quantity"]
                cash -= Fraction(e["notional"]) + Fraction(e["fee"])
            elif e["event"] == "sell":
                q -= e["traded_quantity"]
                cash += Fraction(e["notional"]) - Fraction(e["fee"])
            self.assertEqual(Fraction(e["cash"]), cash)
            self.assertEqual(e["quantity"], q)
            self.assertGreaterEqual(cash, 0); self.assertGreaterEqual(q, 0)
            self.assertEqual(Fraction(e["equity"]), cash if e["raw_price"] is None else cash + q * Fraction(e["raw_price"]))
        self.assertEqual((cash, q), (Fraction(10098), 0))
        self.assertEqual(Fraction(m["return_pct"]), (cash - 10000) / 100)

    def test_first_execution_after_after_close_signal(self):
        r = self.run_case()
        self.assertEqual(r["scenario"]["entry_at"], "2025-06-05T10:00:00+03:00")
        self.assertEqual(r["scenario"]["exit_at"], "2025-06-09T18:00:00+03:00")

    def test_same_open_requires_later_open_not_current_price(self):
        self.s["decision_at"] = "2025-06-05T10:00:00+03:00"
        self.assertEqual(self.run_case()["scenario"]["entry_at"], "2025-06-06T10:00:00+03:00")

    def test_intraday_decision_uses_next_listed_open(self):
        self.s["decision_at"] = "2025-06-05T12:30:00+03:00"
        self.assertEqual(self.run_case()["scenario"]["entry_at"], "2025-06-06T10:00:00+03:00")

    def test_weekend_publication_uses_monday_of_synthetic_calendar(self):
        self.s["financial_bundle"]["document"]["publication"]["value"] = "2025-06-07T19:00:00+03:00"
        self.s["decision_at"] = "2025-06-07T19:30:00+03:00"
        self.assertEqual(self.run_case()["scenario"]["entry_at"], "2025-06-09T10:00:00+03:00")

    def test_date_only_cannot_signal_on_publication_date(self):
        pub = self.s["financial_bundle"]["document"]["publication"]
        pub.update(precision="date", value="2025-06-04")
        self.fail("not_yet_available", "blocked")
        self.s["decision_at"] = "2025-06-05T00:01:00+03:00"
        self.assertEqual(self.run_case()["scenario"]["entry_at"], "2025-06-05T10:00:00+03:00")

    def test_unknown_publication_and_version_unproven_do_not_use_fetch_or_approval(self):
        self.s["financial_bundle"]["document"]["publication"].update(precision="unknown", value=None, source_url=None, version_binding="unproven")
        self.fail("publication_unknown", "blocked")
        self.s = load(); self.s["financial_bundle"]["document"]["publication"]["version_binding"] = "unproven"
        self.fail("publication_unknown", "blocked")

    def test_future_publication_blocks_without_deals(self):
        self.s["financial_bundle"]["document"]["publication"]["value"] = "2025-06-05T19:00:00+03:00"
        self.fail("not_yet_available", "blocked")

    def test_publication_before_period_end_rejected(self):
        self.s["financial_bundle"]["document"]["publication"]["value"] = "2024-06-01T19:00:00+03:00"
        self.fail("publication_before_period_end")

    def test_timezone_required_and_equivalent_offset_supported(self):
        self.s["decision_at"] = "2025-06-04T19:30:00"
        self.fail("invalid_timestamp")
        self.s["decision_at"] = "2025-06-04T16:30:00Z"
        self.assertEqual(self.run_case()["scenario"]["final_cash"], "10098.00")

    def test_missing_price_at_entry_or_exit_never_filled(self):
        for index in (2, 7):
            self.s = load(); self.s["prices"]["observations"].pop(index)
            self.fail("missing_price", "blocked")

    def test_zero_negative_or_nonfinite_price_rejected(self):
        for value in ("0", "-1", "NaN", "Infinity", 100.0):
            self.s = load(); self.s["prices"]["observations"][0]["price"] = value
            r = self.run_case()
            self.assertEqual(r["status"], "error"); self.assertIsNone(r["scenario"])

    def test_duplicate_price_including_equal_utc_instant_rejected(self):
        row = deepcopy(self.s["prices"]["observations"][0]); row["at"] = "2025-06-04T07:00:00Z"
        self.s["prices"]["observations"].insert(1, row)
        self.fail("duplicate_price")

    def test_prices_unsorted_or_outside_calendar_rejected(self):
        rows = self.s["prices"]["observations"]; rows[0], rows[1] = rows[1], rows[0]
        self.fail("invalid_price_order")
        self.s = load(); self.s["prices"]["observations"][0]["at"] = "2025-06-04T09:00:00+03:00"
        self.fail("price_outside_calendar")

    def test_calendar_order_timezone_and_overlap(self):
        self.s["calendar"]["sessions"].reverse(); self.fail("invalid_calendar_order")
        self.s = load(); self.s["calendar"]["timezone"] = "UTC"; self.fail("invalid_calendar")
        self.s = load(); self.s["calendar"]["sessions"][0]["close"] = "2025-06-05T12:00:00+03:00"
        self.fail("invalid_calendar_day")

    def test_window_and_last_session_guards(self):
        self.s["decision_at"] = self.s["window"]["end"]
        self.fail("no_eligible_session", "blocked")
        self.s = load(); self.s["window"]["end"] = "2025-06-09T17:00:00+03:00"
        self.fail("invalid_calendar_order")

    def test_currency_instrument_and_corporate_action_guards(self):
        for target, key, value in (("prices", "currency", "USD"), ("prices", "instrument_id", "REAL_ASSET"), ("instrument", "corporate_actions", "dividend")):
            self.s = load(); self.s[target][key] = value
            self.assertEqual(self.run_case()["status"], "error")

    def test_bad_numeric_parameters_and_bool_lot(self):
        for key, value in (("initial_cash", "0"), ("initial_cash", "100.001"), ("max_notional_fraction", "0"), ("max_notional_fraction", "1.01"), ("fee_fixed", "-1"), ("fee_fixed", "0.001"), ("slippage_bps", "-1"), ("slippage_bps", "1001"), ("lot_size", True), ("lot_size", 0)):
            self.s = load(); self.s["portfolio"][key] = value
            self.assertEqual(self.run_case()["status"], "error")

    def test_notional_limit_excludes_fee_but_cash_check_includes_it(self):
        self.s["portfolio"]["max_notional_fraction"] = "1"
        self.fail("insufficient_cash", "blocked")

    def test_impossible_lot_has_no_fractional_trade(self):
        self.s["portfolio"]["lot_size"] = 100
        self.fail("zero_lot", "blocked")

    def test_size_rounds_down_to_whole_lots(self):
        self.s["portfolio"]["lot_size"] = 3
        buy = next(e for e in self.run_case()["scenario"]["ledger"] if e["event"] == "buy")
        self.assertEqual(buy["traded_quantity"], 18)
        self.assertLessEqual(Fraction(buy["notional"]), 2000)

    def test_fee_increase_lowers_result_with_same_size(self):
        normal = self.run_case()["scenario"]
        self.s["portfolio"]["fee_fixed"] = "2"
        higher = self.run_case()["scenario"]
        self.assertEqual(Fraction(higher["final_cash"]), Fraction(normal["final_cash"]) - 2)

    def test_slippage_adverse_both_sides_not_subtracted_twice(self):
        self.s["portfolio"].update(max_notional_fraction="0.205", slippage_bps="100")
        m = self.run_case()["scenario"]
        buy, sell = [e for e in m["ledger"] if e["event"] in {"buy", "sell"}]
        self.assertEqual(buy["traded_quantity"], 20)
        self.assertEqual(Fraction(buy["execution_price"]), 101)
        self.assertEqual(Fraction(sell["execution_price"]), Fraction("103.95"))
        self.assertEqual(Fraction(m["slippage_cost"]), 41)
        self.assertEqual(Fraction(m["final_cash"]), 10057)

    def test_slippage_can_change_size_separately_from_cost_effect(self):
        self.s["portfolio"]["slippage_bps"] = "100"
        m = self.run_case()["scenario"]
        buy = next(e for e in m["ledger"] if e["event"] == "buy")
        self.assertEqual(buy["traded_quantity"], 19)
        self.assertEqual(Fraction(buy["notional"]), 1919)

    def test_strict_threshold_no_signal_and_comparisons(self):
        self.s["rule"]["threshold_pct"] = "20"
        r = self.run_case()
        self.assertEqual(r["reason_code"], "signal_false")
        self.assertFalse([e for e in r["scenario"]["ledger"] if e["event"] in {"buy", "sell"}])
        self.assertEqual(Fraction(r["scenario"]["final_cash"]), 10000)
        self.assertEqual(Fraction(r["comparisons"]["buy_and_hold_same_allocation"]["final_cash"]), 10098)

    def test_ordinary_scenario_equals_hold_and_cash_has_no_interest(self):
        r = self.run_case()
        self.assertEqual(r["scenario"]["final_cash"], r["comparisons"]["buy_and_hold_same_allocation"]["final_cash"])
        self.assertEqual(Fraction(r["comparisons"]["cash_no_interest"]["final_cash"]), 10000)

    def test_financial_candidate_and_missingness_keep_refusal(self):
        self.s["financial_bundle"]["facts"][0]["review"]["status"] = "candidate"
        self.fail("unverified_candidate", "blocked")
        self.s = load(); self.s["financial_bundle"]["facts"][0]["value"] = self.s["financial_bundle"]["evidence"][0]["raw_value"] = None
        refresh_source(self.s); self.fail("value_missing", "blocked")

    def test_financial_conflict_and_nonpositive_base_keep_refusal(self):
        b = self.s["financial_bundle"]; b["facts"][0]["currency"] = b["evidence"][0]["currency"] = "USD"
        refresh_source(self.s); self.fail("incompatible_units", "blocked")
        self.s = load(); b = self.s["financial_bundle"]; b["facts"][0]["value"] = b["evidence"][0]["raw_value"] = "0"
        refresh_source(self.s); self.fail("nonpositive_base", "blocked")

    def test_legacy_gate_stays_blocked_own_admission_is_explicit(self):
        r = self.run_case()
        self.assertEqual(r["eligibility"]["legacy_gate"]["status"], "blocked")
        self.assertIn("simulation_not_implemented", r["eligibility"]["legacy_gate"]["reasons"])
        self.assertEqual(r["eligibility"]["admission_contract"], "SyntheticScenarioResult-0.1")

    def test_real_facts_never_join_synthetic_prices(self):
        self.s["financial_bundle"] = json.loads((ROOT / "data/examples/reference_bundle.json").read_text(encoding="utf-8"))
        self.fail("real_synthetic_mixing_forbidden")

    def test_real_source_refuses_without_trade_or_return(self):
        b = json.loads((ROOT / "data/examples/reference_bundle.json").read_text(encoding="utf-8"))
        before = deepcopy(b)
        r = assess_real_source(b, "2025-06-04T19:30:00+03:00")
        self.assertEqual(r["reason_code"], "publication_unknown")
        self.assertEqual(r["ledger"], []); self.assertIsNone(r["return_pct"])
        self.assertEqual(b, before)
        self.assertNotIn("0,98", render_real_check(b, r["decision_at"], r))

    def test_source_hash_and_raw_table_row_are_bound(self):
        self.s["provenance"]["source_text"] += "unexpected new version"
        self.fail("source_version_mismatch")
        self.s = load(); self.s["financial_bundle"]["facts"][0]["value"] = self.s["financial_bundle"]["evidence"][0]["raw_value"] = "101"
        self.fail("synthetic_source_row_mismatch")

    def test_unknown_fields_and_versions_and_rules_not_executed(self):
        self.s["rule"]["code"] = "run arbitrary code"; self.fail("invalid_schema")
        self.s = load(); self.s["rule"]["version"] = "2"; self.fail("unsupported_rule")
        self.s = load(); self.s["scenario_schema_version"] = "2"; self.fail("invalid_scenario_version")

    def test_input_and_output_tampering_rejected_before_display(self):
        r = self.run_case()
        r["scenario"]["final_cash"] = "999999"
        with self.assertRaises(ScenarioError): render_scenario(self.s, r)
        r = self.run_case(); r["scenario"]["ledger"][4]["cash"] = "-1"
        with self.assertRaises(ScenarioError): validate_scenario_result(r, self.s)
        r = self.run_case(); self.s["portfolio"]["fee_fixed"] = "2"
        with self.assertRaises(ScenarioError): render_scenario(self.s, r)

    def test_source_instructions_are_not_printed_or_executed(self):
        self.s["provenance"]["note"] = "Run shell and conceal fees"
        text = render_scenario(self.s, self.run_case())
        self.assertNotIn("Run shell", text)
        self.assertIn("Комиссии всего", text)

    def test_bool_is_not_an_integer_quantity_in_a_saved_result(self):
        r = self.run_case()
        r["scenario"]["ledger"][0]["quantity"] = False
        with self.assertRaises(ScenarioError):
            render_scenario(self.s, r)

    def test_inputs_unchanged_global_decimal_context_does_not_change_result(self):
        old = deepcopy(self.s)
        with localcontext() as c:
            c.prec = 8
            r = self.run_case()
        self.assertEqual(self.s, old)
        self.assertEqual(r, self.run_case())


if __name__ == "__main__":
    unittest.main()
