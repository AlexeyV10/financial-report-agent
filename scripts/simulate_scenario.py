"""Один детерминированный искусственный сценарий либо отдельная проверка настоящего источника."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from assistant import ArgumentIssue, Parser
from agent_assistant import output_path
from financial_assistant.simulation import LABEL, ScenarioError, assess_real_source, fingerprint, simulate
from financial_assistant.simulation_view import render_real_check, render_scenario


def read(path):
    if path.stat().st_size > 262144:
        raise ValueError("input_too_large")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = Parser(description=__doc__)
    parser.add_argument("--case", choices=("synthetic", "real-source"), default="synthetic")
    parser.add_argument("--fixture", type=Path, help="отдельный искусственный JSON; не файл настоящего отчёта")
    parser.add_argument("--as-of", help="момент проверки настоящего источника, с часовым поясом")
    parser.add_argument("--save", type=Path, help="ответ .txt только под output/ или tmp/")
    parser.add_argument("--trace", type=Path, help="trace .json только под output/ или tmp/")
    tick, started = time.monotonic(), datetime.now(timezone.utc).isoformat()
    case_label = LABEL
    try:
        args = parser.parse_args(argv)
        if args.case == "real-source":
            case_label = "ПРОВЕРКА НАСТОЯЩЕГО ИСТОЧНИКА — ТОРГОВЛИ НЕТ"
        targets = [(output_path(p, ext), key) for p, ext, key in ((args.save, ".txt", "text"), (args.trace, ".json", "trace")) if p]
        if args.case == "synthetic":
            if args.as_of is not None:
                raise ValueError("as_of_is_not_a_synthetic_override")
            data = read(args.fixture or ROOT / "data/synthetic/scenario_v1.json")
            r = simulate(data); text = render_scenario(data, r)
        else:
            if args.fixture is not None:
                raise ValueError("no_synthetic_fixture_for_real_source")
            data = read(ROOT / "data/examples/reference_bundle.json")
            stamp = args.as_of if args.as_of is not None else "2025-06-04T19:30:00+03:00"
            r = assess_real_source(data, stamp); text = render_real_check(data, stamp, r)
        trace = {"run_id": str(uuid.uuid4()), "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
                 "elapsed_s": time.monotonic() - tick, "case": args.case, "request_sha256": fingerprint(data),
                 "versions": {"scenario_schema": "0.1", "financial_contract": "0.1", "growth_formula": "annual_growth_v1",
                              "code_sha256": {name: hashlib.sha256((ROOT / "src/financial_assistant" / name).read_bytes()).hexdigest() for name in ("simulation.py", "simulation_view.py", "contracts.py", "finance.py")}},
                 "model_calls": 0, "result": r}
        for path, key in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text if key == "text" else json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(text, end="")
        return 0 if r["status"] in {"completed", "blocked"} else 2
    except (ArgumentIssue, OSError, ValueError, TypeError, KeyError, ScenarioError):
        print(case_label + "\nТехническая ошибка параметров, входного JSON, проверки результата или сохранения.\nПосмотрите --help. Реальный и искусственный наборы не подменяются. Сделки не сформированы.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
