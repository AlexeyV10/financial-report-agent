"""Record smoke checks on the local real index, without publishing source text."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.retrieval import search_index


def main():
    out = ROOT / "evaluation/step6_2026-11-09"
    out.mkdir(parents=True, exist_ok=True)
    b = json.loads((ROOT / "data/examples/reference_bundle.json").read_text(encoding="utf-8"))
    db, pdf = ROOT / "tmp/retrieval/document.sqlite", ROOT / "tmp/pdfs/phosagro-2024-ru.pdf"
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    (out / "unit-tests.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    if tests.returncode:
        raise RuntimeError("Unit checks failed; inspect evaluation log")
    rows = []
    cases = [("real_keywords", "выручка 2024 2023", {"period": "2024"}),
             ("russian_variant", "ВЫРУЧКИ", {"period": "2023"}),
             ("wrong_entity", "выручка", {"entity_id": "another_group"}),
             ("missing_period", "выручка", {"period": "2025"}),
             ("unknown_publication", "выручка", {"mode": "historical_as_of", "as_of": "2025-02-14T10:00:00+03:00"})]
    for name, query, options in cases:
        result = search_index(db, pdf, b, query, **options)
        target_ranks = [i for i, x in enumerate(result["results"], 1) if x["pdf_page"] == 4 and x["page_region"] == "left_half_of_spread"]
        if name in {"real_keywords", "russian_variant"}:
            assert target_ranks, name
        else:
            assert not result["results"], name
        rows.append({"case": name, "status": result["status"], "reason_code": result["reason_code"],
                     "target_page_rank": target_ranks[0] if target_ranks else None,
                     "returned_pages": [x["pdf_page"] for x in result["results"]], "passed": True})
    with closing(sqlite3.connect(db)) as c:
        meta = json.loads(c.execute("SELECT payload FROM metadata").fetchone()[0])
        fragments = c.execute("SELECT count(*) FROM fragments").fetchone()[0]
        text = c.execute("SELECT body FROM fragments WHERE page=4 AND region='left_half_of_spread'").fetchone()[0]
    target = next(line for line in text.splitlines() if line.startswith("Выручка "))
    assert "507,689" in target and "440,304" in target
    assert "Консолидированный отчет о прибыли" in text and "2024 2023" in text
    assert "Консолидированный отчет о финансовом положении" not in text
    paths = ["src/financial_assistant/retrieval.py", "scripts/search_documents.py", "scripts/extract_pdf.py", "scripts/check_step6.py", "tests/test_retrieval.py", "src/financial_assistant/contracts.py", "data/examples/reference_bundle.json", "requirements-pdf.txt"]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "sqlite": sqlite3.sqlite_version, "extraction": meta["extractor"], "indexed_fragments": fragments,
              "reference_page_check": {"pdf_page": 4, "region": "left_half_of_spread", "title_units_years_and_values_preserved": True,
                                       "right_balance_not_merged": True, "visual_check": "assistant compared local PNG with extracted text; see docs/retrieval.md"},
              "smoke_cases": rows, "unit_exit_code": tests.returncode,
              "sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
              "limits": "public smoke cases, no held-out evaluation or assistant-quality metrics; no new verified financial facts"}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fragments": fragments, "cases": rows, "unit_exit_code": tests.returncode}, ensure_ascii=False))


if __name__ == "__main__":
    main()
