"""Bounded, non-executing classification of a local document capture for WIN-11."""

import csv
from io import BytesIO, StringIO
import math
import os
from pathlib import Path
import re
import stat
import struct
import unicodedata
import warnings
from xml.etree import ElementTree
import zipfile
import zlib

from .application_paths import WorkspacePathError, _component, _inspect, _root
from .vault_storage import MAX_CAPTURE_BYTES


MAX_ZIP_MEMBERS = 256
MAX_ZIP_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 64 * 1024 * 1024
MAX_ZIP_RATIO = 200
MAX_ARCHIVE_DEPTH = 12
MAX_PDF_PAGES = 100
MAX_PDF_DIMENSION = 8192
MAX_IMAGE_DIMENSION = 8192
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_FRAMES = 16
MAX_IMAGE_TOTAL_PIXELS = 32_000_000
_MAX_XML_BYTES = 4 * 1024 * 1024
_MAX_CSV_SAMPLE = 65536
_PDF_HEADER = re.compile(br"%PDF-[12]\.[0-9](?:\r|\n)")
_LINK_SCHEME = re.compile(r"[a-z][a-z0-9+.-]*:", re.I)
_DYNAMIC_FIELD = re.compile(r"\b(?:DDE(?:AUTO)?|INCLUDETEXT|INCLUDEPICTURE|MACROBUTTON)\b", re.I)
_TYPE_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
_REL_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
_OOXML_PARTS = {
    "xl/workbook.xml": ("xlsx", "spreadsheetml.sheet", "workbook", "spreadsheetml"),
    "word/document.xml": ("docx", "wordprocessingml.document", "document", "wordprocessingml"),
}
_ACTIVE_PARTS = {"activex", "customui", "embeddings", "externallinks", "querytables", "webextensions"}
_ACTIVE_SUFFIXES = {".bin", ".exe", ".dll", ".com", ".scr", ".js", ".vbs", ".cmd", ".bat", ".ps1",
                    ".hta", ".lnk", ".jar", ".class", ".xlam", ".xlsm", ".docm"}


class ImportValidationError(ValueError):
    """A sanitized, stable refusal without filenames or parser diagnostics."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _local_drive(path):
    if os.name != "nt":
        return True
    if not re.fullmatch(r"[A-Za-z]:\\", path.anchor):
        return False
    # A mapped drive can look like an ordinary drive letter to pathlib.
    import ctypes
    return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(path.anchor)) in {2, 3, 5, 6}


def _path_to_capture(candidate):
    try:
        path = Path(candidate)
        if not path.is_absolute() or not _local_drive(path):
            raise ImportValidationError("invalid_source_path")
        return _root(path.parent, create_later=True) / _component(path.name)
    except (TypeError, WorkspacePathError):
        raise ImportValidationError("invalid_source_path") from None
    except OSError:
        raise ImportValidationError("source_read_failed") from None


def _source_info(path, absent):
    try:
        info = _inspect(path, missing=absent)
    except WorkspacePathError as error:
        code = "invalid_source_path" if error.code in {"path_escape", "invalid_relative_path"} else error.code
        raise ImportValidationError(code if code != "filesystem_access_error" else "source_read_failed") from None
    if not stat.S_ISREG(info.st_mode):
        raise ImportValidationError("invalid_source_path")
    return info


def _same_capture(first, second):
    return (stat.S_ISREG(second.st_mode) and os.path.samestat(first, second)
            and first.st_size == second.st_size and first.st_mtime_ns == second.st_mtime_ns)


def read_candidate(path: Path) -> bytes:
    """Capture regular local file bytes once and require the same identity before and after."""
    path = _path_to_capture(path)
    before = _source_info(path, "source_missing")
    if not before.st_size:
        raise ImportValidationError("empty_capture")
    if before.st_size > MAX_CAPTURE_BYTES:
        raise ImportValidationError("capture_too_large")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not _same_capture(before, opened):
                raise ImportValidationError("source_changed")
            data = stream.read(MAX_CAPTURE_BYTES + 1)
            after = os.fstat(stream.fileno())
    except FileNotFoundError:
        raise ImportValidationError("source_changed") from None
    except OSError:
        raise ImportValidationError("source_read_failed") from None
    current = _source_info(path, "source_changed")
    if len(data) > MAX_CAPTURE_BYTES:
        raise ImportValidationError("capture_too_large")
    if len(data) != before.st_size or not _same_capture(before, after) or not _same_capture(after, current):
        raise ImportValidationError("source_changed")
    return data


def _archive_name(info):
    name = info.orig_filename
    if "\\" in name or len(name) > 512:
        raise ImportValidationError("archive_path_invalid")
    raw = name[:-1] if name.endswith("/") else name
    parts = raw.split("/")
    if len(parts) > MAX_ARCHIVE_DEPTH:
        raise ImportValidationError("archive_limit")
    try:
        for part in parts:
            _component(part)
    except WorkspacePathError:
        raise ImportValidationError("archive_path_invalid") from None
    mode = stat.S_IFMT(info.external_attr >> 16)
    expected = stat.S_IFDIR if info.is_dir() else stat.S_IFREG
    if mode not in {0, expected} or (info.external_attr & 0x400):
        raise ImportValidationError("archive_links_forbidden")
    return raw, parts


def _preflight_directory(data):
    # Verify the compact central directory before ZipFile allocates member objects.
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        raise ImportValidationError("archive_corrupt")
    disk, start_disk, disk_members, count, size, offset, comment = struct.unpack_from("<4H2IH", data, end + 4)
    if count > MAX_ZIP_MEMBERS or disk_members > MAX_ZIP_MEMBERS:
        raise ImportValidationError("archive_limit")
    if disk or start_disk or disk_members != count or end + 22 + comment != len(data) or offset + size != end:
        raise ImportValidationError("archive_corrupt")
    cursor = offset
    for _ in range(count):
        if cursor + 46 > end or data[cursor:cursor + 4] != b"PK\x01\x02":
            raise ImportValidationError("archive_corrupt")
        name, extra, note = struct.unpack_from("<3H", data, cursor + 28)
        if not 0 < name <= 512:
            raise ImportValidationError("archive_path_invalid")
        cursor += 46 + name + extra + note
    if cursor != end:
        raise ImportValidationError("archive_corrupt")


def _archive_entries(archive):
    entries = archive.infolist()
    if len(entries) > MAX_ZIP_MEMBERS:
        raise ImportValidationError("archive_limit")
    names, prefixes, regular, parents, offsets = set(), {}, set(), set(), set()
    total = 0
    for info in entries:
        name, parts = _archive_name(info)
        for end in range(1, len(parts) + 1):
            prefix = "/".join(parts[:end])
            key = unicodedata.normalize("NFC", prefix).casefold()
            prior = prefixes.setdefault(key, prefix)
            if prefix != prior:
                raise ImportValidationError("archive_duplicate_member")
            if end < len(parts):
                parents.add(key)
        key = unicodedata.normalize("NFC", name).casefold()
        if key in names or info.header_offset in offsets:
            raise ImportValidationError("archive_duplicate_member")
        names.add(key)
        offsets.add(info.header_offset)
        if not info.is_dir():
            regular.add(key)
        elif info.file_size:
            raise ImportValidationError("archive_corrupt")
        if info.flag_bits & 0x41:
            raise ImportValidationError("archive_encrypted")
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ImportValidationError("unsupported_format")
        if (any(part.casefold() in _ACTIVE_PARTS for part in parts)
                or Path(name).suffix.casefold() in _ACTIVE_SUFFIXES
                or key == "xl/connections.xml"):
            raise ImportValidationError("archive_active_payload")
        total += info.file_size
        if (info.file_size > MAX_ZIP_MEMBER_BYTES or total > MAX_ZIP_TOTAL_BYTES
                or info.file_size > MAX_ZIP_RATIO * max(info.compress_size, 1)):
            raise ImportValidationError("archive_limit")
        yield name, info
    if regular.intersection(parents):
        raise ImportValidationError("archive_path_invalid")


def _xml(raw):
    try:
        text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    except UnicodeError:
        raise ImportValidationError("ooxml_structure_invalid") from None
    if "\0" in text:
        raise ImportValidationError("ooxml_structure_invalid")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise ImportValidationError("archive_active_payload")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        raise ImportValidationError("ooxml_structure_invalid") from None
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1].casefold()
        if name in {"oleobject", "altchunk", "externalreference", "dde"}:
            raise ImportValidationError("archive_active_payload")
        if name in {"instrtext", "fldsimple"} and (
                _DYNAMIC_FIELD.search(element.text or "") or any(
                    _DYNAMIC_FIELD.search(value) for key, value in element.attrib.items()
                    if key.rsplit("}", 1)[-1].casefold() == "instr")):
            raise ImportValidationError("archive_active_payload")
        if name == "relationship":
            mode = element.get("TargetMode", "").strip().casefold()
            target = element.get("Target", "").strip()
            if mode == "external" or target.startswith(("//", "\\")) or _LINK_SCHEME.match(target):
                raise ImportValidationError("archive_active_payload")
        content_type = element.get("ContentType", "").casefold()
        if any(marker in content_type for marker in ("macroenabled", "vbaproject", "activex", "oleobject")):
            raise ImportValidationError("archive_active_payload")
    return root


def _read_member(archive, info, xml):
    if xml and info.file_size > _MAX_XML_BYTES:
        raise ImportValidationError("archive_limit")
    chunks, total = [], 0
    with archive.open(info) as stream:
        for block in iter(lambda: stream.read(65536), b""):
            total += len(block)
            if total > info.file_size:
                raise ImportValidationError("archive_corrupt")
            if xml:
                chunks.append(block)
    if total != info.file_size:
        raise ImportValidationError("archive_corrupt")
    return _xml(b"".join(chunks)) if xml else None


def _ooxml_type(roots, names):
    candidates = _OOXML_PARTS.keys() & names
    descriptor = roots.get("[Content_Types].xml")
    rels = roots.get("_rels/.rels")
    if not candidates and descriptor is None and rels is None:
        raise ImportValidationError("unsupported_format")
    if len(candidates) != 1 or descriptor is None or rels is None:
        raise ImportValidationError("ooxml_structure_invalid")
    part, = candidates
    result, subtype, element, family = _OOXML_PARTS[part]
    if (descriptor.tag != f"{{{_TYPE_NAMESPACE}}}Types" or rels.tag != f"{{{_REL_NAMESPACE}}}Relationships"
            or roots[part].tag not in {f"{{http://schemas.openxmlformats.org/{family}/2006/main}}{element}",
                                       f"{{http://purl.oclc.org/ooxml/{family}/main}}{element}"}):
        raise ImportValidationError("ooxml_structure_invalid")
    mime = "application/vnd.openxmlformats-officedocument." + subtype + ".main+xml"
    types = [entry for entry in descriptor if entry.tag == f"{{{_TYPE_NAMESPACE}}}Override"
             and entry.get("PartName") == "/" + part]
    targets = [entry.get("Target", "").removeprefix("/") for entry in rels
               if entry.tag == f"{{{_REL_NAMESPACE}}}Relationship"
               and entry.get("Type", "").endswith("/officeDocument")]
    if len(types) != 1 or types[0].get("ContentType") != mime or targets != [part]:
        raise ImportValidationError("ooxml_structure_invalid")
    return result


def _classify_zip(data):
    _preflight_directory(data)
    roots, names = {}, set()
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = list(_archive_entries(archive))
            for name, info in entries:
                is_xml = not info.is_dir() and name.casefold().endswith((".xml", ".rels"))
                root = _read_member(archive, info, is_xml)
                if is_xml and name in {"[Content_Types].xml", "_rels/.rels", *_OOXML_PARTS}:
                    roots[name] = root
                if not info.is_dir():
                    names.add(name)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, EOFError, RuntimeError, ValueError, OSError) as error:
        if isinstance(error, ImportValidationError):
            raise
        raise ImportValidationError("archive_corrupt") from None
    return _ooxml_type(roots, names)


def _classify_pdf(data):
    if not _PDF_HEADER.match(data) or not data.rstrip(b" \t\r\n\f\0").endswith(b"%%EOF"):
        raise ImportValidationError("pdf_corrupt")
    try:
        import pypdfium2 as pdfium
        from pypdfium2 import raw
    except (ImportError, OSError):
        raise ImportValidationError("pdf_unavailable") from None

    try:
        # Only load the document and read page metrics. Do not initialize forms or actions.
        with pdfium.PdfDocument(data) as document:
            if raw.FPDF_GetSecurityHandlerRevision(document.raw) >= 0:
                raise ImportValidationError("pdf_encrypted")
            count = len(document)
            if count < 1:
                raise ImportValidationError("pdf_corrupt")
            if count > MAX_PDF_PAGES:
                raise ImportValidationError("pdf_limit")
            for index in range(count):
                size = document.get_page_size(index)
                if any(not math.isfinite(side) or side <= 0 for side in size):
                    raise ImportValidationError("pdf_corrupt")
                if max(size) > MAX_PDF_DIMENSION:
                    raise ImportValidationError("pdf_limit")
    except pdfium.PdfiumError as error:
        code = "pdf_encrypted" if error.err_code == raw.FPDF_ERR_PASSWORD else "pdf_corrupt"
        raise ImportValidationError(code) from None
    return "pdf"


def _classify_image(data, label, pillow_format):
    try:
        from PIL import Image, UnidentifiedImageError
    except (ImportError, OSError):
        raise ImportValidationError("image_unavailable") from None

    total = 0
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=[pillow_format]) as image:
                _image_pixels(image)
                image.verify()
            with Image.open(BytesIO(data), formats=[pillow_format]) as image:
                for index in range(MAX_IMAGE_FRAMES + 1):
                    try:
                        image.seek(index)
                    except EOFError:
                        break
                    total += _image_pixels(image)
                    if index >= MAX_IMAGE_FRAMES or total > MAX_IMAGE_TOTAL_PIXELS:
                        raise ImportValidationError("image_limit")
                    image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImportValidationError("image_limit") from None
    except (UnidentifiedImageError, EOFError, OSError, SyntaxError, ValueError) as error:
        if isinstance(error, ImportValidationError):
            raise
        raise ImportValidationError("image_corrupt") from None
    return label


def _image_pixels(image):
    width, height = image.size
    pixels = width * height
    if not 0 < min(width, height) or max(width, height) > MAX_IMAGE_DIMENSION or pixels > MAX_IMAGE_PIXELS:
        raise ImportValidationError("image_limit")
    return pixels


def _csv_delimiter(text):
    sample = text[:_MAX_CSV_SAMPLE]
    if len(text) > len(sample):
        sample = sample.rpartition("\n")[0]
    exact, sparse = [], []
    for delimiter in (",", ";", "\t"):
        try:
            widths = [len(row) for row in csv.reader(StringIO(sample, newline=""), delimiter=delimiter, strict=True)
                      if row and any(value.strip() for value in row)]
        except csv.Error:
            continue
        if widths and 2 <= widths[0] <= 128 and max(widths) == widths[0]:
            full = widths.count(widths[0])
            if full >= 2 and full == len(widths):
                exact.append(delimiter)
            elif full >= 2 and full * 2 >= len(widths):
                sparse.append(delimiter)
    candidates = exact or sparse
    return candidates[0] if len(candidates) == 1 else None


def _decode_text(data):
    if data.startswith((b"\xff\xfe\0\0", b"\0\0\xfe\xff")):
        raise ImportValidationError("unsupported_format")
    encoding = "utf-8"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    elif data.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    try:
        text = data.decode(encoding)
    except UnicodeError:
        raise ImportValidationError("text_invalid") from None
    if not text.strip() or any(char not in "\r\n\t" and not char.isprintable()
                               and unicodedata.category(char) != "Zs" for char in text):
        raise ImportValidationError("text_invalid")
    return text, encoding


def classify_bytes(data: bytes) -> str:
    """Return only a format label after bounded checks. Never admit a financial fact."""
    if type(data) is not bytes:
        raise ImportValidationError("invalid_capture")
    if not data:
        raise ImportValidationError("empty_capture")
    if len(data) > MAX_CAPTURE_BYTES:
        raise ImportValidationError("capture_too_large")
    if data.startswith(b"%PDF"):
        return _classify_pdf(data)
    if data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return _classify_zip(data)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _classify_image(data, "png", "PNG")
    if data.startswith(b"\xff\xd8\xff"):
        return _classify_image(data, "jpeg", "JPEG")
    if data.startswith((b"II*\0", b"MM\0*")):
        return _classify_image(data, "tiff", "TIFF")
    if data.startswith((b"MZ", b"\x7fELF", b"\x1f\x8b", b"7z\xbc\xaf'\x1c", b"\xd0\xcf\x11\xe0")):
        raise ImportValidationError("unsupported_format")
    text, _ = _decode_text(data)
    return "csv" if _csv_delimiter(text) is not None else "txt"
