"""Один ограниченный сценарий: вопрос → локальный поиск → проверенные факты → ответ."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.user_path import UserQuery, input_issue, response, run_user_query, technical_response


class ArgumentIssue(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentIssue(message)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = Parser(description=__doc__, epilog="Без параметров: группа ФосАгро, МСФО, выручка 2024 к 2023, анализ выбранной версии и локальный поиск. Произвольный русский вопрос не разбирается.")
    for key, default, help_text in (
        ("company", "ФосАгро", "компания; сейчас только ФосАгро"),
        ("scope", "группа", "границы отчётности: группа"),
        ("standard", "МСФО", "стандарт: МСФО / IFRS"),
        ("metric", "выручка", "показатель: выручка"),
        ("year", "2024", "текущий полный год"),
        ("compare", "2023", "предыдущий полный год"),
        ("mode", "snapshot", "snapshot — выбранная версия; historical — на указанный момент"),
        ("source", "search", "search — локальный поиск; manual — явный ручной реестр")):
        parser.add_argument("--" + key, default=default, help=help_text)
    parser.add_argument("--as-of", help="исторический момент с часовым поясом")
    parser.add_argument("--results", type=int, default=5, help="число результатов поиска, 1…10")
    parser.add_argument("--pdf", type=Path, default=ROOT / "tmp/pdfs/phosagro-2024-ru.pdf", help="локальная копия выбранного PDF")
    parser.add_argument("--db", type=Path, default=ROOT / "tmp/retrieval/document.sqlite", help="локальный индекс выбранного PDF")
    parser.add_argument("--bundle", type=Path, default=ROOT / "data/examples/reference_bundle.json", help="реестр выбранного сценария")
    parser.add_argument("--save", type=Path, help="сохранить ответ в .txt под output/ или tmp/")
    q = UserQuery()
    try:
        args = parser.parse_args(argv)
        q = UserQuery(**{key: getattr(args, key) for key in UserQuery.__dataclass_fields__})
        issue = input_issue(q)
        if issue:
            view = response(q, "clarification", *issue)
        else:
            try:
                bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
                view = run_user_query(q, bundle, args.pdf, args.db, args.results)
            except FileNotFoundError:
                view = technical_response(q, "registry_missing")
            except (OSError, ValueError, UnicodeError):
                view = technical_response(q, "registry_invalid")
        if args.save:
            path = args.save.resolve()
            if path.suffix.lower() != ".txt" or not any(path.is_relative_to((ROOT / d).resolve()) for d in ("output", "tmp")):
                view = technical_response(q, "save_failed")
            else:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(view["text"], encoding="utf-8")
                except OSError:
                    view = technical_response(q, "save_failed")
        print(view["text"], end="")
        return 2 if view["status"] == "error" else 1 if view["status"] == "clarification" else 0
    except ArgumentIssue:
        print("Ошибка параметров запуска. Посмотрите python scripts/assistant.py --help. Сценарий не запущен.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
