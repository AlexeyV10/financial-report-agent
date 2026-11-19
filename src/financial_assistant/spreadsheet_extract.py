"""Bounded XLSX cell extraction. Formulas and caches remain unverified source data."""

from io import BytesIO
import json
import re
import zipfile
import zlib

from .office_extraction_common import ExtractionError, MAX_CELLS, MAX_TEXT, xml_part
from .vault_storage import MAX_CAPTURE_BYTES


MAX_SHEETS = 16
MAX_XLSX_OUTPUT_BYTES = 1_600_000
_SHEET_NAMESPACES = (
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://purl.oclc.org/ooxml/spreadsheetml/main",
)
_OFFICE_RELS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://purl.oclc.org/ooxml/officeDocument/relationships",
)
_PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
_UINT = re.compile(r"[0-9]{1,8}")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_EXTERNAL_FORMULA = re.compile(r"\[[0-9]+\][^!]*!|\[[^\]]+\.xl(?:s|sx|sm|sb)\]|https?://", re.I)
_ACTIVE_FORMULA = re.compile(r"\b(?:DDE(?:AUTO)?|WEBSERVICE|RTD|CALL|REGISTER(?:\.ID)?)\s*\(", re.I)
_FORMULA_ATTRS = {"t", "ref", "si", "aca", "bx", "ca", "dt2D", "dtr", "r1", "r2", "del1", "del2"}
_BUILTIN_FORMATS = {
    0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 10: "0.00%",
    11: "0.00E+00", 12: "# ?/?", 13: "# ??/??", 14: "mm-dd-yy", 15: "d-mmm-yy",
    16: "d-mmm", 17: "mmm-yy", 18: "h:mm AM/PM", 19: "h:mm:ss AM/PM", 20: "h:mm",
    21: "h:mm:ss", 22: "m/d/yy h:mm", 37: "#,##0 ;(#,##0)", 38: "#,##0 ;[Red](#,##0)",
    39: "#,##0.00;(#,##0.00)", 40: "#,##0.00;[Red](#,##0.00)", 45: "mm:ss",
    46: "[h]:mm:ss", 47: "mmss.0", 48: "##0.0E+0", 49: "@",
}


def _tag(namespace, tag):
    return f"{{{namespace}}}{tag}"


def _namespace(root, name):
    for namespace in _SHEET_NAMESPACES:
        if root.tag == _tag(namespace, name):
            return namespace
    raise ExtractionError("xlsx_structure_invalid")


def _one(parent, namespace, name, *, required=False):
    found = parent.findall(_tag(namespace, name))
    if len(found) > 1 or (required and not found):
        raise ExtractionError("xlsx_structure_invalid")
    return found[0] if found else None


def _text(value):
    if len(value) > MAX_TEXT:
        raise ExtractionError("xlsx_limit")
    return value


def _int(value, limit, error):
    if value is None or not _UINT.fullmatch(value) or int(value) > limit:
        raise ExtractionError(error)
    return int(value)


def _bool(value, *, default=False):
    if value is None:
        return default
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    raise ExtractionError("xlsx_structure_invalid")


def _coordinates(address):
    match = _CELL.fullmatch(address or "")
    if match is None:
        raise ExtractionError("xlsx_invalid_cell")
    letters, row = match.groups()
    column = 0
    for character in letters:
        column = 26 * column + ord(character) - ord("A") + 1
    if column > 16384 or int(row) > 1048576:
        raise ExtractionError("xlsx_invalid_cell")
    return int(row), column


def _range(value):
    parts = (value or "").split(":")
    if not 1 <= len(parts) <= 2:
        raise ExtractionError("xlsx_invalid_range")
    first = _coordinates(parts[0])
    last = _coordinates(parts[-1])
    if first[0] > last[0] or first[1] > last[1]:
        raise ExtractionError("xlsx_invalid_range")
    return first, last


def _workbook_relationships(archive):
    root = xml_part(archive, "xl/_rels/workbook.xml.rels")
    if root.tag != _tag(_PACKAGE_RELS, "Relationships") or len(root) > 256:
        raise ExtractionError("xlsx_invalid_relationship")
    result = {}
    for relation in root:
        identifier, relation_type, target = relation.get("Id"), relation.get("Type"), relation.get("Target")
        if relation.tag != _tag(_PACKAGE_RELS, "Relationship") or not identifier or len(identifier) > 128:
            raise ExtractionError("xlsx_invalid_relationship")
        if relation.get("TargetMode", "Internal") != "Internal":
            raise ExtractionError("xlsx_active_content")
        if identifier in result or not relation_type or not target:
            raise ExtractionError("xlsx_invalid_relationship")
        kind = next((relation_type[len(prefix) + 1:] for prefix in _OFFICE_RELS
                     if relation_type.startswith(prefix + "/")), None)
        result[identifier] = kind, target
    return result


def _part(target, kind):
    if len(target) > 512 or any(char in target for char in "\\:#?%"):
        raise ExtractionError("xlsx_invalid_relationship")
    path = target[1:] if target.startswith("/") else "xl/" + target
    if any(component in {"", ".", ".."} for component in path.split("/")):
        raise ExtractionError("xlsx_invalid_relationship")
    if kind == "worksheet":
        if not path.startswith("xl/worksheets/") or "/" in path.removeprefix("xl/worksheets/") or not path.endswith(".xml"):
            raise ExtractionError("xlsx_invalid_relationship")
    elif path != {"styles": "xl/styles.xml", "sharedStrings": "xl/sharedStrings.xml"}[kind]:
        raise ExtractionError("xlsx_invalid_relationship")
    return path


def _auxiliary(archive, relationships, kind):
    candidates = [target for relation_kind, target in relationships.values() if relation_kind == kind]
    if len(candidates) > 1:
        raise ExtractionError("xlsx_invalid_relationship")
    return xml_part(archive, _part(candidates[0], kind)) if candidates else None


def _rich_text(element, namespace):
    if element is None:
        return ""
    chunks = []
    for child in element:
        if child.tag == _tag(namespace, "t"):
            chunks.append(child.text or "")
        elif child.tag == _tag(namespace, "r"):
            chunks.extend(text.text or "" for text in child.findall(_tag(namespace, "t")))
    return _text("".join(chunks))


def _shared_strings(archive, relationships):
    root = _auxiliary(archive, relationships, "sharedStrings")
    if root is None:
        return []
    namespace = _namespace(root, "sst")
    items = root.findall(_tag(namespace, "si"))
    if len(items) > MAX_CELLS:
        raise ExtractionError("xlsx_limit")
    return [_rich_text(item, namespace) for item in items]


def _styles(archive, relationships):
    root = _auxiliary(archive, relationships, "styles")
    if root is None:
        return [(0, "General")]
    namespace = _namespace(root, "styleSheet")
    formats = dict(_BUILTIN_FORMATS)
    seen = set()
    custom = _one(root, namespace, "numFmts")
    if custom is not None:
        for entry in custom.findall(_tag(namespace, "numFmt")):
            key = _int(entry.get("numFmtId"), 65535, "xlsx_invalid_style")
            code = entry.get("formatCode")
            if key in seen or code is None:
                raise ExtractionError("xlsx_invalid_style")
            seen.add(key)
            formats[key] = _text(code)
    styles = _one(root, namespace, "cellXfs")
    result = []
    if styles is not None:
        for entry in styles.findall(_tag(namespace, "xf")):
            key = _int(entry.get("numFmtId", "0"), 65535, "xlsx_invalid_style")
            result.append((key, formats.get(key)))
            if len(result) > MAX_CELLS:
                raise ExtractionError("xlsx_limit")
    return result or [(0, "General")]


def _value(raw, cell_type, inline, strings, namespace):
    if cell_type == "inlineStr":
        if raw is not None:
            raise ExtractionError("xlsx_invalid_cell")
        return ("text", _rich_text(inline, namespace)) if inline is not None else ("blank", None)
    if inline is not None or cell_type not in {"n", "s", "str", "b", "e", "d"}:
        raise ExtractionError("xlsx_invalid_cell")
    if raw is None:
        return "blank", None
    if cell_type == "s":
        index = _int(raw, len(strings) - 1, "xlsx_invalid_shared_string")
        return "text", strings[index]
    if (cell_type == "b" and raw not in {"0", "1"}) or (cell_type == "n" and not _NUMBER.fullmatch(raw)):
        raise ExtractionError("xlsx_invalid_cell")
    return {"n": "number", "str": "text", "b": "boolean", "e": "error", "d": "date"}[cell_type], raw


def _formula_fields(formula, value_kind, value, stale):
    attributes = {key: _text(value) for key, value in formula.attrib.items()}
    if not attributes.keys() <= _FORMULA_ATTRS or attributes.get("t", "normal") not in {"normal", "array", "shared", "dataTable"}:
        raise ExtractionError("xlsx_invalid_cell")
    expression = _text(formula.text) if formula.text is not None else None
    if expression and ("|" in expression or _EXTERNAL_FORMULA.search(expression) or _ACTIVE_FORMULA.search(expression)):
        raise ExtractionError("xlsx_active_content")
    dirty = _bool(formula.get("ca")) or _bool(formula.get("aca")) or stale
    return {"formula": expression, "formula_attributes": attributes,
            "cached_value": value, "cached_kind": value_kind,
            "cache_status": "missing" if value is None else "stale" if dirty else "unverified"}


def _cell(element, namespace, sheet, part, row, strings, styles, stale):
    address = element.get("r")
    actual_row, column = _coordinates(address)
    if actual_row != row:
        raise ExtractionError("xlsx_invalid_cell")
    index = _int(element.get("s", "0"), len(styles) - 1, "xlsx_invalid_style")
    format_id, format_code = styles[index]
    node = _one(element, namespace, "v")
    raw = _text(node.text) if node is not None and node.text is not None else None
    inline = _one(element, namespace, "is")
    formula = _one(element, namespace, "f")
    value_kind, value = _value(raw, element.get("t", "n"), inline, strings, namespace)
    result = {"locator": {"sheet": sheet, "part": part, "row": row, "column": column, "address": address},
              "kind": value_kind, "text": value, "raw_value": raw, "style_index": index,
              "number_format_id": format_id, "format_code": format_code}
    if formula is not None:
        result["kind"] = "formula"
        result.update(_formula_fields(formula, value_kind, value, stale))
    return result


class _Budget:
    def __init__(self):
        self.cells = 0
        self.bytes = 0

    def add(self, item, *, cell=False):
        self.cells += cell
        self.bytes += len(json.dumps(item, ensure_ascii=True, separators=(",", ":"))) + 1
        if self.cells > MAX_CELLS or self.bytes > MAX_XLSX_OUTPUT_BYTES:
            raise ExtractionError("xlsx_limit")


def _worksheet(archive, part, sheet, visibility, strings, styles, stale, budget):
    root = xml_part(archive, part)
    namespace = _namespace(root, "worksheet")
    data = _one(root, namespace, "sheetData", required=True)
    rows, row_numbers = [], set()
    for element in data.findall(_tag(namespace, "row")):
        row = _int(element.get("r"), 1048576, "xlsx_invalid_cell")
        if not row or row in row_numbers or len(row_numbers) >= MAX_CELLS:
            raise ExtractionError("xlsx_limit" if len(row_numbers) >= MAX_CELLS else "xlsx_invalid_cell")
        row_numbers.add(row)
        cells, columns = [], set()
        for raw_cell in element.findall(_tag(namespace, "c")):
            cell = _cell(raw_cell, namespace, sheet, part, row, strings, styles, stale)
            column = cell["locator"]["column"]
            if column in columns:
                raise ExtractionError("xlsx_invalid_cell")
            columns.add(column)
            budget.add(cell, cell=True)
            cells.append(cell)
        budget.add({"row": row})
        rows.append({"row": row, "cells": cells})

    merges, seen = [], set()
    merge_cells = _one(root, namespace, "mergeCells")
    if merge_cells is not None:
        for entry in merge_cells.findall(_tag(namespace, "mergeCell")):
            ref = entry.get("ref")
            first, last = _range(ref)
            if first == last or ref in seen:
                raise ExtractionError("xlsx_invalid_range")
            if len(merges) >= MAX_CELLS:
                raise ExtractionError("xlsx_limit")
            seen.add(ref)
            budget.add(ref)
            merges.append(ref)

    headers = []
    filter_node = _one(root, namespace, "autoFilter")
    if filter_node is not None:
        first, _ = _range(filter_node.get("ref"))
        headers.append(first[0])
    else:
        for row in rows[:3]:
            populated = [cell for cell in row["cells"] if cell["kind"] != "blank"]
            if not populated or any(cell["kind"] != "text" for cell in populated):
                break
            headers.append(row["row"])
    return {"name": sheet, "locator": {"sheet": sheet, "part": part, "visibility": visibility},
            "rows": rows, "merges": merges, "header_rows": headers}


def _extract(archive):
    workbook = xml_part(archive, "xl/workbook.xml")
    namespace = _namespace(workbook, "workbook")
    relationships = _workbook_relationships(archive)
    sheets = _one(workbook, namespace, "sheets", required=True).findall(_tag(namespace, "sheet"))
    if not sheets:
        raise ExtractionError("xlsx_structure_invalid")
    if len(sheets) > MAX_SHEETS:
        raise ExtractionError("xlsx_limit")
    calculation = _one(workbook, namespace, "calcPr")
    stale = calculation is not None and (_bool(calculation.get("fullCalcOnLoad"))
        or _bool(calculation.get("forceFullCalc")) or not _bool(calculation.get("calcCompleted"), default=True)
        or calculation.get("calcMode") == "manual")
    strings = _shared_strings(archive, relationships)
    styles = _styles(archive, relationships)
    tables, seen_names, seen_parts = [], set(), set()
    budget = _Budget()
    for entry in sheets:
        name = entry.get("name")
        keys = [entry.get(_tag(prefix, "id")) for prefix in _OFFICE_RELS if entry.get(_tag(prefix, "id")) is not None]
        visibility = entry.get("state", "visible")
        if (not name or len(name) > 31 or any(character in name for character in ":\\/?*[]")
                or name.casefold() in seen_names or len(keys) != 1 or keys[0] not in relationships
                or visibility not in {"visible", "hidden", "veryHidden"}):
            raise ExtractionError("xlsx_invalid_relationship")
        kind, target = relationships[keys[0]]
        if kind != "worksheet":
            raise ExtractionError("xlsx_worksheet_unsupported")
        part = _part(target, kind)
        if part.casefold() in seen_parts:
            raise ExtractionError("xlsx_invalid_relationship")
        seen_names.add(name.casefold())
        seen_parts.add(part.casefold())
        tables.append(_worksheet(archive, part, name, visibility, strings, styles, stale, budget))
    result = {"encoding": None, "delimiter": None, "tables": tables, "paragraphs": [],
              "notes": ["formula_caches_are_not_evaluated", "header_rows_are_structural_or_initial_text_candidates"]}
    if len(json.dumps(result, ensure_ascii=True, separators=(",", ":"))) > MAX_XLSX_OUTPUT_BYTES:
        raise ExtractionError("xlsx_limit")
    return result


def extract_xlsx(data: bytes) -> dict:
    """Extract exact cell provenance from an XLSX already accepted by safe import."""
    if type(data) is not bytes or not data or len(data) > MAX_CAPTURE_BYTES:
        raise ExtractionError("xlsx_limit")
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            return _extract(archive)
    except (OSError, zipfile.BadZipFile, EOFError, RuntimeError, zlib.error):
        raise ExtractionError("xlsx_corrupt") from None
