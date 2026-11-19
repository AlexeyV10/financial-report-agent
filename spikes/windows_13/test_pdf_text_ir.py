"""Exercise PDF text, native offsets, rotation, crops and conservative reading order."""

from contextlib import closing
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from financial_assistant.office_extraction_common import ExtractionError
from financial_assistant.pdf_text_ir import extract_pdf_pages


def text(x, y, value, size=12):
    esc = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /F1 {size} Tf {x} {y} Td ({esc}) Tj ET\n"


def pdf(pages, *, labels=(), media="0 0 460 320"):
    label_entries = " ".join(f"{index} << /P ({label}) >>" for index, label in labels)
    decorations = f" /PageLabels << /Nums [{label_entries}] >>" if labels else ""
    kids = " ".join(f"{4 + 2 * index} 0 R" for index in range(len(pages)))
    objects = [
        f"<< /Type /Catalog /Pages 2 0 R{decorations} >>".encode("ascii"),
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} /MediaBox [{media}] >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, (rotation, crop, commands) in enumerate(pages):
        contents = commands.encode("ascii")
        crop_box = f" /CropBox [{crop}]" if crop else ""
        objects.append((
            f"<< /Type /Page /Parent 2 0 R /Rotate {rotation}{crop_box} "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * index} 0 R >>"
        ).encode("ascii"))
        objects.append(f"<< /Length {len(contents)} >>\nstream\n".encode("ascii") + contents + b"endstream")
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, definition in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode("ascii") + definition + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    return bytes(data + f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))


class PdfTextIrTests(unittest.TestCase):
    def test_intrinsic_rotation_uses_effective_crop_and_native_character_offsets(self):
        commands = text(42, 190, "Visible text") + text(4, 12, "Outside the crop")
        data = pdf([(r, "20 30 380 270", commands) for r in (0, 90, 180, 270)],
                   labels=((0, "First-i"),))
        with patch.object(pdfium.PdfPage, "render", side_effect=AssertionError("unexpected rendering")):
            extracted = extract_pdf_pages(data)
        self.assertEqual(extracted["pages"][0]["pdf_page_label"], "First-i")
        with pdfium.PdfDocument(data) as raw_document:
            for number, page in enumerate(extracted["pages"]):
                with self.subTest(rotation=page["rotation"]):
                    self.assertEqual(page["bounds"], [20, 30, 380, 270])
                    self.assertEqual(page["page_index"], number)
                    self.assertEqual(page["rotation"], number * 90)
                    self.assertEqual(page["text_status"], "digital")
                    self.assertIsNone(page["printed_page"])
                    line, = page["lines"]
                    span, = line["spans"]
                    self.assertEqual(span["text"], "Visible text")
                    self.assertEqual(line["bbox"], span["bbox"])
                    with closing(raw_document[number]) as native, closing(native.get_textpage()) as characters:
                        start, end = span["char_start"], span["char_end"]
                        self.assertEqual(characters.get_text_range(start, end - start), span["text"])
                        backing = [characters.get_charbox(index) for index in range(start, end)
                                   if characters.get_text_range(index, 1).strip()]
                        expected_native = [min(box[0] for box in backing), min(box[1] for box in backing),
                                           max(box[2] for box in backing), max(box[3] for box in backing)]
                    self.assertEqual(span["pdf_box"], expected_native)
                    l, b, r, t = expected_native
                    expected_display = (
                        [l - 20, 270 - t, r - 20, 270 - b],
                        [b - 30, l - 20, t - 30, r - 20],
                        [380 - r, b - 30, 380 - l, t - 30],
                        [270 - t, 380 - r, 270 - b, 380 - l],
                    )
                    self.assertEqual(span["bbox"], expected_display[number])
                    self.assertEqual([page["width"], page["height"]],
                                     [360, 240] if number % 2 == 0 else [240, 360])
        self.assertEqual(set(extracted), {"pages", "provenance", "notes"})
        for info in extracted["provenance"].values():
            self.assertRegex(info["sha256"], r"^[a-f0-9]{64}$")

    def test_horizontal_prose_columns_are_read_before_next_column_and_table_keeps_baseline(self):
        commands = ""
        left = ["Left opening statement", "Left continued passage", "Left concluding passage"]
        right = ["Right opening statement", "Right continued passage", "Right concluding passage"]
        for y, a, b in zip((270, 250, 230), left, right, strict=True):
            commands += text(30, y, a) + text(266, y, b)
        commands += text(30, 155, "Metric") + text(198, 155, "2025") + text(360, 155, "2024")
        commands += text(30, 135, "Revenue") + text(198, 135, "(120,75)") + text(360, 135, "100")
        page, = extract_pdf_pages(pdf([(0, None, commands)]))["pages"]
        self.assertEqual(page["reading_order"], "columns")
        self.assertEqual([line["text"] for line in page["lines"][:6]], left + right)
        self.assertEqual([[span["text"] for span in line["spans"]] for line in page["lines"][6:]], [
            ["Metric", "2025", "2024"], ["Revenue", "(120,75)", "100"],
        ])
        self.assertLess(page["lines"][0]["bbox"][0], page["lines"][3]["bbox"][0])

    def test_footer_is_evidence_separate_from_metadata_and_unlabeled_body(self):
        sample = pdf([
            (0, None, text(45, 290, "Page 9") + text(130, 22, "Page 3 / Own teaching example.")),
            (0, None, text(45, 290, "Page 10") + text(130, 22, "42")),
            (0, None, text(130, 22, "Page 4") + text(130, 38, "Page 5")),
        ], labels=((0, "Annex-A"), (1, "Annex-B")))
        first, second, ambiguous = extract_pdf_pages(sample)["pages"]
        self.assertEqual((first["pdf_page_label"], first["printed_page"]), ("Annex-A", "3"))
        self.assertEqual((second["pdf_page_label"], second["printed_page"]), ("Annex-B", None))
        self.assertIsNone(ambiguous["printed_page"])

    def test_image_only_page_reports_pending_without_entering_renderer(self):
        image = "q 200 0 0 180 70 40 cm BI /W 1 /H 1 /BPC 8 /CS /RGB /F /AHx ID 000000> EI Q\n"
        with patch.object(pdfium.PdfPage, "render", side_effect=AssertionError("unexpected rendering")):
            result = extract_pdf_pages(pdf([(0, None, image)], labels=((0, "Scan A"),)))
        page, = result["pages"]
        self.assertEqual(page["text_status"], "ocr_pending")
        self.assertEqual(page["lines"], [])
        self.assertEqual(page["pdf_page_label"], "Scan A")
        self.assertIsNone(page["printed_page"])
        self.assertIn("ocr_pending", result["notes"])

    def test_refuses_corrupt_read_and_dimensions_or_text_budget(self):
        samples = (
            (b"%PDF-1.4\nnot a page\n%%EOF", "pdf_corrupt"),
            (pdf([(0, None, text(15, 18, "bounded"))], media="0 0 8300 320"), "pdf_limit"),
        )
        for candidate, code in samples:
            with self.subTest(code=code), self.assertRaises(ExtractionError) as error:
                extract_pdf_pages(candidate)
            self.assertEqual(error.exception.code, code)
        with patch("financial_assistant.pdf_text_ir._MAX_PAGE_CHARS", 4):
            with self.assertRaises(ExtractionError) as error:
                extract_pdf_pages(pdf([(0, None, text(15, 18, "bounded"))]))
            self.assertEqual(error.exception.code, "pdf_limit")


if __name__ == "__main__":
    unittest.main()
