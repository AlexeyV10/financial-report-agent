"""Deterministic financial operation by explicit IDs, optionally after live search."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.contracts import ContractError
from financial_assistant.finance import calculate_metric, calculate_from_retrieval, tool_request, validate_financial_result
from financial_assistant.retrieval import RetrievalError, search_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["calculate", "from-search"])
    parser.add_argument("--previous-fact", required=True)
    parser.add_argument("--current-fact", required=True)
    parser.add_argument("--operation", default="annual_growth_v1")
    parser.add_argument("--mode", default="document_snapshot")
    parser.add_argument("--as-of")
    parser.add_argument("--bundle", type=Path, default=ROOT / "data/examples/reference_bundle.json")
    parser.add_argument("--pdf", type=Path, default=ROOT / "tmp/pdfs/phosagro-2024-ru.pdf")
    parser.add_argument("--db", type=Path, default=ROOT / "tmp/retrieval/document.sqlite")
    parser.add_argument("--query", default="выручка 2024 2023")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if args.output and not any(args.output.resolve().is_relative_to((ROOT / d).resolve()) for d in ("output", "tmp")):
            raise ContractError("Output must stay in workspace output/ or tmp/")
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        request = tool_request(args.previous_fact, args.current_fact, args.operation, args.mode, args.as_of)
        retrieval = None
        if args.action == "from-search":
            retrieval = search_index(args.db, args.pdf, bundle, args.query,
                                     entity_id=bundle["request"]["entity_id"],
                                     version_id=bundle["document"]["version_id"], top_k=args.top_k,
                                     mode=args.mode, as_of=args.as_of)
            result = calculate_from_retrieval(bundle, request, retrieval)
        else:
            result = calculate_metric(bundle, request)
        validate_financial_result(result, bundle, request, retrieval)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, RetrievalError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "reason_code": getattr(exc, "code", "invalid_financial_input"), "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
