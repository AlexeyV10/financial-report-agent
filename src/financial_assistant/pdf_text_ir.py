"""Digital PDF text and source geometry without rendering or running document actions."""

from ctypes import c_double
from dataclasses import dataclass
import hashlib
import json
from math import isfinite
import platform
import re

from .office_extraction_common import ExtractionError
from .safe_import import MAX_PDF_DIMENSION, MAX_PDF_PAGES, _PDF_HEADER
from .vault_storage import MAX_CAPTURE_BYTES


_MAX_PAGE_CHARS = 32000
_MAX_DOCUMENT_CHARS = 180000
_MAX_PAGE_SPANS = 3000
_BASELINE_TOLERANCE = 2.5
_MIN_FRAGMENT_GAP = 7.0
_FRAGMENT_GAP_RATIO = 0.8
_COLUMN_GUTTER = 12.0
_COLUMN_PROBES = (0.5, 0.45, 0.55, 0.4, 0.6)
_MIN_COLUMN_LINES = 2
_MIN_PROSE_WORDS = 3
_MIN_PROSE_LETTERS = 12
_FOOTER_FRACTION = 0.18
_FOOTER = re.compile(
    r"(?:page|страница|стр\.)\s+([0-9]{1,6}|[ivxlcdm]{1,12})"
    r"(?:\s*(?:/|of|из)\s*[0-9]{1,6}|\s*/\s*[^\W\d_][^\r\n]{0,160})?", re.IGNORECASE,
)
_WORDS = re.compile(r"[^\W\d_]+")
_LINE_BREAKS = frozenset("\r\n\v\f\u0085\u2028\u2029")
_CONFIG = {
    "profile": "win13-pdf-text-1", "max_pages": MAX_PDF_PAGES, "max_dimension": MAX_PDF_DIMENSION,
    "max_capture_bytes": MAX_CAPTURE_BYTES, "max_page_chars": _MAX_PAGE_CHARS,
    "max_document_chars": _MAX_DOCUMENT_CHARS, "max_page_spans": _MAX_PAGE_SPANS,
    "baseline_tolerance": _BASELINE_TOLERANCE, "fragment_gap": _MIN_FRAGMENT_GAP,
    "fragment_gap_ratio": _FRAGMENT_GAP_RATIO, "column_gutter": _COLUMN_GUTTER,
    "column_probes": _COLUMN_PROBES, "min_column_lines": _MIN_COLUMN_LINES,
    "min_prose_words": _MIN_PROSE_WORDS, "min_prose_letters": _MIN_PROSE_LETTERS,
    "footer_fraction": _FOOTER_FRACTION, "footer_pattern": _FOOTER.pattern,
    "bbox_space": "rotated_crop_top_left", "pdf_box_space": "native_pdf_user_space",
    "offsets": "pdfium_character_indices_half_open",
}


def _fingerprint(value):
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _provenance(pdfium):
    parser = {"name": "PDFium", "version": str(pdfium.PDFIUM_INFO),
              "binding": "pypdfium2", "binding_version": str(pdfium.PYPDFIUM_INFO)}
    config = dict(_CONFIG, column_probes=list(_CONFIG["column_probes"]))
    environment = {"python": platform.python_version(), "system": platform.system(),
                   "machine": platform.machine()}
    return {key: dict(value, sha256=_fingerprint(value))
            for key, value in (("parser", parser), ("config", config), ("environment", environment))}


def _union(boxes):
    boxes = tuple(boxes)
    return [min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes)]


def _clip(box, bounds):
    return (max(box[0], bounds[0]), max(box[1], bounds[1]),
            min(box[2], bounds[2]), min(box[3], bounds[3]))


def _valid_box(box):
    return all(isfinite(value) for value in box) and box[0] < box[2] and box[1] < box[3]


def _display_point(x, y, bounds, rotation):
    left, bottom, right, top = bounds
    if rotation == 0:
        return x - left, top - y
    if rotation == 90:
        return y - bottom, x - left
    if rotation == 180:
        return right - x, y - bottom
    return top - y, right - x


def _display_box(box, bounds, rotation):
    a, b = _display_point(box[0], box[1], bounds, rotation)
    c, d = _display_point(box[2], box[3], bounds, rotation)
    return [min(a, c), min(b, d), max(a, c), max(b, d)]


@dataclass(frozen=True, slots=True)
class _Glyph:
    index: int
    text: str
    box: tuple
    display: list
    horizontal: bool
    baseline: float


@dataclass(frozen=True, slots=True)
class _Fragment:
    span: dict
    horizontal: bool
    baseline: float


def _adjacent(previous, current):
    if (previous.horizontal != current.horizontal
            or abs(previous.baseline - current.baseline) > _BASELINE_TOLERANCE):
        return False
    axis = 0 if current.horizontal else 1
    cross = 1 - axis
    a, b = previous.display, current.display
    distance = max(a[axis] - b[axis + 2], b[axis] - a[axis + 2])
    height = max(a[cross + 2] - a[cross], b[cross + 2] - b[cross])
    return distance <= max(_MIN_FRAGMENT_GAP, _FRAGMENT_GAP_RATIO * height)


def _as_fragment(glyphs, text):
    first, last = glyphs[0], glyphs[-1]
    return _Fragment({
        "text": "".join(text), "bbox": _union(glyph.display for glyph in glyphs),
        "pdf_box": _union(glyph.box for glyph in glyphs),
        "char_start": first.index, "char_end": last.index + 1,
    }, first.horizontal, first.baseline)


def _glyph(raw, page, index, text, bounds, rotation, matrix, x, y, notes):
    box = page.get_charbox(index)
    if not _valid_box(box):
        notes.add("unlocated_pdf_character")
        return None
    clipped = _clip(box, bounds)
    if not _valid_box(clipped):
        return None
    if (not raw.FPDFText_GetMatrix(page, index, matrix)
            or not raw.FPDFText_GetCharOrigin(page, index, x, y)
            or not all(isfinite(value) for value in (matrix.a, matrix.b, x.value, y.value))):
        notes.add("unlocated_pdf_character")
        return None
    horizontal = (abs(matrix.a) >= abs(matrix.b)) == (rotation in {0, 180})
    origin = _display_point(x.value, y.value, bounds, rotation)
    return _Glyph(index, text, box, _display_box(clipped, bounds, rotation),
                  horizontal, origin[1 if horizontal else 0])


def _fragments(raw, page, count, bounds, rotation, notes):
    matrix = raw.FS_MATRIX()
    x, y = c_double(), c_double()
    words, glyphs, pending = [], [], []
    for index in range(count):
        codepoint = raw.FPDFText_GetUnicode(page, index)
        if codepoint == 0 or codepoint > 0x10ffff or 0xd800 <= codepoint <= 0xdfff:
            notes.add("unmapped_pdf_character")
            character = ""
        else:
            character = chr(codepoint)
        if character.isspace() and character not in _LINE_BREAKS:
            if glyphs:
                pending.append(character)
            continue
        glyph = None
        if character >= " " and character not in _LINE_BREAKS:
            glyph = _glyph(raw, page, index, character, bounds, rotation, matrix, x, y, notes)
        if glyphs and (glyph is None or not _adjacent(glyphs[-1], glyph)):
            yield _as_fragment(glyphs, words)
            words, glyphs, pending = [], [], []
        if glyph is not None:
            words.extend(pending)
            pending.clear()
            words.append(glyph.text)
            glyphs.append(glyph)
    if glyphs:
        yield _as_fragment(glyphs, words)


def _line(spans):
    return {"text": " ".join(span["text"] for span in spans),
            "bbox": _union(span["bbox"] for span in spans), "spans": spans}


def _baseline_lines(fragments):
    lines = []
    for horizontal in (True, False):
        current, baseline = [], None
        for fragment in sorted((item for item in fragments if item.horizontal == horizontal),
                               key=lambda item: (item.baseline, item.span["char_start"])):
            if current and fragment.baseline - baseline > _BASELINE_TOLERANCE:
                lines.append((horizontal, _ordered_line(current, horizontal)))
                current = []
            if not current:
                baseline = fragment.baseline
            current.append(fragment.span)
        if current:
            lines.append((horizontal, _ordered_line(current, horizontal)))
    return sorted(lines, key=lambda item: (item[1]["bbox"][1], item[1]["bbox"][0]))


def _ordered_line(spans, horizontal):
    return _line(sorted(spans, key=lambda span: (span["bbox"][0 if horizontal else 1], span["char_start"])))


def _prose(spans):
    tokens = _WORDS.findall(" ".join(span["text"] for span in spans))
    return len(tokens) >= _MIN_PROSE_WORDS and sum(map(len, tokens)) >= _MIN_PROSE_LETTERS


def _column_sides(line, divide):
    left, right = [], []
    for span in line["spans"]:
        start, _, end, _ = span["bbox"]
        if end <= divide - _COLUMN_GUTTER / 2:
            left.append(span)
        elif start >= divide + _COLUMN_GUTTER / 2:
            right.append(span)
        else:
            return None
    if any(side and not _prose(side) for side in (left, right)):
        return None
    return left, right


def _column_run(run):
    left = [_line(a) for _, (a, _) in run if a]
    right = [_line(b) for _, (_, b) in run if b]
    if (min(len(left), len(right)) >= _MIN_COLUMN_LINES
            and max(left[0]["bbox"][1], right[0]["bbox"][1])
            <= min(left[-1]["bbox"][3], right[-1]["bbox"][3])):
        return left + right, len(run)
    return [line for line, _ in run], 0


def _reading_order(lines, width):
    best = [line for _, line in lines]
    best_score = 0
    for ratio in _COLUMN_PROBES:
        ordered, run, score = [], [], 0
        for horizontal, line in lines:
            sides = _column_sides(line, width * ratio) if horizontal else None
            if sides is not None:
                run.append((line, sides))
                continue
            region, size = _column_run(run)
            ordered.extend(region)
            score += size
            run.clear()
            ordered.append(line)
        region, size = _column_run(run)
        ordered.extend(region)
        score += size
        if score > best_score:
            best, best_score = ordered, score
    return best, "columns" if best_score else "row_major"


def _printed_label(lines, bounds, display_height):
    candidates = set()
    native_footer = bounds[1] + (bounds[3] - bounds[1]) * _FOOTER_FRACTION
    for horizontal, line in lines:
        match = _FOOTER.fullmatch(line["text"].strip())
        if not match:
            continue
        display_middle = (line["bbox"][1] + line["bbox"][3]) / 2
        native_box = _union(span["pdf_box"] for span in line["spans"])
        native_middle = (native_box[1] + native_box[3]) / 2
        if (horizontal and display_middle >= display_height * (1 - _FOOTER_FRACTION)
                or native_middle <= native_footer):
            candidates.add(match.group(1))
    return next(iter(candidates)) if len(candidates) == 1 else None


def _read_page(pdfium, document, page_index, remaining_chars, notes):
    raw = pdfium.raw
    page = document[page_index]
    try:
        bounds, rotation = page.get_bbox(), page.get_rotation()
        if not _valid_box(bounds) or rotation not in {0, 90, 180, 270}:
            raise ExtractionError("pdf_corrupt")
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        if rotation in {90, 270}:
            width, height = height, width
        size = page.get_size()
        if any(not isfinite(side) or side <= 0 for side in size):
            raise ExtractionError("pdf_corrupt")
        if max(width, height, *size) > MAX_PDF_DIMENSION:
            raise ExtractionError("pdf_limit")

        text = page.get_textpage()
        try:
            count = text.count_chars()
            if count > min(_MAX_PAGE_CHARS, remaining_chars):
                raise ExtractionError("pdf_limit")
            fragments = []
            for fragment in _fragments(raw, text, count, bounds, rotation, notes):
                if len(fragments) >= _MAX_PAGE_SPANS:
                    raise ExtractionError("pdf_limit")
                fragments.append(fragment)
        finally:
            text.close()
    finally:
        page.close()

    try:
        label = document.get_page_label(page_index) or None
        label_bytes = len(label.encode("utf-8")) if label is not None else 0
    except UnicodeError:
        raise ExtractionError("pdf_corrupt") from None
    if label_bytes > 256 or (label is not None and "\0" in label):
        raise ExtractionError("pdf_limit")
    baseline = _baseline_lines(fragments)
    lines, order = _reading_order(baseline, width)
    if not lines:
        notes.add("ocr_pending")
    return {
        "page_index": page_index, "pdf_page_label": label,
        "printed_page": _printed_label(baseline, bounds, height), "rotation": rotation,
        "bounds": list(bounds), "width": width, "height": height, "lines": lines,
        "reading_order": order, "text_status": "digital" if lines else "ocr_pending",
    }, count


def extract_pdf_pages(data: bytes) -> dict:
    """Extract literal, located text from bounded in-memory PDF bytes."""
    if type(data) is not bytes or not data:
        raise ExtractionError("pdf_corrupt")
    if len(data) > MAX_CAPTURE_BYTES:
        raise ExtractionError("pdf_limit")
    if not _PDF_HEADER.match(data) or not data.rstrip(b" \t\r\n\f\0").endswith(b"%%EOF"):
        raise ExtractionError("pdf_corrupt")
    try:
        import pypdfium2 as pdfium
    except (ImportError, OSError):
        raise ExtractionError("pdf_unavailable") from None

    pages, notes = [], set()
    remaining = _MAX_DOCUMENT_CHARS
    try:
        with pdfium.PdfDocument(data) as document:
            if pdfium.raw.FPDF_GetSecurityHandlerRevision(document.raw) >= 0:
                raise ExtractionError("pdf_encrypted")
            if not len(document):
                raise ExtractionError("pdf_corrupt")
            if len(document) > MAX_PDF_PAGES:
                raise ExtractionError("pdf_limit")
            for index in range(len(document)):
                page, count = _read_page(pdfium, document, index, remaining, notes)
                pages.append(page)
                remaining -= count
    except pdfium.PdfiumError as error:
        code = "pdf_encrypted" if error.err_code == pdfium.raw.FPDF_ERR_PASSWORD else "pdf_corrupt"
        raise ExtractionError(code) from None

    return {"pages": pages, "provenance": _provenance(pdfium), "notes": sorted(notes)}
