"""Literal CSV and TXT extraction with physical source positions."""

import csv
from io import StringIO
import re
import unicodedata

from .office_extraction_common import ExtractionError, MAX_CELLS, MAX_TEXT
from .safe_import import ImportValidationError, _csv_delimiter, _decode_text


_DECIMAL = re.compile(r'([+-]?)([0-9]+|[0-9]{1,3}(?: [0-9]{3})+)(?:[.,]([0-9]+))?')


def _numeric_lexeme(raw):
    value = raw.strip().replace('\u00a0', ' ').replace('\u202f', ' ').replace('\u2212', '-')
    parentheses = value.startswith('(') and value.endswith(')')
    if parentheses:
        value = value[1:-1].strip()
    match = _DECIMAL.fullmatch(value)
    if not match:
        return None
    sign, integer, fraction = match.groups()
    if parentheses and sign:
        return None
    sign = '-' if parentheses or sign == '-' else ''
    precise = integer.replace(' ', '')
    return sign + precise + ('.' + fraction if fraction is not None else '')


def _check_length(text):
    if len(text) > MAX_TEXT:
        raise ExtractionError('extraction_limit')
    return text


def _csv_table(text, delimiter):
    reader = csv.reader(StringIO(text, newline=''), delimiter=delimiter, strict=True)
    rows = []
    width = count = end = 0
    try:
        for fields in reader:
            first_line = end + 1
            end = reader.line_num
            if not fields:
                continue
            if width == 0:
                width = len(fields)
            if len(fields) > width:
                raise ExtractionError('csv_inconsistent_width')
            count += width
            if count > MAX_CELLS:
                raise ExtractionError('extraction_limit')
            row = len(rows) + 1
            cells = []
            for column in range(1, width + 1):
                value = _check_length(fields[column - 1]) if column <= len(fields) else None
                number = _numeric_lexeme(value) if value is not None else None
                if value is None:
                    kind = 'missing'
                elif value == '':
                    kind = 'blank'
                else:
                    kind = 'number' if number is not None else 'text'
                cells.append({
                    'locator': {'row': row, 'column': column, 'first_line': first_line, 'last_line': end},
                    'text': value, 'kind': kind, 'numeric_lexeme': number,
                })
            rows.append({'row': row, 'cells': cells})
    except csv.Error:
        raise ExtractionError('csv_invalid') from None
    return {'name': 'CSV', 'locator': {'document': 'csv'}, 'rows': rows,
            'merges': [], 'header_rows': [1] if rows else []}


def extract_text(data, file_type):
    try:
        text, encoding = _decode_text(data)
    except ImportValidationError as error:
        raise ExtractionError(error.code) from None
    if file_type == 'csv':
        delimiter = _csv_delimiter(text)
        if delimiter is None:
            raise ExtractionError('csv_dialect_unknown')
        return {'encoding': encoding, 'delimiter': delimiter, 'tables': [_csv_table(text, delimiter)],
                'paragraphs': [], 'notes': ['numeric_lexemes_unreviewed', 'first_csv_row_header_candidate']}
    if file_type != 'txt':
        raise ExtractionError('unsupported_extraction_type')
    paragraphs = []
    for number, line in enumerate(StringIO(text, newline=None), start=1):
        if number > MAX_CELLS:
            raise ExtractionError('extraction_limit')
        paragraphs.append({'text': _check_length(line.removesuffix('\n')), 'locator': {'line': number}})
    return {'encoding': encoding, 'delimiter': None, 'tables': [], 'paragraphs': paragraphs, 'notes': []}


def csv_export(table):
    """Write a CSV table as literal cells. Formula-looking text is escaped."""
    buffer = StringIO(newline='')
    writer = csv.writer(buffer, delimiter=';', lineterminator='\r\n')
    for row in table['rows']:
        values = []
        for cell in row['cells']:
            value = cell['text']
            if cell['kind'] == 'formula':
                formula = cell.get('formula')
                value = '=' + formula.removeprefix('=') if formula else None
            if value is None:
                value = ''
            stripped = unicodedata.normalize('NFKC', value.lstrip())
            if ((stripped.startswith(('=', '+', '-', '@')) and _numeric_lexeme(value) is None)
                    or value.startswith(('\t', '\r', '\n'))):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return buffer.getvalue().encode('utf-8-sig')
