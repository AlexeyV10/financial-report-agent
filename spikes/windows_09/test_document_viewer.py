"""WIN-09 checks using the WIN-01 oracle and the existing installed WIN-08 fixture.

Set WIN09_SHELL_STAGE to the fixture directory when it is outside the sibling
worktree. The renderer tests use the bundled PDFium and Pillow.
"""

import base64
from contextlib import closing
from fractions import Fraction
import hashlib
from io import BytesIO
from itertools import product
import json
from math import ceil, floor
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
import pypdfium2

ROOT = Path(__file__).resolve().parents[2]
for test_import_root in (ROOT / "src", ROOT / "spikes/windows_01", ROOT / "spikes/windows_04"):
    sys.path.insert(0, str(test_import_root))

from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.application_service import ApplicationService
from financial_assistant.document_viewer import (
    DocumentViewerError,
    PdfiumRenderer,
    render_workspace_source,
    view_geometry,
)
from financial_assistant.typed_ipc import decode_response, make_request
from financial_assistant.vault_storage import VaultStore
from workspace_demo import calculate_workspace_demo


STAGE = Path(os.environ.get(
    "WIN09_SHELL_STAGE", ROOT.parent / "windows-08-worktree/tmp/shell-e2e-reviewed"
)).resolve()
ORACLE = json.loads((ROOT / "spikes/windows_01/expected.json").read_text(encoding="utf-8"))
SOURCE_ID = "own-demo-v1"
SOURCE_SHA256 = "c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451"
GREEN = (0, 140, 65)
RUN_ID = "win09-test-receipt"


def read_own_pdf():
    source = STAGE / "Проект А/Отчёты/Учебный пример.pdf"
    if not source.is_file():
        raise unittest.SkipTest("Set WIN09_SHELL_STAGE to the reviewed WIN-08 fixture")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise AssertionError("The own demo fixture differs from its pinned SHA-256")
    return data


def two_page_pdf():
    """Create an independent PDF whose labels differ from its printed folios."""
    def text_stream(folio):
        stream = f"BT /F1 12 Tf 20 70 Td (Printed folio {folio}) Tj ET".encode("ascii")
        return f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"

    def page(contents):
        return (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] /Contents {contents} 0 R "
                "/Resources << /Font << /F1 7 0 R >> >> >>").encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /PageLabels << /Nums [0 << /P (Front-i) >> "
        b"1 << /P (Annex-7) >>] >> >>",
        b"<< /Type /Pages /Count 2 /Kids [3 0 R 5 0 R] >>",
        page(4), text_stream(1), page(6), text_stream(42),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(data)


class ViewerAssertions(unittest.TestCase):
    def assert_error(self, code, method, *args, **kwargs):
        with self.assertRaises(DocumentViewerError) as error:
            method(*args, **kwargs)
        self.assertEqual(error.exception.code, code)

    def assert_png(self, frame, size, highlight):
        self.assertEqual((frame["width"], frame["height"]), size)
        self.assertEqual(frame["highlight"], highlight)
        data = base64.b64decode(frame["png"], validate=True)
        with Image.open(BytesIO(data)) as source:
            self.assertEqual(source.format, "PNG")
            self.assertEqual(source.size, size)
            with source.convert("RGB") as image:
                left, top, right, bottom = highlight
                right, bottom = min(right, size[0] - 1), min(bottom, size[1] - 1)
                middle_x, middle_y = (left + right) // 2, (top + bottom) // 2
                for point in ((left, top), (right, bottom), (middle_x, top),
                              (middle_x, bottom), (left, middle_y), (right, middle_y)):
                    self.assertEqual(image.getpixel(point), GREEN, point)
                self.assertNotEqual(image.getpixel((left - 1, middle_y)), GREEN)
                self.assertNotEqual(image.getpixel((middle_x, top - 1)), GREEN)


class PdfiumRendererTests(ViewerAssertions):
    def test_64_rotation_zoom_and_dpi_cases_match_oracle_and_png(self):
        data = read_own_pdf()
        renderer = PdfiumRenderer()
        width, height = ORACLE["page_size"]
        source_rect = ORACLE["profit_pdf_rect"]
        percentages = (100, 125, 150, 200)
        for rotation, zoom, dpi in product((0, 90, 180, 270), percentages, percentages):
            with self.subTest(rotation=rotation, zoom=zoom, dpi=dpi):
                scale = Fraction(zoom * dpi, 10000)
                size = (height, width) if rotation in (90, 270) else (width, height)
                raster = tuple(ceil(value * scale) for value in size)
                left, top, right, bottom = ORACLE["profit_pixel_rect_at_scale1"][str(rotation)]
                highlight = [floor(left * scale), floor(top * scale),
                             ceil(right * scale), ceil(bottom * scale)]
                geometry = view_geometry(width, height, source_rect, zoom_percent=zoom,
                                         rotation=rotation, dpi_percent=dpi)
                self.assertEqual(geometry, {
                    "full_width": raster[0], "full_height": raster[1],
                    "width": raster[0], "height": raster[1], "highlight": highlight, "crop": None,
                })
                self.assert_png(renderer.render(data, 0, zoom, rotation, dpi, source_rect=source_rect),
                                raster, highlight)

    def test_center_and_clipped_edge_crops_keep_highlight_visible(self):
        width, height = ORACLE["page_size"]
        data = read_own_pdf()
        renderer = PdfiumRenderer()
        fixtures = (
            (ORACLE["profit_pdf_rect"], 100, 0, 100, [288, 174, 352, 222], (64, 48), [12, 12, 52, 36]),
            ([4, 2, 20, 14], 100, 0, 100, [0, 334, 32, 360], (32, 26), [4, 12, 20, 24]),
            ([4, 2, 20, 14], 125, 90, 150, [0, 0, 49, 60], (49, 60), [3, 7, 27, 38]),
        )
        for rect, zoom, rotation, dpi, crop, size, highlight in fixtures:
            with self.subTest(rect=rect, rotation=rotation):
                geometry = view_geometry(width, height, rect, zoom_percent=zoom, rotation=rotation,
                                         dpi_percent=dpi, crop_to_source=True)
                self.assertEqual(geometry["crop"], crop)
                frame = renderer.render(data, 0, zoom, rotation, dpi, source_rect=rect, crop_to_source=True)
                self.assert_png(frame, size, highlight)

    def test_loads_only_selected_pdf_page_and_preserves_label_and_printed_text(self):
        renderer = PdfiumRenderer()
        data = two_page_pdf()
        load_page = pypdfium2.PdfDocument.get_page
        loaded = []

        def observe_load(document, page_index):
            loaded.append(page_index)
            return load_page(document, page_index)

        with patch.object(pypdfium2.PdfDocument, "get_page", observe_load):
            result = renderer.render(data, 1, 100, 0, 100)
            self.assert_error("page_out_of_range", renderer.render, data, 2, 100, 0, 100)
        self.assertEqual(loaded, [1])
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["pdf_page_label"], "Annex-7")
        self.assertEqual(result["page_text"].strip(), "Printed folio 42")
        self.assertIsNone(result["highlight"])

    def test_invalid_options_and_bounded_geometry(self):
        renderer = PdfiumRenderer()
        data = two_page_pdf()
        self.assert_error("invalid_view_options", renderer.render, data, 0, True, 0, 100)
        self.assert_error("invalid_view_options", renderer.render, data, 0, 100, 45, 100)
        self.assert_error("invalid_view_options", renderer.render, data, 0, 100, 0, 201)
        self.assert_error("page_out_of_range", renderer.render, data, -1, 100, 0, 100)
        self.assert_error("render_failed", renderer.render, b"not a PDF", 0, 100, 0, 100)
        self.assert_error("render_limit", view_geometry, 1500, 200, None,
                          zoom_percent=200, rotation=0, dpi_percent=200)
        self.assert_error("invalid_crop", view_geometry, 200, 120, None,
                          zoom_percent=100, rotation=0, dpi_percent=100, crop_to_source=True)


@unittest.skipUnless(STAGE.is_dir(), "Set WIN09_SHELL_STAGE to the reviewed WIN-08 fixture")
class WorkspaceViewerTests(ViewerAssertions):
    def setUp(self):
        self.paths = ApplicationPaths(STAGE / "Установка оболочки", STAGE / "Данные оболочки")
        self.prepared_vault = STAGE / "Проект А"

    def active_vault(self):
        # Reuse the prepared install and archive, with a genuine, newly scoped run receipt.
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        temp = TemporaryDirectory(prefix="win09-test-", dir=scratch)
        self.addCleanup(temp.cleanup)
        vault = Path(temp.name) / "Отдельный проект"
        vault.mkdir()
        marker = self.prepared_vault / "workspace.json"
        shutil.copyfile(marker, vault / marker.name)
        binding = json.loads(marker.read_text(encoding="utf-8"))["resources"][0]
        source = vault / binding["path"]
        source.parent.mkdir()
        source.write_bytes(read_own_pdf())
        shutil.copyfile(self.prepared_vault / "vault.sqlite3", vault / "vault.sqlite3")

        service = ApplicationService(self.paths, vault, calculate_workspace_demo)
        workspace, context_id = service.context()
        request = make_request(context_id, RUN_ID)
        result = decode_response(service.evaluate(request), request)
        self.assertEqual(result["status"], "completed", result["error"])
        self.assertEqual(service.persist(request, result), result)
        return workspace, source

    def test_existing_installed_fixture_reads_completed_run_and_preserves_archive(self):
        workspace = WorkspaceContext.open(self.paths, self.prepared_vault)
        receipts = sorted((workspace.vault_root / "runs").glob("*.json"))
        self.assertTrue(receipts)
        receipt = next(path for path in receipts
                       if json.loads(path.read_text(encoding="utf-8"))["status"] == "completed")
        original = receipt.read_bytes()
        db = workspace.vault_root / "vault.sqlite3"
        db_content = db.read_bytes()
        run_id = json.loads(original)["run_id"]
        frame = render_workspace_source(workspace, run_id, SOURCE_ID, 0, 100, 0, 100)
        self.assertEqual(frame["schema"], "win09-viewer-1")
        self.assertEqual(frame["status"], "ok")
        self.assertEqual(frame["source_sha256"], SOURCE_SHA256)
        self.assertEqual(frame["resource_id"], SOURCE_ID)
        self.assertEqual(frame["page_index"], 0)
        self.assertEqual(frame["page_count"], 1)
        self.assertIsNone(frame["pdf_page_label"])
        self.assertEqual(frame["printed_page"], "1")
        self.assertIn("Operating profit", frame["page_text"])
        self.assertIn("Операционная прибыль (Operating profit)\t18", frame["table_text"])
        self.assert_png(frame, (420, 360), [300, 186, 340, 210])
        self.assertEqual(receipt.read_bytes(), original)
        self.assertEqual(db.read_bytes(), db_content)

    def test_archived_copy_works_without_loose_source_and_rejects_wrong_resource_page_or_run(self):
        workspace, source = self.active_vault()
        source.unlink()
        frame = render_workspace_source(workspace, RUN_ID, SOURCE_ID, 0, 100, 0, 100, True)
        self.assert_png(frame, (64, 48), [12, 12, 52, 36])
        for name, resource_id in (("unknown_id", "other-resource"), ("absolute_path", str(source))):
            with self.subTest(resource=name):
                self.assert_error("resource_not_authorized", render_workspace_source,
                                  workspace, RUN_ID, resource_id, 0, 100, 0, 100)
        self.assert_error("page_out_of_range", render_workspace_source,
                          workspace, RUN_ID, SOURCE_ID, 1, 100, 0, 100)
        self.assert_error("receipt_missing", render_workspace_source,
                          workspace, "missing-receipt", SOURCE_ID, 0, 100, 0, 100)

    def test_run_receipt_cannot_authorize_another_vault_or_different_cited_bytes(self):
        workspace, _ = self.active_vault()
        root = workspace.vault_root
        receipt = root / "runs" / (RUN_ID + ".json")
        raw = receipt.read_bytes()
        result = json.loads(raw)
        for key, value in (("source_sha256", "f" * 64), ("source_highlight", [1, 2, 3, 4])):
            with self.subTest(key=key):
                claim = json.loads(raw)
                claim["result"][key] = value
                receipt.write_text(json.dumps(claim), encoding="utf-8")
                self.assert_error("source_binding_mismatch", render_workspace_source,
                                  workspace, RUN_ID, SOURCE_ID, 0, 100, 0, 100)

        other = root.parent / "Другой проект"
        (other / "runs").mkdir(parents=True)
        marker = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
        marker["workspace_id"] = "workspace-b"
        (other / "workspace.json").write_text(json.dumps(marker), encoding="utf-8")
        (other / "runs" / receipt.name).write_text(json.dumps(result), encoding="utf-8")
        self.assert_error("source_binding_mismatch", render_workspace_source,
                          WorkspaceContext.open(self.paths, other), RUN_ID, SOURCE_ID, 0, 100, 0, 100)

    def test_same_size_corrupt_archived_bytes_and_missing_storage_refuse_render(self):
        workspace, _ = self.active_vault()
        with VaultStore(workspace) as store:
            data = store.read_original(SOURCE_SHA256)
            db = store.path
        with closing(sqlite3.connect(db)) as connection:
            changed = data[:-1] + bytes([data[-1] ^ 1])
            connection.execute("UPDATE originals SET data = ? WHERE sha256 = ?", (changed, SOURCE_SHA256))
            connection.commit()
        self.assert_error("storage_integrity_failed", render_workspace_source,
                          workspace, RUN_ID, SOURCE_ID, 0, 100, 0, 100)
        db.rename(db.with_suffix(".held"))
        self.assert_error("storage_missing", render_workspace_source,
                          workspace, RUN_ID, SOURCE_ID, 0, 100, 0, 100)

    def test_viewer_cli_rejects_user_supplied_pdf_path_without_echoing_it(self):
        candidate = self.prepared_vault / "Отчёты/Учебный пример.pdf"
        result = subprocess.run([
            sys.executable, "-I", "-B", str(ROOT / "spikes/windows_09/viewer_cli.py"),
            "--install-root", str(self.paths.install_root), "--app-data", str(self.paths.app_data_root),
            "--vault", str(self.prepared_vault), "--run-id", RUN_ID, "--resource-id", SOURCE_ID,
            "--page-index", "0", "--zoom-percent", "100", "--rotation", "0", "--dpi-percent", "100",
            "--path", str(candidate),
        ], cwd=ROOT, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout.count(b"\n"), 1)
        self.assertEqual(json.loads(result.stdout), {
            "schema": "win09-viewer-1", "status": "error", "error": "invalid_view_options",
        })


if __name__ == "__main__":
    unittest.main()
