"""Один ограниченный контроллер: локальная LLM либо явно выбранный mock."""
from dataclasses import fields
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from assistant import ArgumentIssue, Parser
from financial_assistant.agent import Limits, MockAdapter, run_agent
from financial_assistant.local_model import OllamaAdapter
from financial_assistant.user_path import UserQuery, technical_response


def output_path(path, suffix):
    path = path.resolve()
    if path.suffix.lower() != suffix or not any(path.is_relative_to((ROOT / d).resolve()) for d in ("output", "tmp")):
        raise ValueError("invalid_output_path")
    return path


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = Parser(description=__doc__)
    for f in fields(UserQuery):
        parser.add_argument("--" + f.name.replace("_", "-"), default=f.default)
    parser.add_argument("--adapter", choices=("ollama", "mock"), default="ollama")
    parser.add_argument("--bundle", type=Path, default=ROOT / "data/examples/reference_bundle.json")
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/local_model.json")
    parser.add_argument("--pdf", type=Path, default=ROOT / "tmp/pdfs/phosagro-2024-ru.pdf")
    parser.add_argument("--db", type=Path, default=ROOT / "tmp/retrieval/document.sqlite")
    parser.add_argument("--max-calls", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--per-call-timeout", type=float, default=90)
    parser.add_argument("--results", type=int, default=5)
    parser.add_argument("--mock-first-results", type=int, default=5)
    parser.add_argument("--trace", type=Path, help="сохранить минимальный trace .json под output/ или tmp/")
    parser.add_argument("--save", type=Path, help="сохранить ответ .txt под output/ или tmp/")
    q = UserQuery()
    try:
        args = parser.parse_args(argv)
        q = UserQuery(**{f.name: getattr(args, f.name) for f in fields(UserQuery)})
        targets = [(output_path(p, ext), kind) for p, ext, kind in ((args.trace, ".json", "trace"), (args.save, ".txt", "text")) if p]
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        limits = Limits(max_calls=args.max_calls, timeout_s=args.timeout, per_call_s=args.per_call_timeout, max_search_results=args.results)
        limits.validate()
        if args.adapter == "mock":
            if not 1 <= args.mock_first_results <= 10:
                raise ValueError("invalid_mock_results")
            adapter = MockAdapter(args.mock_first_results)
        else:
            config = json.loads(args.config.read_text(encoding="utf-8"))
            adapter = OllamaAdapter(config["model"], config["model_digest"], config["server_version"])
        run = run_agent(q, bundle, adapter, args.pdf, args.db, limits)
        label = "C/mock — детерминированный имитатор, не языковая модель" if args.adapter == "mock" else "C/LLM — локальная модель выбирает разрешённые действия"
        text = label + "\n" + run["user_response"]["text"]
        text += f"\nКонтроллер: {run['status']}; причина: {run['reason_code']}; решений модели: {len(run['trace']['events'])}/{limits.max_calls}.\n"
        for path, kind in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(run["trace"], ensure_ascii=False, indent=2) + "\n" if kind == "trace" else text, encoding="utf-8")
        print(text, end="")
        return 0 if run["status"] in {"completed", "preflight_refusal"} else 1 if run["status"] == "clarification" else 3 if run["status"] in {"limit_exceeded", "timeout"} else 2
    except (ArgumentIssue, OSError, ValueError, KeyError, TypeError):
        print(technical_response(q, "registry_invalid")["text"], end="")
        print("Проверьте параметры --help, реестр/конфигурацию и допустимые пути сохранения. Модель/mock не заменяются автоматически.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
