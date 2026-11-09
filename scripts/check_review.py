"""Capture fresh local checks without overwriting the original stage-1 logs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/solo_workflow_2026-11-09"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = json.loads((ROOT / "evaluation/stage1_check.json").read_text(encoding="utf-8"))
    comparison = {p: {"previous": h, "current": sha(ROOT / p), "matches": sha(ROOT / p) == h}
                  for p, h in before["inputs_sha256"].items()}
    commands = [
        [sys.executable, "scripts/check_stage1.py", "--write-report", str(OUT / "stage1_check.json")],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    ]
    results = []
    for args in commands:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        results.append(result)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
    unit_log = results[1].stdout + results[1].stderr
    (OUT / "unit-tests.txt").write_text(unit_log, encoding="utf-8")
    matches = re.findall(r"Ran (\d+) tests?", unit_log)
    if not matches or not unit_log.rstrip().endswith("OK"):
        raise RuntimeError("Could not establish a successful unittest result")
    examples = json.loads((OUT / "stage1_check.json").read_text(encoding="utf-8"))
    reference = json.loads((ROOT / "data/examples/reference_bundle.json").read_text(encoding="utf-8"))
    sources = {}
    for rel in ("tmp/pdfs/phosagro-2024-ru.pdf", "tmp/pdfs/phosagro-2024-ru-recheck-2026-11-09.pdf"):
        path = ROOT / rel
        if path.exists():
            observed = sha(path)
            valid = observed == reference["document"]["sha256"] and path.stat().st_size == reference["document"]["byte_length"]
            if not valid:
                raise RuntimeError("Source version mismatch: " + rel)
            sources[rel] = {"sha256": observed, "bytes": path.stat().st_size, "matches_reference": valid}
        else:
            sources[rel] = {"status": "not_present_source_truth_not_rechecked"}
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "historical_report_checked_at": before["checked_at"], "historical_hash_comparison": comparison,
              "expected_changed_files": ["src/financial_assistant/contracts.py", "tests/test_contracts.py"],
              "contract_examples_passed": examples["passed"], "contract_examples_total": examples["total"],
              "unit_tests_passed": int(matches[-1]),
              "commands_exit_codes": [x.returncode for x in results], "source_checks": sources,
              "source_visual_review": "separately documented in docs/acceptance_recheck.md; not performed by this script",
              "workflow": "single_user_with_codex",
              "fact_verification_provenance": "assistant_checked_not_a_claim_of_user_review",
              "quality_metrics_measured": False}
    (OUT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Fresh checks: {examples['passed']}/{examples['total']} examples; {report['unit_tests_passed']} unit tests; source hashes recorded")
    print("Changed since original report: " + ", ".join(p for p, v in comparison.items() if not v["matches"]))


if __name__ == "__main__":
    main()
