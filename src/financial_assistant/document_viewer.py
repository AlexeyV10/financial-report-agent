"""Lazy PDF rendering of an exact source already cited in the selected vault."""

import base64
from io import BytesIO
import json
from math import ceil, floor
import re

from .application_paths import WorkspaceContext, WorkspacePathError
from .application_service import ApplicationService, SOURCE_ID, SOURCE_SHA256
from .typed_ipc import TypedIpcError, decode_response, make_request
from .vault_storage import MAX_CAPTURE_BYTES, VaultStorageError, VaultStore


VIEWER_SCHEMA = "win09-viewer-1"
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 8_000_000
MAX_PAGES = 100
_MAX_PNG_BYTES = 1_450_000
_MAX_PAGE_TEXT_BYTES = 32_768
_PAD = 12
_GREEN = (0, 140, 65)
_OWN_SOURCE_RECT = (300, 150, 340, 174)
_OWN_HIGHLIGHT = [300, 186, 340, 210]
_OWN_PRINTED_PAGE = re.compile(r"(?m)^Page (1) / Own generated example; redistribution permitted\.\s*$")
_OWN_TABLE = ("МСФО · группа · 2025 год · млн RUB\n"
              "Выручка (Revenue)\t120\nОперационная прибыль (Operating profit)\t18")
_RENDER_FIELDS = {"page_count", "pdf_page_label", "width", "height", "highlight", "page_text", "png"}


class DocumentViewerError(ValueError):
    """A stable viewer error without a private path or raw PDFium message."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _validate_view(zoom_percent, rotation, dpi_percent, crop_to_source):
    if (type(zoom_percent) is not int or not 50 <= zoom_percent <= 200
            or type(dpi_percent) is not int or not 50 <= dpi_percent <= 200
            or type(rotation) is not int or rotation not in {0, 90, 180, 270}
            or type(crop_to_source) is not bool):
        raise DocumentViewerError("invalid_view_options")


def _validate_page_index(page_index):
    if type(page_index) is not int or not 0 <= page_index < MAX_PAGES:
        raise DocumentViewerError("page_out_of_range")


def _pixel_box(rect, width, height, rotation, scale):
    left, bottom, right, top = rect
    rotated = {
        0: (left, height - top, right, height - bottom),
        90: (bottom, left, top, right),
        180: (width - right, bottom, width - left, top),
        270: (height - top, width - right, height - bottom, width - left),
    }[rotation]
    return [floor(rotated[0] * scale), floor(rotated[1] * scale),
            ceil(rotated[2] * scale), ceil(rotated[3] * scale)]


def view_geometry(width, height, source_rect, *, zoom_percent, rotation, dpi_percent,
                  crop_to_source=False) -> dict:
    """Map a bottom-left PDF rectangle to the bounded rotated raster and crop."""
    _validate_view(zoom_percent, rotation, dpi_percent, crop_to_source)
    if (type(width) not in {int, float} or type(height) not in {int, float}
            or not 0 < width <= MAX_DIMENSION * 4 or not 0 < height <= MAX_DIMENSION * 4):
        raise DocumentViewerError("render_limit")
    scale = zoom_percent * dpi_percent / 10000
    size = (width, height) if rotation in {0, 180} else (height, width)
    full_width, full_height = (ceil(value * scale) for value in size)
    if max(full_width, full_height) > MAX_DIMENSION or full_width * full_height > MAX_PIXELS:
        raise DocumentViewerError("render_limit")
    if crop_to_source and source_rect is None:
        raise DocumentViewerError("invalid_crop")

    highlight = crop = None
    result_width, result_height = full_width, full_height
    if source_rect is not None:
        if (type(source_rect) not in {list, tuple} or len(source_rect) != 4
                or any(type(value) not in {int, float} for value in source_rect)):
            raise DocumentViewerError("invalid_crop")
        left, bottom, right, top = source_rect
        if not (0 <= left < right <= width and 0 <= bottom < top <= height):
            raise DocumentViewerError("invalid_crop")
        highlight = _pixel_box(source_rect, width, height, rotation, scale)
        if crop_to_source:
            crop_rect = (max(0, left - _PAD), max(0, bottom - _PAD),
                         min(width, right + _PAD), min(height, top + _PAD))
            crop = _pixel_box(crop_rect, width, height, rotation, scale)
            result_width, result_height = crop[2] - crop[0], crop[3] - crop[1]
            highlight = [value - crop[index % 2] for index, value in enumerate(highlight)]
    return {"full_width": full_width, "full_height": full_height, "width": result_width,
            "height": result_height, "highlight": highlight, "crop": crop}


def _draw_page(page, geometry, scale, rotation):
    from PIL import ImageDraw

    bitmap = page.render(scale=scale, rotation=rotation, may_draw_forms=False)
    try:
        image = bitmap.to_pil().convert("RGB")
        if image.size != (geometry["full_width"], geometry["full_height"]):
            raise DocumentViewerError("render_failed")
        if geometry["crop"] is not None:
            image = image.crop(geometry["crop"])
        rect = geometry["highlight"]
        if rect is not None:
            left, top, right, bottom = rect
            # Right and bottom in the geometry may refer to the outer pixel edge.
            ImageDraw.Draw(image).rectangle((left, top, min(right, image.width - 1),
                                             min(bottom, image.height - 1)),
                                            outline=_GREEN, width=max(1, round(2 * scale)))
        with BytesIO() as stream:
            image.save(stream, format="PNG")
            if stream.tell() > _MAX_PNG_BYTES:
                raise DocumentViewerError("render_limit")
            return base64.b64encode(stream.getvalue()).decode("ascii")
    finally:
        bitmap.close()


class PdfiumRenderer:
    """Open a trusted PDF in memory and render only the requested page."""

    def render(self, data: bytes, page_index, zoom_percent, rotation, dpi_percent, *,
               source_rect=None, crop_to_source=False) -> dict:
        _validate_page_index(page_index)
        _validate_view(zoom_percent, rotation, dpi_percent, crop_to_source)
        if type(data) is not bytes or not 0 < len(data) <= MAX_CAPTURE_BYTES:
            raise DocumentViewerError("render_limit")
        try:
            import pypdfium2 as pdfium

            with pdfium.PdfDocument(data) as document:
                count = len(document)
                if count > MAX_PAGES:
                    raise DocumentViewerError("render_limit")
                if page_index >= count:
                    raise DocumentViewerError("page_out_of_range")
                label = document.get_page_label(page_index) or None
                if label is not None and (len(label.encode("utf-8")) > 256 or "\0" in label):
                    raise DocumentViewerError("render_limit")
                page = document[page_index]
                try:
                    geometry = view_geometry(*page.get_size(), source_rect, zoom_percent=zoom_percent,
                                             rotation=rotation, dpi_percent=dpi_percent, crop_to_source=crop_to_source)
                    text_page = page.get_textpage()
                    try:
                        if text_page.count_chars() > _MAX_PAGE_TEXT_BYTES:
                            raise DocumentViewerError("render_limit")
                        page_text = text_page.get_text_bounded().replace("\r\n", "\n").replace("\r", "\n")
                    finally:
                        text_page.close()
                    if len(page_text.encode("utf-8")) > _MAX_PAGE_TEXT_BYTES or "\0" in page_text:
                        raise DocumentViewerError("render_limit")
                    png = _draw_page(page, geometry, zoom_percent * dpi_percent / 10000, rotation)
                finally:
                    page.close()
        except DocumentViewerError:
            raise
        except Exception:
            raise DocumentViewerError("render_failed") from None
        return {"page_count": count, "pdf_page_label": label, "width": geometry["width"],
                "height": geometry["height"], "highlight": geometry["highlight"], "page_text": page_text, "png": png}


def _authorized_pdf(workspace, run_id, resource_id, page_index):
    if resource_id != SOURCE_ID:
        raise DocumentViewerError("resource_not_authorized")
    try:
        current, context_id = ApplicationService(workspace.paths, workspace.vault_root, None).context()
        if current.workspace_id != workspace.workspace_id:
            raise DocumentViewerError("source_binding_mismatch")
        request = make_request(context_id, run_id)
        receipt = current.read_receipt(run_id)
        wire = (json.dumps(receipt, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")
        confirmed = decode_response(wire, request)
    except (WorkspacePathError, OSError) as error:
        raise DocumentViewerError(getattr(error, "code", "filesystem_access_error")) from None
    except (TypeError, ValueError, RecursionError) as error:
        if isinstance(error, DocumentViewerError):
            raise
        code = "source_binding_mismatch" if isinstance(error, TypedIpcError) and error.code == "response_mismatch" else "receipt_invalid"
        raise DocumentViewerError(code) from None

    result = confirmed["result"]
    if (confirmed["status"] != "completed" or result["workspace_id"] != current.workspace_id
            or result["source_id"] != resource_id or result["source_sha256"] != SOURCE_SHA256
            or result["source_page"] != 1 or result["source_highlight"] != _OWN_HIGHLIGHT
            or result["display"] != "15.00"):
        raise DocumentViewerError("source_binding_mismatch")
    if page_index != result["source_page"] - 1:
        raise DocumentViewerError("page_out_of_range")
    try:
        with VaultStore(current) as store:
            matches = [version for version in store.list_versions(resource_id) if version["sha256"] == SOURCE_SHA256]
            if len(matches) != 1:
                raise DocumentViewerError("original_missing")
            data = store.read_original(SOURCE_SHA256)
    except VaultStorageError as error:
        raise DocumentViewerError(error.code) from None
    return data


def render_workspace_source(workspace: WorkspaceContext, run_id, resource_id, page_index,
                            zoom_percent, rotation, dpi_percent, crop_to_source=False, renderer=None) -> dict:
    """Resolve a successful run's own source within the current vault, then render it."""
    _validate_page_index(page_index)
    _validate_view(zoom_percent, rotation, dpi_percent, crop_to_source)
    data = _authorized_pdf(workspace, run_id, resource_id, page_index)
    if renderer is None:
        renderer = PdfiumRenderer()
    frame = renderer.render(data, page_index, zoom_percent, rotation, dpi_percent,
                            source_rect=_OWN_SOURCE_RECT, crop_to_source=crop_to_source)
    if type(frame) is not dict or frame.keys() != _RENDER_FIELDS:
        raise DocumentViewerError("render_failed")
    printed = _OWN_PRINTED_PAGE.search(frame["page_text"])
    return {"schema": VIEWER_SCHEMA, "status": "ok", "resource_id": resource_id,
            "source_sha256": SOURCE_SHA256, "page_index": page_index,
            "printed_page": printed.group(1) if printed else None, "zoom_percent": zoom_percent,
            "rotation": rotation, "dpi_percent": dpi_percent, "crop_to_source": crop_to_source,
            "table_text": _OWN_TABLE, **frame}
