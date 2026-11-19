"""Own in-memory format and refusal fixtures for the local importer."""

from io import BytesIO
from pathlib import Path
import runpy
import stat
import struct
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import zlib

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant.safe_import import ImportValidationError, classify_bytes, read_candidate
from financial_assistant.vault_storage import MAX_CAPTURE_BYTES


def _zip(files, compression=ZIP_DEFLATED):
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression) as archive:
        for name, data in files:
            archive.writestr(name, data)
    return buffer.getvalue()


def _office(kind, extra=()):
    if kind == 'xlsx':
        main, tag = 'xl/workbook.xml', 'workbook'
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'
        namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    else:
        main, tag = 'word/document.xml', 'document'
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
        namespace = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    manifest = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                f'<Override PartName="/{main}" ContentType="{content_type}"/></Types>')
    relations = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="main" Type="http://schemas.openxmlformats.org/officeDocument/'
                 f'2006/relationships/officeDocument" Target="{main}"/></Relationships>')
    return _zip([('[Content_Types].xml', manifest), ('_rels/.rels', relations),
                 (main, f'<{tag} xmlns="{namespace}"/>'), *extra])


def _image(format_name):
    with BytesIO() as output:
        with Image.new('RGB', (8, 12), (0, 120, 60)) as sample:
            sample.save(output, format=format_name)
        return output.getvalue()


def _png_with_large_declared_width():
    normal = _image('PNG')
    header = b'IHDR' + struct.pack('>I', 50000) + normal[20:29]
    return normal[:12] + header + struct.pack('>I', zlib.crc32(header)) + normal[33:]


def _encryption_marker():
    archive = bytearray(_zip([('own.txt', 'own test only')]))
    local = archive.index(b'PK\x03\x04')
    central = archive.index(b'PK\x01\x02')
    archive[local + 6] |= 1
    archive[central + 8] |= 1
    return bytes(archive)


class SafeImportTests(unittest.TestCase):
    def verify_denied(self, data, code):
        with self.assertRaises(ImportValidationError) as raised:
            classify_bytes(data)
        self.assertEqual(raised.exception.code, code)

    def test_own_file_format_detected_without_reading_name(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        payload = 'Год;Выручка\n2025;120\n2024;100\n'.encode('utf-8')
        with TemporaryDirectory(dir=ROOT / 'tmp') as temp:
            candidate = Path(temp) / 'Русский документ.pdf'
            candidate.write_bytes(payload)
            self.assertEqual(read_candidate(candidate), payload)
            self.assertEqual(classify_bytes(read_candidate(candidate)), 'csv')
            with self.assertRaises(ImportValidationError):
                read_candidate(Path(candidate.name))

    def test_utf16_with_bom_and_plain_utf8(self):
        self.assertEqual(classify_bytes('Собственный текст\nВторая строка'.encode('utf-16')), 'txt')
        self.assertEqual(classify_bytes('одна строка'.encode('utf-8')), 'txt')

    def test_stream_read_caps_on_actual_regular_file(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        with TemporaryDirectory(dir=ROOT / 'tmp') as temp:
            path = Path(temp) / 'synthetic-oversize.txt'
            with path.open('xb') as stream:
                stream.seek(MAX_CAPTURE_BYTES)
                stream.write(b'X')
            with self.assertRaises(ImportValidationError) as raised:
                read_candidate(path)
            self.assertEqual(raised.exception.code, 'capture_too_large')

    def test_own_real_pdf_and_truncated_pdf(self):
        generator = runpy.run_path(str(ROOT / 'spikes/windows_10/generate_d0_demo.py'))
        pdf = generator['report_pdf']()
        self.assertEqual(classify_bytes(pdf), 'pdf')
        self.verify_denied(b'%PDF-1.7\nthis own synthetic fixture has no page tree\n', 'pdf_corrupt')

    def test_pdf_declared_large_page_is_not_rasterized(self):
        generator = runpy.run_path(str(ROOT / 'spikes/windows_10/generate_d0_demo.py'))
        make_pdf = generator['report_pdf']
        make_pdf.__globals__['PAGE_SIZE'] = (10000, 340)
        self.verify_denied(make_pdf(), 'pdf_limit')

    def test_actual_pillow_formats_and_declared_huge_width(self):
        for name in ('PNG', 'JPEG', 'TIFF'):
            with self.subTest(name=name):
                self.assertEqual(classify_bytes(_image(name)), name.lower())
        self.verify_denied(_png_with_large_declared_width(), 'image_limit')

    def test_same_zip_has_docx_or_xlsx_according_to_marker(self):
        self.assertEqual(classify_bytes(_office('xlsx')), 'xlsx')
        self.assertEqual(classify_bytes(_office('docx')), 'docx')
        self.verify_denied(_zip([('only.txt', 'own fixture')]), 'unsupported_format')

    def test_archive_paths_rejected_without_extracting_anything(self):
        for path in ('../qa-marker.txt', '/qa-marker.txt', 'C:/qa-marker.txt', 'word/file.txt:stream'):
            with self.subTest(path=path):
                self.verify_denied(_office('docx', [(path, 'own QA marker')]), 'archive_path_invalid')
        forward = _office('docx', [('word/qa-marker.txt', 'own QA marker')])
        self.assertEqual(forward.count(b'word/qa-marker.txt'), 2)
        raw_backslashes = forward.replace(b'word/qa-marker.txt', b'word\\qa-marker.txt')
        self.verify_denied(raw_backslashes, 'archive_path_invalid')

    def test_archive_equivalent_names_and_symlinks_rejected(self):
        self.verify_denied(_office('xlsx', [('XL/WORKBOOK.XML', b'<own/>')]), 'archive_duplicate_member')
        link = ZipInfo('word/own-link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.verify_denied(_office('docx', [(link, b'own-marker')]), 'archive_links_forbidden')

    def test_archive_markers_for_encryption_and_active_members_are_refused(self):
        self.verify_denied(_encryption_marker(), 'archive_encrypted')
        self.verify_denied(_office('xlsx', [('xl/vbaProject.bin', b'own inert VBA-marker test')]),
                           'archive_active_payload')
        self.verify_denied(_office('docx', [('word/embeddings/own.exe', b'own inert marker')]),
                           'archive_active_payload')

    def test_archive_declared_ratio_fails_before_document_capture(self):
        self.verify_denied(_office('xlsx', [('xl/worksheets/synthetic.txt', b'A' * 500000)]), 'archive_limit')

    def test_external_xml_relationship_is_refused_without_contacting_it(self):
        external = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="inert" Type="http://schemas.openxmlformats.org/officeDocument/'
                    '2006/relationships/hyperlink" TargetMode="External" '
                    'Target="https://example.invalid/owned-qa"/></Relationships>')
        self.verify_denied(_office('docx', [('word/_rels/document.xml.rels', external)]), 'archive_active_payload')

    def test_corrupted_archive_member_does_not_become_document(self):
        damaged = bytearray(_office('xlsx'))
        first_item = damaged.index(b'PK\x01\x02')
        damaged[first_item + 16] ^= 1
        self.verify_denied(bytes(damaged), 'archive_corrupt')


if __name__ == '__main__':
    unittest.main()
