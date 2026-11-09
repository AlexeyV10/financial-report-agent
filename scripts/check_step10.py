"""Current step-10 checks. Does not start/download a model, source PDF or index."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    out, work = ROOT / "evaluation/step10_2026-11-09", ROOT / "tmp/step10-checks"
    out.mkdir(exist_ok=True); work.mkdir(exist_ok=True)
    fixture = json.loads((ROOT / "data/synthetic/scenario_v1.json").read_text(encoding="utf-8"))
    frozen = json.loads((ROOT / "data/synthetic/frozen_rule_v1.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((ROOT / "data/synthetic/scenario_v1.json").read_bytes()).hexdigest() == frozen["fixture_sha256"]
    cases = []
    def case(name, mutations, code, token):
        s = deepcopy(fixture)
        for path, value in mutations:
            target = s
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
        path = work / (name + ".json"); write(path, s)
        cases.append((name, ["--fixture", str(path)], code, token))
    cases.append(("normal", ["--save", str(work / "demo.txt")], 0, "10 098,00"))
    cases.append(("real_source", ["--case", "real-source"], 0, "publication_unknown"))
    case("no_signal", [(("rule", "threshold_pct"), "20")], 0, "10 000")
    case("missing_entry_price", [(("prices", "observations"), fixture["prices"]["observations"][:2] + fixture["prices"]["observations"][3:])], 0, "missing_price")
    case("missing_final_price", [(("prices", "observations"), fixture["prices"]["observations"][:-1])], 0, "missing_price")
    case("future_publication", [(("financial_bundle", "document", "publication", "value"), "2025-06-05T19:00:00+03:00")], 0, "not_yet_available")
    pub = deepcopy(fixture["financial_bundle"]["document"]["publication"]); pub.update(precision="unknown", value=None, source_url=None, version_binding="unproven")
    case("unknown_publication", [(("financial_bundle", "document", "publication"), pub)], 0, "publication_unknown")
    pub = deepcopy(fixture["financial_bundle"]["document"]["publication"]); pub.update(precision="date", value="2025-06-04")
    case("date_only", [(("financial_bundle", "document", "publication"), pub), (("decision_at",), "2025-06-05T00:01:00+03:00")], 0, "10 098,00")
    case("weekend", [(("financial_bundle", "document", "publication", "value"), "2025-06-07T19:00:00+03:00"), (("decision_at",), "2025-06-07T19:30:00+03:00")], 0, "2025-06-09T10:00:00+03:00")
    case("insufficient_cash", [(("portfolio", "max_notional_fraction"), "1")], 0, "insufficient_cash")
    case("zero_lot", [(("portfolio", "lot_size"), 100)], 0, "zero_lot")
    case("invalid_fee", [(("portfolio", "fee_fixed"), "-1")], 2, "invalid_fee")
    case("wrong_currency", [(("prices", "currency"), "USD")], 2, "currency_mismatch")
    case("corporate_action", [(("instrument", "corporate_actions"), "split")], 2, "unsupported_instrument_or_actions")
    case("slippage_fixed_quantity", [(("portfolio", "max_notional_fraction"), "0.205"), (("portfolio", "slippage_bps"), "100")], 0, "10 057,00")
    case("naive_date", [(("decision_at",), "2025-06-04T19:30:00")], 2, "invalid_timestamp")
    real = json.loads((ROOT / "data/examples/reference_bundle.json").read_text(encoding="utf-8"))
    case("real_synthetic_mixing", [(("financial_bundle",), real)], 2, "real_synthetic_mixing_forbidden")
    invalid = work / "invalid.json"; invalid.write_text("not JSON", encoding="utf-8")
    cases += [("invalid_json", ["--fixture", str(invalid)], 2, "Техническая ошибка"),
              ("missing_fixture", ["--fixture", str(work / "absent.json")], 2, "Техническая ошибка"),
              ("synthetic_as_of_not_ignored", ["--as-of", "2025-06-04T19:30:00+03:00"], 2, "Техническая ошибка"),
              ("real_empty_as_of", ["--case", "real-source", "--as-of", ""], 2, "Техническая ошибка"),
              ("real_fixture_forbidden", ["--case", "real-source", "--fixture", str(ROOT / "data/synthetic/scenario_v1.json")], 2, "Техническая ошибка"),
              ("protect_reference", ["--save", str(ROOT / "data/examples/reference_bundle.json")], 2, "Техническая ошибка"),
              ("protect_code", ["--trace", str(ROOT / "src/financial_assistant/contracts.py")], 2, "Техническая ошибка"),
              ("unknown_code_argument", ["--code", "arbitrary"], 2, "Техническая ошибка")]
    outcomes = []
    for name, args, expected, token in cases:
        trace = work / (name + ".trace.json")
        command = [sys.executable, str(ROOT / "scripts/simulate_scenario.py"), *args]
        if "--trace" not in args: command += ["--trace", str(trace)]
        r = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", timeout=15)
        passed = r.returncode == expected and token in r.stdout
        result = json.loads(trace.read_text(encoding="utf-8"))["result"] if trace.exists() else None
        if result is not None and result["status"] != "completed":
            assert result.get("scenario") is None and result.get("return_pct") is None
            assert "Итог:" not in r.stdout
        if name == "real_empty_as_of": assert "ИСКУССТВЕННЫЕ ДАННЫЕ" not in r.stdout
        outcomes.append({"case": name, "exit_code": r.returncode, "expected_exit_code": expected, "passed": passed,
                         "status": None if result is None else result["status"], "reason": None if result is None else result["reason_code"]})
        assert passed, (name, r.returncode, r.stdout, r.stderr)
    regressions = []
    for name, script, args, token in (("B_normal", "assistant.py", [], "+15,30%"),
                                     ("B_historical", "assistant.py", ["--mode", "historical", "--as-of", "2025-02-14T10:00:00+03:00"], "Исторический ответ"),
                                     ("C_mock_normal", "agent_assistant.py", ["--adapter", "mock"], "+15,30%"),
                                     ("C_mock_historical", "agent_assistant.py", ["--adapter", "mock", "--mode", "historical", "--as-of", "2025-02-14T10:00:00+03:00"], "Исторический ответ")):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT, capture_output=True, encoding="utf-8", timeout=20)
        passed = r.returncode == 0 and token in r.stdout
        regressions.append({"case": name, "passed": passed}); assert passed, name
    with (out / "unit-tests.txt").open("w", encoding="utf-8") as log:
        tests = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT / "tests")))
    assert tests.wasSuccessful(), "See unit-tests.txt"
    trace = json.loads((work / "normal.trace.json").read_text(encoding="utf-8"))
    result, manual = trace["result"], json.loads((ROOT / "data/synthetic/manual_expected_v1.json").read_text(encoding="utf-8"))
    m = result["scenario"]
    cash = Fraction(10000) - Fraction(20)*100 - 1 + Fraction(20)*105 - 1
    assert cash == Fraction(manual["final_cash"]) == Fraction(m["final_cash"])
    assert (cash - 10000)/100 == Fraction(manual["return_pct"]) == Fraction(m["return_pct"])
    independent = {"method": "Fraction and literal control from user; independent of simulator Decimal/ledger implementation", "final_cash": str(cash), "return_pct": str((cash-10000)/100), "cash_after_buy": "7999", "fees": "2", "passed": True}
    write(out / "independent-arithmetic.json", independent)
    for src, dst in ((work / "demo.txt", out / "demo-synthetic.txt"), (work / "normal.trace.json", out / "demo-synthetic.trace.json"), (work / "real_source.trace.json", out / "real-source-blocked.trace.json")):
        shutil.copyfile(src, dst)
    real_text = subprocess.run([sys.executable, str(ROOT / "scripts/simulate_scenario.py"), "--case", "real-source"], cwd=ROOT, capture_output=True, encoding="utf-8", timeout=10)
    assert real_text.returncode == 0
    (out / "real-source-blocked.txt").write_text(real_text.stdout, encoding="utf-8")
    before = json.loads((out / "before.json").read_text(encoding="utf-8"))["protected_sha256"]
    after = {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in before}
    normalized = dict(after)
    migrations = {
        "src/financial_assistant/user_path.py": ("Искусственный сценарий запускается отдельно; этот финансовый ответ не разрешает торговлю.", "Условное торговое моделирование пока не реализовано."),
        "tests/test_user_path.py": ('"Искусственный сценарий запускается отдельно", "не разрешает торговлю"', '"моделирование пока не реализовано"')}
    for name,(new,old) in migrations.items():
        data=(ROOT/name).read_bytes(); candidate=data.replace(new.encode(),old.encode())
        normalized[name]=hashlib.sha256(candidate).hexdigest()
    assert normalized == before, "Unexpected change to existing implementation/fixtures"
    write(out / "report.json", {"unit_tests": {"run": tests.testsRun, "successful": tests.wasSuccessful()}, "cli": outcomes, "regressions": regressions,
        "independent_arithmetic": independent, "frozen_rule_sha256": frozen["fixture_sha256"], "protected_sha256": after,
        "unchanged_existing_files": [n for n in before if before[n] == after[n]], "intentional_existing_changes": list(migrations),
        "only_declared_footer_and_test_changed": normalized == before, "models_started": False, "model_calls": 0,
        "scope": "Synthetic code/time/arithmetic checks only. Not market returns, model quality, or strategy superiority."})
    print(json.dumps({"unit_tests": tests.testsRun, "cli_passed": len(outcomes), "regressions_passed": len(regressions), "synthetic_final_cash": str(cash), "real_source": "blocked/publication_unknown", "existing_changes": list(migrations), "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
