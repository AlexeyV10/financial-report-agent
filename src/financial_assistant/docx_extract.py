"""Recover literal Word paragraphs and tables from a checked OOXML package."""

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile

from .office_extraction_common import ExtractionError, MAX_CELLS, MAX_TEXT, xml_part
from .safe_import import _DYNAMIC_FIELD


_PART = "word/document.xml"
_NAMESPACES = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
)
_WRAPPERS = {"customXml", "smartTag", "sdt", "sdtContent", "ins", "moveTo"}
_INLINE_WRAPPERS = _WRAPPERS | {"r", "hyperlink"}
_TOKENS = {"t", "tab", "br", "cr", "noBreakHyphen", "softHyphen", "fldChar", "instrText", "fldSimple"}
_LITERAL_TOKENS = {"tab": "\t", "br": "\n", "cr": "\n", "noBreakHyphen": "\u2011", "softHyphen": "\u00ad"}
_ANCILLARY = re.compile(r"word/(?:header[0-9]+|footer[0-9]+|footnotes|endnotes|comments)\.xml")
_MAX_NESTING = 48


def _bounded_number(element, namespace, minimum, default):
    if element is None:
        return default
    value = element.get(namespace + "val", "")
    if not value.isascii() or not value.removeprefix("+").isdecimal():
        raise ExtractionError("docx_structure_invalid")
    if len(value) > 6:
        raise ExtractionError("extraction_limit")
    integer = int(value)
    if integer < minimum:
        raise ExtractionError("docx_structure_invalid")
    if integer > MAX_CELLS:
        raise ExtractionError("extraction_limit")
    return integer


class _Document:
    def __init__(self, body, namespace):
        self._ns = namespace
        self._paragraph_ordinals = self._ordinals(body, "p")
        self._table_ordinals = self._ordinals(body, "tbl")
        self._fields = []
        self._rows = self._grid_slots = 0
        self.paragraphs = []
        self.tables = []
        self.notes = set()

    def _ordinals(self, body, name):
        positions = {}
        for index, element in enumerate(body.iter(self._ns + name), 1):
            if index > MAX_CELLS:
                raise ExtractionError("extraction_limit")
            positions[element] = index
        return positions

    def _children(self, parent, wanted, wrappers=_WRAPPERS, depth=0):
        if depth > _MAX_NESTING:
            raise ExtractionError("extraction_limit")
        for child in parent:
            if not child.tag.startswith(self._ns):
                continue
            tag = child.tag[len(self._ns):]
            if tag in wanted:
                yield tag, child
            elif tag in wrappers:
                yield from self._children(child, wanted, wrappers, depth + 1)

    def _field_token(self, tag, element):
        self.notes.add("field_content_omitted")
        if tag == "fldSimple":
            if _DYNAMIC_FIELD.search(element.get(self._ns + "instr", "")):
                raise ExtractionError("archive_active_payload")
        elif tag == "instrText":
            if self._fields and self._fields[-1] is not None:
                self._fields[-1] += element.text or ""
                if len(self._fields[-1]) > MAX_TEXT:
                    raise ExtractionError("extraction_limit")
        else:
            marker = element.get(self._ns + "fldCharType")
            if marker == "begin":
                if len(self._fields) >= _MAX_NESTING:
                    raise ExtractionError("extraction_limit")
                self._fields.append("")
            elif marker in {"separate", "end"} and self._fields:
                command = self._fields.pop()
                if command and _DYNAMIC_FIELD.search(command):
                    raise ExtractionError("archive_active_payload")
                if marker == "separate":
                    if command is None:
                        raise ExtractionError("docx_structure_invalid")
                    self._fields.append(None)
            else:
                raise ExtractionError("docx_structure_invalid")

    def _paragraph(self, paragraph, row_locator):
        pieces = []
        length = 0
        for tag, element in self._children(paragraph, _TOKENS, _INLINE_WRAPPERS):
            if tag in {"fldChar", "instrText", "fldSimple"}:
                self._field_token(tag, element)
            elif not self._fields:
                value = (element.text or "") if tag == "t" else _LITERAL_TOKENS[tag]
                length += len(value)
                if length > MAX_TEXT:
                    raise ExtractionError("extraction_limit")
                pieces.append(value)
        text = "".join(pieces)
        locator = {"part": _PART, "paragraph": self._paragraph_ordinals[paragraph], **row_locator}
        self.paragraphs.append({"locator": locator, "text": text})
        return text

    def _properties(self, element, child, property_name):
        return element.find(self._ns + child + "/" + self._ns + property_name)

    def _merge_marker(self, cell, name):
        element = self._properties(cell, "tcPr", name)
        if element is None:
            return None
        kind = element.get(self._ns + "val", "continue")
        if kind not in {"restart", "continue"}:
            raise ExtractionError("docx_structure_invalid")
        return kind

    def _cell_contents(self, cell, locator, depth):
        paragraphs = []
        for tag, element in self._children(cell, {"p", "tbl"}):
            if tag == "p":
                paragraphs.append(self._paragraph(element, locator))
            else:
                self._table(element, depth + 1)
        text = "\n".join(paragraphs)
        if len(text) > MAX_TEXT:
            raise ExtractionError("extraction_limit")
        return {"locator": locator, "text": text or None, "kind": "text" if text else "empty"}

    def _table(self, table, depth=0):
        if depth > _MAX_NESTING:
            raise ExtractionError("extraction_limit")
        index = self._table_ordinals[table]
        locator = {"part": _PART, "table": index}
        caption = self._properties(table, "tblPr", "tblCaption")
        caption = caption.get(self._ns + "val", "") if caption is not None else ""
        if len(caption) > MAX_TEXT:
            raise ExtractionError("extraction_limit")
        result = {"name": caption or f"Таблица {index}", "locator": locator,
                  "rows": [], "merges": [], "header_rows": []}
        self.tables.append(result)
        self._table_rows(table, result, depth)
        result["merges"] = [merge for merge in result["merges"]
                            if (merge["row"], merge["column"]) != (merge["end_row"], merge["end_column"])]

    def _table_rows(self, table, result, depth):
        active_vertical = {}
        for row_number, (_, row) in enumerate(self._children(table, {"tr"}), 1):
            self._rows += 1
            if self._rows > MAX_CELLS:
                raise ExtractionError("extraction_limit")
            before = _bounded_number(self._properties(row, "trPr", "gridBefore"), self._ns, 0, 0)
            after = _bounded_number(self._properties(row, "trPr", "gridAfter"), self._ns, 0, 0)
            column = 1 + before
            header = self._properties(row, "trPr", "tblHeader")
            if header is not None:
                value = header.get(self._ns + "val", "true")
                if value in {"true", "1", "on"}:
                    result["header_rows"].append(row_number)
                elif value not in {"false", "0", "off"}:
                    raise ExtractionError("docx_structure_invalid")
            cells, next_vertical = [], {}
            horizontal = None
            for ordinal, (_, cell) in enumerate(self._children(row, {"tc"}), 1):
                span = _bounded_number(self._properties(cell, "tcPr", "gridSpan"), self._ns, 1, 1)
                self._grid_slots += span
                if self._grid_slots > MAX_CELLS or column + span - 1 > MAX_CELLS:
                    raise ExtractionError("extraction_limit")
                horizontal = self._cell_merges(
                    cell, row_number, column, span, horizontal, active_vertical, next_vertical, result["merges"],
                )
                locator = dict(result["locator"], row=row_number, cell=ordinal, column=column)
                cells.append(dict(self._cell_contents(cell, locator, depth), column_span=span))
                column += span
            if column - 1 + after > MAX_CELLS:
                raise ExtractionError("extraction_limit")
            active_vertical = next_vertical
            result["rows"].append({"row": row_number, "cells": cells})

    def _cell_merges(self, cell, row, column, span, horizontal, active_vertical, next_vertical, merges):
        vertical, legacy = self._merge_marker(cell, "vMerge"), self._merge_marker(cell, "hMerge")
        if legacy is not None and (vertical is not None or span != 1):
            raise ExtractionError("docx_merge_unsupported")
        last_column = column + span - 1
        new_range = {"row": row, "column": column, "end_row": row, "end_column": last_column}
        key = (column, span)
        if legacy == "continue":
            if horizontal is None:
                raise ExtractionError("docx_structure_invalid")
            horizontal["end_column"] = last_column
            return horizontal
        if legacy == "restart":
            merges.append(new_range)
            return new_range
        if vertical == "continue":
            if key not in active_vertical:
                raise ExtractionError("docx_structure_invalid")
            merge = active_vertical[key]
            merge["end_row"] = row
            next_vertical[key] = merge
        elif vertical == "restart" or span > 1:
            merges.append(new_range)
            if vertical == "restart":
                next_vertical[key] = new_range
        return None

    def read(self, body):
        for tag, element in self._children(body, {"p", "tbl"}):
            if tag == "p":
                self._paragraph(element, {})
            else:
                self._table(element)
        if self._fields:
            raise ExtractionError("docx_structure_invalid")


def extract_docx(data: bytes) -> dict:
    """Read the main part after the caller has revalidated the complete captured DOCX."""
    try:
        with ZipFile(BytesIO(data)) as archive:
            root = xml_part(archive, _PART)
            has_ancillary = any(_ANCILLARY.fullmatch(name) for name in archive.namelist())
    except (BadZipFile, TypeError):
        raise ExtractionError("office_part_invalid") from None
    namespace = next(("{" + name + "}" for name in _NAMESPACES if root.tag == "{" + name + "}document"), None)
    if namespace is None:
        raise ExtractionError("docx_structure_invalid")
    bodies = root.findall(namespace + "body")
    if len(bodies) != 1:
        raise ExtractionError("docx_structure_invalid")
    body, = bodies
    document = _Document(body, namespace)
    document.read(body)
    if has_ancillary:
        document.notes.add("ancillary_parts_omitted")
    return {"encoding": None, "delimiter": None, "tables": document.tables,
            "paragraphs": document.paragraphs, "notes": sorted(document.notes)}
