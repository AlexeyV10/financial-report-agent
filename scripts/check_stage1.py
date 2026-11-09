"""Offline contract demonstration; no LLM, retrieval, PDF parser or simulator."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.contracts import answer, validate_answer


def load_bundle():
    return json.loads((ROOT / "data/examples/reference_bundle.json").read_text(encoding="utf-8"))


def mutate(bundle, patches):
    result = deepcopy(bundle)
    for patch in patches:
        target = result
        for part in patch["path"][:-1]:
            target = target[part]
        target[patch["path"][-1]] = patch["value"]
    return result


def run():
    cases = json.loads((ROOT / "data/examples/cases.json").read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        inputs = mutate(load_bundle(), case["patches"])
        actual = answer(inputs)
        validate_answer(actual, inputs)
        expected = case["expected"]
        assert actual["status"] == expected["status"], case["case_id"]
        assert actual["reason_code"] == expected["reason_code"], case["case_id"]
        assert actual["scenario_gate"]["status"] == expected["scenario_status"], case["case_id"]
        if "delta" in expected:
            for field in ("delta", "growth_pct_display"):
                assert actual["calculation"][field] == expected[field], case["case_id"]
        else:
            assert actual["calculation"] is None and actual["claims"] == [], case["case_id"]
        rows.append({"case_id": case["case_id"], "kind": case["kind"], "passed": True,
                     "expected": expected, "actual": actual})
    paths = [ROOT / "src/financial_assistant/contracts.py", ROOT / "scripts/check_stage1.py",
             ROOT / "data/examples/reference_bundle.json", ROOT / "data/examples/cases.json",
             ROOT / "tests/test_contracts.py"]
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
            "scope": "4 public contract examples; not assistant quality metrics or a held-out benchmark",
            "inputs_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            "passed": len(rows), "total": len(cases), "cases": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args()
    report = run()
    print(f"{report['passed']}/{report['total']} contract examples passed")
    for row in report["cases"]:
        out = row["actual"]
        print(f"{row['case_id']}: {out['status']} / {out['reason_code']}; scenario={out['scenario_gate']['status']}")
    calc = report["cases"][0]["actual"]["calculation"]
    print(f"Revenue: 440304 -> 507689 million RUB; delta={calc['delta']}; growth={calc['growth_pct_display']}%")
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
