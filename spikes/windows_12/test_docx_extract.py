"""Synthetic Word packages exercising provenance, merges and passive text."""

from io import BytesIO
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from financial_assistant.docx_extract import extract_docx
from financial_assistant.office_extraction_common import ExtractionError, MAX_CELLS, MAX_TEXT
from financial_assistant.safe_import import ImportValidationError, classify_bytes


MAIN = "word/document.xml"
TRANSITIONAL = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
STRICT = "http://purl.oclc.org/ooxml/wordprocessingml/main"
PARAGRAPH = "<w:p><w:r><w:t>{}</w:t></w:r></w:p>"
CONTENT_TYPES = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>'
)
RELATIONS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="main" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>'
)


def package(body, *, namespace=TRANSITIONAL, other=()):
    main = f'<w:document xmlns:w="{namespace}"><w:body>{body}</w:body></w:document>'
    with BytesIO() as stream:
        with ZipFile(stream, "w") as archive:
            for name, data in [("[Content_Types].xml", CONTENT_TYPES), ("_rels/.rels", RELATIONS),
                               (MAIN, main), *other]:
                archive.writestr(name, data)
        return stream.getvalue()


def read(data):
    assert classify_bytes(data) == "docx"
    return extract_docx(data)


class DocxExtractionTests(unittest.TestCase):
    def test_paragraph_part_numbers_physical_cells_grid_spans_and_header_rows(self):
        body = (
            '<w:p><w:r><w:t xml:space="preserve">Отчёт </w:t><w:tab/><w:t>&lt;текст&gt;</w:t></w:r></w:p>'
            '<w:tbl><w:tblPr><w:tblCaption w:val="Результаты"/></w:tblPr>'
            '<w:tblGrid><w:gridCol/><w:gridCol/><w:gridCol/></w:tblGrid>'
            '<w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc>'
            '<w:tcPr><w:gridSpan w:val="2"/><w:vMerge w:val="restart"/></w:tcPr>'
            + PARAGRAPH.format("Показатель") + '</w:tc><w:tc>' + PARAGRAPH.format("2025") + '</w:tc></w:tr>'
            '<w:tr><w:trPr><w:tblHeader w:val="false"/></w:trPr><w:tc>'
            '<w:tcPr><w:gridSpan w:val="2"/><w:vMerge/></w:tcPr><w:p/></w:tc><w:tc>'
            + PARAGRAPH.format("(120,50 млн)") + PARAGRAPH.format("Сравнительные данные") + '</w:tc></w:tr>'
            '<w:tr><w:trPr><w:gridBefore w:val="1"/><w:gridAfter w:val="1"/></w:trPr><w:tc>'
            + PARAGRAPH.format("Подстрока") + '</w:tc></w:tr></w:tbl>'
            + PARAGRAPH.format("Примечание")
        )
        result = read(package(body))
        self.assertEqual(set(result), {"encoding", "delimiter", "tables", "paragraphs", "notes"})
        self.assertIsNone(result["encoding"])
        self.assertIsNone(result["delimiter"])
        self.assertEqual(result["notes"], [])
        self.assertEqual(result["paragraphs"][0], {
            "locator": {"part": MAIN, "paragraph": 1}, "text": "Отчёт \t<текст>",
        })
        table, = result["tables"]
        self.assertEqual(table["name"], "Результаты")
        self.assertEqual(table["locator"], {"part": MAIN, "table": 1})
        self.assertEqual(table["header_rows"], [1])
        self.assertEqual(table["merges"], [{"row": 1, "column": 1, "end_row": 2, "end_column": 2}])
        self.assertEqual(table["rows"][0]["cells"][0]["column_span"], 2)
        self.assertEqual(table["rows"][0]["cells"][1]["locator"], {
            "part": MAIN, "table": 1, "row": 1, "cell": 2, "column": 3,
        })
        self.assertIsNone(table["rows"][1]["cells"][0]["text"])
        self.assertEqual(table["rows"][1]["cells"][0]["kind"], "empty")
        self.assertEqual(table["rows"][1]["cells"][1]["text"], "(120,50 млн)\nСравнительные данные")
        self.assertEqual(table["rows"][2]["cells"][0]["locator"]["column"], 2)
        self.assertEqual(result["paragraphs"][4]["locator"], {
            "part": MAIN, "paragraph": 5, "table": 1, "row": 2, "cell": 2, "column": 3,
        })
        self.assertEqual(result["paragraphs"][-1]["locator"], {"part": MAIN, "paragraph": 8})

    def test_nested_tables_and_visible_control_content_have_unique_ordinals(self):
        nested = '<w:tbl><w:tr><w:tc>' + PARAGRAPH.format("Вложенный") + '</w:tc></w:tr></w:tbl>'
        outer = '<w:tbl><w:tr><w:tc>' + PARAGRAPH.format("До") + nested + PARAGRAPH.format("После") + '</w:tc></w:tr></w:tbl>'
        controlled = '<w:sdt><w:sdtContent>' + outer + '</w:sdtContent></w:sdt>'
        result = read(package(controlled, namespace=STRICT))
        outer_table, inner_table = result["tables"]
        self.assertEqual(outer_table["rows"][0]["cells"][0]["text"], "До\nПосле")
        self.assertEqual(inner_table["rows"][0]["cells"][0]["text"], "Вложенный")
        self.assertEqual([row["locator"]["table"] for row in result["paragraphs"]], [1, 2, 1])
        self.assertEqual([row["locator"]["paragraph"] for row in result["paragraphs"]], [1, 2, 3])

    def test_legacy_horizontal_merge_and_honest_ancillary_scope(self):
        body = (
            '<w:tbl><w:tr><w:tc><w:tcPr><w:hMerge w:val="restart"/></w:tcPr>'
            + PARAGRAPH.format("Заголовок") +
            '</w:tc><w:tc><w:tcPr><w:hMerge/></w:tcPr><w:p/></w:tc></w:tr></w:tbl>'
        )
        header = f'<w:hdr xmlns:w="{TRANSITIONAL}">{PARAGRAPH.format("Колонтитул")}</w:hdr>'
        result = read(package(body, other=(("word/header1.xml", header),)))
        self.assertEqual(result["tables"][0]["merges"],
                         [{"row": 1, "column": 1, "end_row": 1, "end_column": 2}])
        self.assertEqual(result["notes"], ["ancillary_parts_omitted"])
        self.assertNotIn("Колонтитул", [item["text"] for item in result["paragraphs"]])

    def test_fields_omit_instructions_and_cached_content_and_detect_split_dynamic_marker(self):
        def field(first, second):
            return (
                '<w:p><w:r><w:t>До</w:t><w:fldChar w:fldCharType="begin"/>'
                f'<w:instrText>{first}</w:instrText></w:r><w:r><w:instrText>{second}</w:instrText>'
                '<w:fldChar w:fldCharType="separate"/><w:t>НЕ ВЫВОДИТЬ</w:t>'
                '<w:fldChar w:fldCharType="end"/><w:br/><w:t>После</w:t></w:r></w:p>'
            )
        result = read(package(field("PA", "GE")))
        self.assertEqual(result["notes"], ["field_content_omitted"])
        self.assertEqual(result["paragraphs"][0]["text"], "До\nПосле")
        with self.assertRaises(ExtractionError) as caught:
            read(package(field("D", "DE")))
        self.assertEqual(caught.exception.code, "archive_active_payload")

    def test_full_guard_refuses_external_relationship_and_embedded_parts(self):
        external_link = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="ref" Type="urn:synthetic" TargetMode="External" Target="https://example.invalid"/>'
            '</Relationships>'
        )
        for name, payload in (("word/_rels/document.xml.rels", external_link),
                              ("word/embeddings/hold.dat", "ordinary placeholder bytes")):
            with self.subTest(name=name), self.assertRaises(ImportValidationError) as caught:
                read(package(PARAGRAPH.format("Собственный пример"), other=((name, payload),)))
            self.assertEqual(caught.exception.code, "archive_active_payload")

    def test_bounded_text_grid_and_invalid_vertical_merge(self):
        for body, code in (
            (PARAGRAPH.format("x" * (MAX_TEXT + 1)), "extraction_limit"),
            ('<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="' + str(MAX_CELLS + 1) +
             '"/></w:tcPr><w:p/></w:tc></w:tr></w:tbl>', "extraction_limit"),
            ('<w:tbl><w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc></w:tr></w:tbl>',
             "docx_structure_invalid"),
        ):
            with self.subTest(code=code), self.assertRaises(ExtractionError) as caught:
                read(package(body))
            self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
