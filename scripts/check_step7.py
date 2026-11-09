"""Fresh financial tool/CLI checks; report metadata, not full source excerpts."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT / "evaluation/step7_2026-11-09"
    directory.mkdir(parents=True, exist_ok=True)
    bundle_path = ROOT / "data/examples/reference_bundle.json"
    before = bundle_path.read_bytes()
    b = json.loads(before)
    temp = ROOT / "tmp/financial-cli-tests"
    temp.mkdir(parents=True, exist_ok=True)
    ids = ["--previous-fact", "phosagro-revenue-2023", "--current-fact", "phosagro-revenue-2024"]
    cases = [("direct_real", "real_manual_reference", ["calculate", *ids], 0, "answered", "ok"),
             ("live_search_real", "real_manual_reference", ["from-search", *ids], 0, "answered", "ok"),
             ("top_one_does_not_cover_evidence", "real_search_restricted", ["from-search", *ids, "--top-k", "1"], 0, "missing", "verified_evidence_not_retrieved"),
             ("historical_unknown_direct", "real_snapshot_historical_request", ["calculate", *ids, "--mode", "historical_as_of", "--as-of", "2025-02-14T10:00:00+03:00"], 0, "missing", "publication_unknown"),
             ("historical_unknown_search", "real_snapshot_historical_request", ["from-search", *ids, "--mode", "historical_as_of", "--as-of", "2025-02-14T10:00:00+03:00"], 0, "missing", "publication_unknown"),
             ("unknown_id", "invalid_tool_input", ["calculate", "--previous-fact", "unknown", "--current-fact", "phosagro-revenue-2024"], 2, "error", "invalid_financial_input"),
             ("wrong_order", "invalid_period_binding", ["calculate", "--previous-fact", "phosagro-revenue-2024", "--current-fact", "phosagro-revenue-2023"], 0, "conflict", "input_fact_context_mismatch")]
    for name, previous, current, status, reason in (("twenty_percent", "100", "120", "answered", "ok"),
            ("zero_base", "0", "120", "unsupported", "nonpositive_base"),
            ("negative_base", "-100", "120", "unsupported", "nonpositive_base"),
            ("missing_value", "100", None, "missing", "value_missing")):
        synthetic = deepcopy(b)
        fingerprint = hashlib.sha256(b"synthetic-fixture-not-a-financial-report").hexdigest()
        doc = synthetic["document"]
        doc.update(entity_id="synthetic_group", entity_name="Синтетическая тестовая группа, не эмитент",
                   document_id="synthetic-fixture", document_type="synthetic_fixture", sha256=fingerprint,
                   version_id="sha256:" + fingerprint, document_url="https://example.invalid/synthetic.pdf",
                   source_page_url="https://example.invalid/synthetic")
        doc["related_release"]["url"] = "https://example.invalid/synthetic-release"
        synthetic["request"].update(entity_id="synthetic_group", question="Синтетический тест, не сведения об эмитенте")
        for i, value in enumerate((previous, current)):
            fact, ev = synthetic["facts"][i], synthetic["evidence"][i]
            fact.update(value=value, entity_id="synthetic_group", version_id=doc["version_id"])
            raw = None if value is None else ("(" + value[1:] + ")" if value.startswith("-") else value)
            ev.update(raw_value=raw, document_id=doc["document_id"], version_id=doc["version_id"], document_sha256=fingerprint)
        path = temp / (name + ".json")
        path.write_text(json.dumps(synthetic, ensure_ascii=False, indent=2), encoding="utf-8")
        cases.append((name, "synthetic_not_issuer_data", ["calculate", *ids, "--bundle", str(path)], 0, status, reason))
    runs = []
    for name, kind, args, code, status, reason in cases:
        p = subprocess.run([sys.executable, "scripts/calculate_financial.py", *args], cwd=ROOT, capture_output=True, timeout=30)
        result = json.loads(p.stdout.decode("utf-8"))
        if (p.returncode, result["status"], result["reason_code"]) != (code, status, reason):
            raise RuntimeError(name + ": " + p.stdout.decode("utf-8"))
        calc = (result.get("answer") or {}).get("calculation")
        if name in {"direct_real", "live_search_real"}:
            assert calc["growth_pct_display"] == "15.30" and calc["delta"] == "67385"
        if name == "twenty_percent":
            assert calc["growth_pct_display"] == "20.00"
        if status != "answered":
            assert calc is None
        ranks = [x["rank"] for x in (result.get("retrieval_resolution") or {}).get("used_hits", [])]
        runs.append({"case": name, "kind": kind, "exit_code": p.returncode, "status": status,
                     "reason_code": reason, "growth_pct_display": calc["growth_pct_display"] if calc else None,
                     "used_search_ranks": ranks, "passed": True})
    unit = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, capture_output=True, timeout=60)
    log = (unit.stdout + unit.stderr).decode("utf-8", errors="replace")
    (directory / "unit-tests.txt").write_text(log, encoding="utf-8")
    if unit.returncode:
        raise RuntimeError("Unit tests failed; see log")
    count = int(re.search(r"Ran (\d+) tests", log).group(1))
    assert bundle_path.read_bytes() == before
    files = ["src/financial_assistant/contracts.py", "src/financial_assistant/finance.py", "src/financial_assistant/retrieval.py",
             "scripts/calculate_financial.py", "scripts/check_step7.py", "tests/test_finance.py", "data/examples/reference_bundle.json"]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "unit_tests_passed": count, "cli_cases": runs, "financial_bundle_unchanged": True,
              "reference_calculator": "contracts.answer reused without a second arithmetic implementation",
              "limits": "open deterministic checks; not agent/LLM quality metrics; facts remain manually verified",
              "sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files}}
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"unit_tests_passed": count, "cli_passed": len(runs), "used_search_ranks": runs[1]["used_search_ranks"]}))


if __name__ == "__main__":
    main()
