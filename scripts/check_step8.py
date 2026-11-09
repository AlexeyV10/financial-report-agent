"""Record real CLI behavior and unit checks without copying PDF pages/hits."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.user_path import UserQuery, run_user_query


def main():
    directory = ROOT / "evaluation/step8_2026-11-09"
    directory.mkdir(parents=True, exist_ok=True)
    temp = ROOT / "tmp/user-cli-tests"
    temp.mkdir(parents=True, exist_ok=True)
    bad_pdf, bad_db, bad_registry = temp / "synthetic-altered.pdf", temp / "synthetic-corrupt.sqlite", temp / "invalid-registry.json"
    bad_pdf.write_bytes(b"Synthetic bytes to test wrong version, not an issuer PDF")
    bad_db.write_bytes(b"Synthetic invalid database")
    bad_registry.write_text("{}", encoding="utf-8")
    data_path = ROOT / "data/examples/reference_bundle.json"
    before = hashlib.sha256(data_path.read_bytes()).hexdigest()
    cases = [
        ("default_live", [], 0, "answered", ["+67 385 млн руб.", "+15,30%", "Столбец 2023", "Столбец 2024"], []),
        ("manual_explicit_without_pdf", ["--source", "manual", "--pdf", "tmp/nonexistent.pdf", "--db", "tmp/nonexistent.sqlite"], 0, "answered", ["прежний ручной реестр", "не выполняются", "+15,30%"], []),
        ("unknown_company", ["--company", "Сбер"], 1, "clarification", ["Уточните запрос", "Сбер"], ["15,30%"]),
        ("ambiguous_company", ["--company", "ФосАгро или Сбер"], 1, "clarification", ["Выберите одну компанию"], ["15,30%"]),
        ("wrong_metric", ["--metric", "прибыль"], 1, "clarification", ["другого показателя"], ["15,30%"]),
        ("wrong_year", ["--year", "2025"], 1, "clarification", ["Другой период"], ["15,30%"]),
        ("partial_year", ["--year", "9 месяцев 2024"], 1, "clarification", ["девять месяцев"], ["15,30%"]),
        ("wrong_standard", ["--standard", "РСБУ"], 1, "clarification", ["другого источника"], ["15,30%"]),
        ("historical_live", ["--mode", "historical", "--as-of", "2025-02-14T10:00:00+03:00"], 0, "missing", ["исторический анализ", "Не подтверждено", "Ответ с числом не сформирован"], ["15,30%", "Подстановка:"]),
        ("historical_manual", ["--source", "manual", "--mode", "historical", "--as-of", "2025-02-14T10:00:00+03:00"], 0, "missing", ["Не подтверждено"], ["15,30%", "Подстановка:"]),
        ("as_of_not_ignored", ["--as-of", "2025-02-14T10:00:00+03:00"], 1, "clarification", ["не будет игнорировать дату"], ["15,30%"]),
        ("missing_as_of", ["--mode", "historical"], 1, "clarification", ["Момент: не указан", "укажите --as-of"], ["15,30%"]),
        ("missing_pdf", ["--pdf", "tmp/nonexistent.pdf"], 2, "error", ["Техническая ошибка", "PDF не найден"], ["15,30%", "прежний ручной реестр фактов; текущая"]),
        ("changed_pdf", ["--pdf", str(bad_pdf)], 2, "error", ["Хеш PDF отличается"], ["15,30%"]),
        ("missing_index", ["--db", "tmp/nonexistent.sqlite"], 2, "error", ["индекс не найден"], ["15,30%"]),
        ("corrupt_index", ["--db", str(bad_db)], 2, "error", ["Индекс повреждён"], ["15,30%"]),
        ("too_few_hits", ["--results", "1"], 0, "missing", ["нет обоих нужных доказательств"], ["15,30%", "Подстановка:"]),
        ("invalid_results", ["--results", "0"], 2, "error", ["Число результатов"], ["15,30%"]),
        ("invalid_registry", ["--bundle", str(bad_registry)], 2, "error", ["не прошёл проверку"], ["15,30%"]),
        ("save_report", ["--save", "output/user-answer.txt"], 0, "answered", ["+15,30%"], []),
        ("protect_registry_on_save", ["--save", str(data_path)], 2, "error", ["файл .txt"], ["15,30%"]),
        ("protect_pdf_on_save", ["--save", str(ROOT / "tmp/pdfs/phosagro-2024-ru.pdf")], 2, "error", ["файл .txt"], ["15,30%"]),
        ("bad_arguments", ["--question", "произвольный вопрос"], 2, "error", ["Сценарий не запущен"], ["15,30%", "ФосАгро"]),
    ]
    runs = []
    demo = None
    for name, args, code, status, required, forbidden in cases:
        p = subprocess.run([sys.executable, "scripts/assistant.py", *args], cwd=ROOT, capture_output=True, timeout=30)
        text = p.stdout.decode("utf-8").replace("\r\n", "\n")
        if p.returncode != code or not all(s in text for s in required) or any(s in text for s in forbidden):
            raise RuntimeError(name + ": " + text + p.stderr.decode("utf-8", errors="replace"))
        if name == "default_live":
            demo = text
            assert text.count("https://ar2024.phosagro.ru/pdf/ar/ru/additional-information_financial-statements.pdf#page=4") == 2
            assert "phosagro-revenue" not in text
        if name == "save_report":
            assert (ROOT / "output/user-answer.txt").read_text(encoding="utf-8") == text
        runs.append({"case": name, "expected_status": status, "exit_code": code,
                     "required_meaning_present": True, "forbidden_numeric_or_fallback_text_absent": True, "passed": True})
    (directory / "demo-answer.txt").write_text(demo, encoding="utf-8")
    bundle = json.loads(data_path.read_text(encoding="utf-8"))
    live = run_user_query(UserQuery(), bundle, ROOT / "tmp/pdfs/phosagro-2024-ru.pdf", ROOT / "tmp/retrieval/document.sqlite")
    ranks = [x["rank"] for x in live["financial_result"]["retrieval_resolution"]["used_hits"]]
    unit = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, capture_output=True, timeout=60)
    log = (unit.stdout + unit.stderr).decode("utf-8", errors="replace")
    (directory / "unit-tests.txt").write_text(log, encoding="utf-8")
    if unit.returncode:
        raise RuntimeError("Unit tests failed; see step8 log")
    count = int(re.search(r"Ran (\d+) tests", log).group(1))
    assert hashlib.sha256(data_path.read_bytes()).hexdigest() == before
    previous = json.loads((ROOT / "evaluation/step7_2026-11-09/report.json").read_text(encoding="utf-8"))
    protected = ["src/financial_assistant/contracts.py", "src/financial_assistant/finance.py", "src/financial_assistant/retrieval.py", "data/examples/reference_bundle.json"]
    same = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == previous["sha256"][p] for p in protected}
    assert all(same.values())
    files = protected + ["src/financial_assistant/user_path.py", "scripts/assistant.py", "scripts/check_step8.py", "tests/test_user_path.py"]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "unit_tests_passed": count, "cli_cases": runs, "used_search_ranks": ranks,
              "protected_files_unchanged_from_step7": same,
              "sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files},
              "limits": "one bounded scenario and public deterministic checks; not a natural-language model or agent-quality evaluation"}
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"unit_tests_passed": count, "cli_passed": len(runs), "used_search_ranks": ranks, "protected_files_unchanged": all(same.values())}))


if __name__ == "__main__":
    main()
