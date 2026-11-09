"""Local CLI. All extracted text/index/output stays below workspace tmp/."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.contracts import ContractError
from financial_assistant.retrieval import RetrievalError, build_index, manual_export, search_index, source_hash


def private_path(raw):
    path = Path(raw).resolve()
    if not path.is_relative_to((ROOT / "tmp").resolve()):
        raise RetrievalError("private_path_required", "Source text, index and outputs must stay inside workspace tmp/")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["index", "search"])
    parser.add_argument("--bundle", type=Path, default=ROOT / "data/examples/reference_bundle.json")
    parser.add_argument("--pdf", type=Path, default=ROOT / "tmp/pdfs/phosagro-2024-ru.pdf")
    parser.add_argument("--db", default=str(ROOT / "tmp/retrieval/document.sqlite"))
    parser.add_argument("--pdf-python", help="Interpreter with pdfplumber 0.11.9 installed")
    parser.add_argument("--manual", action="store_true", help="Explicit fallback, never automatic")
    parser.add_argument("--query", default="")
    parser.add_argument("--entity", default="phosagro_group")
    parser.add_argument("--version")
    parser.add_argument("--period")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--mode", default="document_snapshot")
    parser.add_argument("--as-of")
    parser.add_argument("--output", help="Optional JSON below tmp/; contains source excerpts")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        db = private_path(args.db)
        out = private_path(args.output) if args.output else None
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        if args.action == "index":
            source_hash(args.pdf, bundle["document"])
            if db.exists():
                raise RetrievalError("index_exists", "Choose a new --db path; previous index is not overwritten")
            if args.manual:
                export = manual_export(bundle)
            else:
                worker_output = private_path(str(db) + ".extraction.json")
                proc = subprocess.run([args.pdf_python or sys.executable, str(ROOT / "scripts/extract_pdf.py"), str(args.pdf), str(worker_output)], capture_output=True, timeout=90)
                if proc.returncode:
                    raise RetrievalError("extractor_failed", "PDF worker failed; check pdfplumber in --pdf-python. No automatic manual fallback.")
                export = json.loads(worker_output.read_text(encoding="utf-8"))
            result = build_index(db, args.pdf, bundle, export)
        else:
            result = search_index(db, args.pdf, bundle, args.query, args.entity, args.version, args.period, args.top_k, args.mode, args.as_of)
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RetrievalError, ContractError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "error", "reason_code": getattr(exc, "code", "invalid_input_or_io"), "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
