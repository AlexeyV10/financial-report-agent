"""Reproducible open checks; --with-local-llm explicitly enables three local demonstrations."""
from dataclasses import replace
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.agent import Limits, MockAdapter, run_agent
from financial_assistant.local_model import OllamaAdapter, local_json
from financial_assistant.user_path import UserQuery, run_user_query


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-local-llm", action="store_true")
    args = parser.parse_args()
    out, work = ROOT / "evaluation/step9_2026-11-09", ROOT / "tmp/step9-checks"
    out.mkdir(parents=True, exist_ok=True); work.mkdir(parents=True, exist_ok=True)
    b = json.loads((ROOT / "data/examples/reference_bundle.json").read_text(encoding="utf-8"))
    q, pdf, db = UserQuery(), ROOT / "tmp/pdfs/phosagro-2024-ru.pdf", ROOT / "tmp/retrieval/document.sqlite"
    changed, corrupt = work / "changed.pdf", work / "corrupt.sqlite"
    changed.write_bytes(b"Synthetic invalid PDF for source hash check")
    corrupt.write_bytes(b"Synthetic invalid SQLite")
    cases = [("normal", q, pdf, db, 5), ("top1", q, pdf, db, 1),
             ("historical", replace(q, mode="historical", as_of="2025-02-14T10:00:00+03:00"), pdf, db, 5),
             ("manual", replace(q, source="manual"), work / "absent.pdf", work / "absent.sqlite", 5),
             ("unknown_company", replace(q, company="Сбер"), pdf, db, 5),
             ("missing_pdf", q, work / "absent.pdf", db, 5), ("changed_pdf", q, changed, db, 5),
             ("missing_index", q, pdf, work / "absent.sqlite", 5), ("corrupt_index", q, pdf, corrupt, 5)]
    rows = []
    for name, query, source, index, k in cases:
        tick = time.monotonic(); baseline = run_user_query(query, b, source, index, k)
        b_time = time.monotonic() - tick
        run = run_agent(query, b, MockAdapter(), source, index, Limits(max_search_results=k))
        same = (baseline["status"], baseline["reason_code"], baseline["financial_result"]) == (run["user_response"]["status"], run["user_response"]["reason_code"], run["user_response"]["financial_result"])
        save(out / (name + ".mock.trace.json"), run["trace"])
        rows.append({"case": name, "baseline": {"status": baseline["status"], "reason": baseline["reason_code"], "elapsed_s": b_time},
                     "C_mock": {"status": run["status"], "financial_status": run["user_response"]["status"], "reason": run["user_response"]["reason_code"], "elapsed_s": run["trace"]["elapsed_s"], "decisions": len(run["trace"]["events"])},
                     "same_financial_outcome": same})
        assert same, name
        if name == "normal":
            (out / "baseline-answer.txt").write_text(baseline["text"], encoding="utf-8")
            (out / "mock-answer.txt").write_text(run["user_response"]["text"], encoding="utf-8")
    cli_cases = [
        ("normal", ["--adapter", "mock"], 0, "+15,30%"),
        ("adaptive_mock", ["--adapter", "mock", "--mock-first-results", "1"], 0, "6/6"),
        ("top1_refusal", ["--adapter", "mock", "--results", "1"], 0, "Ответ с числом не сформирован"),
        ("historical", ["--adapter", "mock", "--mode", "historical", "--as-of", "2025-02-14T10:00:00+03:00"], 0, "Исторический ответ"),
        ("manual", ["--adapter", "mock", "--source", "manual", "--pdf", str(work / "absent.pdf")], 0, "+15,30%"),
        ("clarification", ["--adapter", "mock", "--company", "Сбер"], 1, "Уточните запрос"),
        ("no_source", ["--adapter", "mock", "--pdf", str(work / "absent.pdf")], 2, "PDF не найден"),
        ("changed_source", ["--adapter", "mock", "--pdf", str(changed)], 2, "Хеш PDF отличается"),
        ("no_index", ["--adapter", "mock", "--db", str(work / "absent.sqlite")], 2, "индекс не найден"),
        ("bad_index", ["--adapter", "mock", "--db", str(corrupt)], 2, "Индекс повреждён"),
        ("budget", ["--adapter", "mock", "--max-calls", "1"], 3, "Исчерпан лимит"),
        ("invalid_limits", ["--adapter", "mock", "--max-calls", "0"], 2, "Техническая ошибка"),
        ("protect_registry", ["--adapter", "mock", "--trace", str(ROOT / "data/examples/reference_bundle.json")], 2, "Техническая ошибка"),
        ("protect_pdf", ["--adapter", "mock", "--save", str(pdf)], 2, "Техническая ошибка"),
        ("unknown_argument", ["--question", "arbitrary"], 2, "Техническая ошибка"),
        ("save", ["--adapter", "mock", "--trace", str(work / "saved.trace.json"), "--save", str(work / "saved.txt")], 0, "+15,30%"),
    ]
    cli = []
    for name, options, code, token in cli_cases:
        r = subprocess.run([sys.executable, str(ROOT / "scripts/agent_assistant.py"), *options], cwd=ROOT, capture_output=True, encoding="utf-8", timeout=35)
        passed = r.returncode == code and token.casefold() in r.stdout.casefold()
        cli.append({"case": name, "exit_code": r.returncode, "expected_exit_code": code, "passed": passed})
        assert passed, (name, r.returncode, r.stdout[-800:], r.stderr[-800:])
    assert (work / "saved.txt").is_file() and json.loads((work / "saved.trace.json").read_text(encoding="utf-8"))["status"] == "completed"
    with (out / "unit-tests.txt").open("w", encoding="utf-8") as log:
        tests = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT / "tests")))
    assert tests.wasSuccessful(), "Unit failures: see unit-tests.txt"
    live = []
    if args.with_local_llm:
        config = json.loads((ROOT / "data/config/local_model.json").read_text(encoding="utf-8"))
        adapter = OllamaAdapter(config["model"], config["model_digest"], config["server_version"])
        for name, query, source, index, k in cases[:3]:
            run = run_agent(query, b, adapter, source, index, Limits(max_search_results=k))
            save(out / (name + ".llm.trace.json"), run["trace"])
            (out / (name + ".llm-answer.txt")).write_text(run["user_response"]["text"], encoding="utf-8")
            baseline = run_user_query(query, b, source, index, k)
            live.append({"case": name, "status": run["status"], "financial_status": run["user_response"]["status"],
                         "reason": run["user_response"]["reason_code"], "decisions": len(run["trace"]["events"]),
                         "elapsed_s": run["trace"]["elapsed_s"], "usage": run["trace"]["usage"],
                         "same_financial_outcome": run["user_response"]["financial_result"] == baseline["financial_result"] and run["user_response"]["status"] == baseline["status"]})
        ps = local_json("/api/ps")
        save(out / "loaded-model.json", {"models": [{k: m.get(k) for k in ("name", "digest", "size", "size_vram", "context_length")} for m in ps.get("models", [])]})
    before = json.loads((out / "before.json").read_text(encoding="utf-8"))["protected_sha256"]
    after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in before}
    assert before == after, "Protected baseline/source changed"
    development = []
    for name in ("agent-llm-first-trace.json", "agent-llm-cold-retry-trace.json", "agent-llm-json-v2-trace.json", "agent-llm-dialogue-v3-trace.json", "agent-llm-dialogue-v4-trace.json"):
        path = ROOT / "output" / name
        if path.exists():
            r = json.loads(path.read_text(encoding="utf-8"))
            shutil.copyfile(path, out / ("development-" + name))
            development.append({"file": "development-" + name, "status": r["status"], "reason": r["stop_reason"], "usage": r["usage"], "elapsed_s": r["elapsed_s"], "prompt": r["versions"]["prompt"]})
    report = {"date": "2026-11-09", "unit_tests": {"run": tests.testsRun, "successful": tests.wasSuccessful()},
              "cli": cli, "paired_open_cases": rows, "local_llm_demonstrations": live,
              "development_runs_not_hidden": development, "protected_sha256": after, "protected_files_unchanged": before == after,
              "limits": Limits().__dict__, "scope": "Open deterministic controller tests and tiny local model demonstrations, NOT held-out model quality, superiority, business benefit or trading performance."}
    save(out / "report.json", report)
    print(json.dumps({"unit_tests": tests.testsRun, "cli_passed": sum(c["passed"] for c in cli), "paired_mock_cases": len(rows), "local_llm_runs": live, "protected_files_unchanged": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
