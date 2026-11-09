"""Optional pdfplumber worker. Writes source text only to the chosen local file."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to((root / "tmp").resolve()):
        raise ValueError("Extracted source text must stay below workspace tmp/")
    import pdfplumber
    import pdfminer
    if args.pdf.stat().st_size > 10_000_000:
        raise ValueError("This prototype supports PDFs up to 10 MB")
    fingerprint = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    fragments = []
    with pdfplumber.open(args.pdf) as pdf:
        if len(pdf.pages) > 100:
            raise ValueError("This prototype supports up to 100 pages")
        for number, page in enumerate(pdf.pages, 1):
            for side, box in (("left_half_of_spread", (0, 0, page.width / 2, page.height)),
                              ("right_half_of_spread", (page.width / 2, 0, page.width, page.height))):
                body = page.crop(box).extract_text(x_tolerance=2, y_tolerance=3) or ""
                if body.strip():
                    fragments.append({"pdf_page": number, "page_region": side,
                                      "bbox_pdf_points_top_origin": list(box), "text": body})
            page.close()
        count = len(pdf.pages)
    payload = {"sha256": fingerprint, "pdf_pages": count, "mode": "pdfplumber_split_spread_v1",
               "python": platform.python_version(), "pdfplumber": pdfplumber.__version__,
               "pdfminer_six": pdfminer.__version__, "fragments": fragments}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pages": count, "fragments": len(fragments), "sha256": fingerprint}))


if __name__ == "__main__":
    main()
