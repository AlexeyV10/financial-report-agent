"""Conservative table candidates from positioned, digitally extracted PDF text."""

import re

from .office_extraction_common import ExtractionError, MAX_CELLS
from .text_extract import _numeric_lexeme


_YEAR = re.compile(r'(?:FY\s*)?(?:19|20)\d{2}(?:\s*г\.?)?\Z', re.I)
_PERIOD_CAPTION = re.compile(r'(?:показатели?|период|год|metric|item|period|year)\s*:?\Z', re.I)
_CURRENCY = re.compile(
    r'(?<!\w)(?:RUB|RUR|USD|EUR|CNY|руб(?:\.|л\w*)?|доллар\w*|евро|юан\w*|₽|\$|€)(?!\w)', re.I,
)
_SCALE = re.compile(
    r'(?<!\w)(?:units?|thousands?|millions?|billions?|тыс\.?|тысяч\w*|млн\.?|миллион\w*|'
    r'млрд\.?|миллиард\w*|ед\.|единиц\w*)(?!\w)', re.I,
)
_CONTINUATION = re.compile(r'^(?:продолжение|continuation|continued)\b|\b(?:продолжение|continued)\s*\)?\s*$', re.I)
_PAGE_FOOTER = re.compile(r'(?:page|страниц[аы])?\s*\d+(?:\s*(?:of|из|/)\s*\d+)?\Z', re.I)
_UNIT_PREFIX = re.compile(r'^(?:currency and scale|currency and units|валюта и масштаб|валюта и единицы)\s*:\s*', re.I)
_MISSING = {'-', '–', '—', '−', 'n/a', 'н/д'}
_INK_TOLERANCE = 2  # A glyph side bearing can move the visible box without moving its column.


def _center(span):
    box = span['bbox']
    return (box[0] + box[2]) / 2


def _unit(spans):
    text = ' '.join(span['text'].strip() for span in spans)
    currencies, scales = _CURRENCY.findall(text), _SCALE.findall(text)
    if len(text) <= 120 and len(currencies) == 1 and len(scales) <= 1:
        # A metric containing a currency name is not a unit header.
        rest = _SCALE.sub('', _CURRENCY.sub('', _UNIT_PREFIX.sub('', text))).strip(' .,:;()/')
        if rest.casefold() in {'', 'in', 'of', 'в', 'amounts in', 'all amounts in', 'суммы в', 'в валюте'}:
            return {'spans': spans, 'text': text, 'scale_observed': bool(scales)}
    return None


def _years(spans):
    split = len(spans)
    while split and _YEAR.fullmatch(spans[split - 1]['text'].strip()):
        split -= 1
    if split == len(spans):
        return None
    prefix = spans[:split]
    if prefix and not (_unit(prefix) or _PERIOD_CAPTION.fullmatch(' '.join(s['text'].strip() for s in prefix))):
        return None
    years = spans[split:]
    if len({re.search(r'\d{4}', span['text'])[0] for span in years}) != len(years):
        return None
    return prefix, years


def _data_row(spans):
    captions, values = [], []
    for span in spans:
        text = span['text'].strip()
        number = _numeric_lexeme(text)
        if number is not None or text.casefold() in _MISSING:
            values.append((span, number))
        elif values:
            return None
        else:
            captions.append(span)
    numbers = sum(number is not None for _, number in values)
    if numbers and any(char.isalpha() for span in captions for char in span['text']):
        return captions, values
    if not captions and numbers >= 2:
        return captions, values
    return None


def _page_blocks(page):
    blocks = []
    block = None
    headings, unit, continuation = [], None, False
    previous_bottom = None
    for line in sorted(page['lines'], key=lambda item: (item['bbox'][1], item['bbox'][0])):
        spans = sorted((span for span in line['spans'] if span['text'].strip()), key=lambda span: span['bbox'][0])
        if not spans:
            continue
        top, bottom = line['bbox'][1], line['bbox'][3]
        if previous_bottom is not None and top - previous_bottom > max(48, 3 * (bottom - top)):
            block = None
            headings, unit, continuation = [], None, False
        previous_bottom = bottom
        years = _years(spans)
        row = _data_row(spans)
        observed_unit = _unit(spans)
        text = ' '.join(span['text'].strip() for span in spans)
        if years:
            prefix, columns = years
            block = {'page': page, 'headings': headings, 'unit': _unit(prefix) if prefix else None,
                     'continuation': continuation, 'year_prefix': prefix, 'columns': columns, 'rows': []}
            block['unit'] = block['unit'] or unit
            blocks.append(block)
            headings, unit, continuation = [], None, False
        elif observed_unit:
            if block is not None and not block['rows']:
                block['unit'] = observed_unit
            else:
                block = None
                unit = observed_unit
        elif row:
            if block is None:
                block = {'page': page, 'headings': headings, 'unit': unit, 'continuation': continuation,
                         'year_prefix': [], 'columns': [], 'rows': []}
                blocks.append(block)
                headings, unit, continuation = [], None, False
            block['rows'].append(row)
        else:
            # A distinct line partitions candidates. Do not silently extend headers across prose.
            if block is not None and not block['rows'] and len(block['headings']) < 4 and len(text) <= 180:
                block['headings'] = [*block['headings'], spans]
            else:
                block = None
                if _CONTINUATION.search(text):
                    continuation = True
                if len(text) <= 180 and not _PAGE_FOOTER.fullmatch(text):
                    headings = [*headings[-2:], spans]
                else:
                    headings, unit, continuation = [], None, False
    return [candidate for candidate in blocks if candidate['rows']]


def _geometry(block):
    captions, values = block['rows'][0]
    if not captions:
        return None
    return captions[0]['bbox'][0], [span for span, _ in values]


def _labels(columns):
    return [span['text'].strip().casefold() for span in columns]


def _edges(spans, edge):
    return tuple(round(span['bbox'][edge], 2) for span in spans)


def _heading_name(block):
    for line in block['headings']:
        text = ' '.join(span['text'].strip() for span in line)
        if not _CONTINUATION.search(text):
            return text
    return None


def _join_basis(previous, current):
    start, end = previous['page'], current['page']
    if end['page_index'] != start['page_index'] + 1:
        return None
    if any(start.get(key) != end.get(key) for key in ('width', 'height', 'rotation', 'bounds')):
        return None
    prior_layout, next_layout = _geometry(previous), _geometry(current)
    if prior_layout is None or next_layout is None:
        return None
    label, values = prior_layout
    next_label, next_values = next_layout
    if abs(label - next_label) > _INK_TOLERANCE or len(values) != len(next_values):
        return None
    if not any(all(abs(a - b) <= _INK_TOLERANCE for a, b in zip(_edges(values, edge), _edges(next_values, edge)))
               for edge in (0, 2)):
        return None
    previous_columns = previous['columns'] or previous.get('inherited_columns', [])
    current_columns = current['columns']
    previous_unit = previous['unit'] or previous.get('inherited_unit')
    current_unit = current['unit']
    previous_name, current_name = _heading_name(previous), _heading_name(current)
    if previous_name and current_name and previous_name.casefold() != current_name.casefold():
        return None
    if not previous_columns or not previous_unit or not previous_unit['scale_observed']:
        return None
    if current_columns:
        if _labels(previous_columns) != _labels(current_columns):
            return None
        if all(_edges(previous_columns, edge) != _edges(current_columns, edge) for edge in (0, 2)):
            return None
    if current_unit and previous_unit['text'].casefold() != current_unit['text'].casefold():
        return None
    if any(_row_columns(block_values, previous_columns) != list(range(2, len(previous_columns) + 2))
           for block_values in (previous['rows'][0][1], current['rows'][0][1])):
        return None
    if current_columns and current_unit:
        return 'repeated_context'
    if current['continuation']:
        return 'explicit_continuation'
    return None


def _groups(pages):
    groups = []
    previous_was_last = False
    for page in pages:
        blocks = _page_blocks(page)
        for index, block in enumerate(blocks):
            for key in ('columns', 'unit'):
                if block[key]:
                    block[key + '_page'] = page['page_index']
            basis = _join_basis(groups[-1][-1], block) if previous_was_last and index == 0 else None
            if basis:
                prior = groups[-1][-1]
                block['inherited_columns'] = prior['columns'] or prior.get('inherited_columns', [])
                block['inherited_unit'] = prior['unit'] or prior.get('inherited_unit')
                for key in ('columns', 'unit'):
                    block.setdefault(key + '_page', prior[key + '_page'])
                block['basis'] = basis
                groups[-1].append(block)
            else:
                groups.append([block])
        previous_was_last = bool(blocks)
    return groups


def _union(spans, field):
    boxes = [span[field] for span in spans]
    return [min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes)]


def _span_locator(page_index, spans):
    return {'page_index': page_index, 'bbox': _union(spans, 'bbox'), 'pdf_box': _union(spans, 'pdf_box'),
            'char_start': min(span['char_start'] for span in spans),
            'char_end': max(span['char_end'] for span in spans)}


def _cell(page_index, row, column, spans, kind):
    locator = _span_locator(page_index, spans)
    locator.update(row=row, column=column)
    if len(spans) > 1:
        locator['parts'] = [_span_locator(page_index, [span]) for span in spans]
    text = spans[0]['text'] if len(spans) == 1 else ' '.join(s['text'].strip() for s in spans)
    return {'locator': locator, 'text': text, 'kind': kind}


def _column(span, anchors):
    distances = [min(abs(span['bbox'][0] - anchor['bbox'][0]), abs(span['bbox'][2] - anchor['bbox'][2]),
                     abs(_center(span) - _center(anchor))) for anchor in anchors]
    best = min(distances)
    tolerance = min([22, *(abs(_center(right) - _center(left)) / 3 for left, right in zip(anchors, anchors[1:]))])
    index = distances.index(best)
    center = _center(anchors[index])
    left, _, right, _ = span['bbox']
    if index and left <= (_center(anchors[index - 1]) + center) / 2:
        return None
    if index + 1 < len(anchors) and right >= (center + _center(anchors[index + 1])) / 2:
        return None
    return index + 2 if best <= tolerance and distances.count(best) == 1 else None


def _row_columns(values, periods):
    if not periods:
        return []
    assigned = [_column(span, periods) for span, _ in values]
    return assigned if None not in assigned and len(set(assigned)) == len(assigned) else []


def _header_rows(table, page_index, block):
    for line in block['headings']:
        row = len(table['rows']) + 1
        cells = []
        column = 1
        for span in line:
            start, _, end, _ = span['bbox']
            covered = [index for index, anchor in enumerate(block['columns'], 2) if start <= _center(anchor) <= end]
            if len(covered) > 1 and covered[0] >= column:
                column = covered[0]
                table['merges'].append({'page_index': page_index, 'row': row,
                                         'start_column': covered[0], 'end_column': covered[-1]})
                cells.append(_cell(page_index, row, column, [span], 'header'))
                column = covered[-1] + 1
            else:
                cells.append(_cell(page_index, row, column, [span], 'header'))
                column += 1
        table['rows'].append({'row': row, 'cells': cells})
        table['header_rows'].append(row)
    if block['columns']:
        row = len(table['rows']) + 1
        cells = []
        if block['year_prefix']:
            cells.append(_cell(page_index, row, 1, block['year_prefix'], 'header'))
        cells.extend(_cell(page_index, row, column, [span], 'header')
                     for column, span in enumerate(block['columns'], 2))
        table['rows'].append({'row': row, 'cells': cells})
        table['header_rows'].append(row)


def _record_block(table, block):
    page_index = block['page']['page_index']
    periods = block['columns'] or block.get('inherited_columns', [])
    unit = block['unit'] or block.get('inherited_unit')
    missing = []
    if not periods:
        missing.append('missing_period_header')
    if unit is None:
        missing.append('missing_unit_header')
    elif not unit['scale_observed']:
        missing.append('missing_unit_scale')
    if block['continuation'] and not block.get('basis'):
        missing.append('unproven_continuation')
    table['context']['pages'].append({
        'page_index': page_index, 'period_labels': [span['text'] for span in periods],
        'unit_label': unit['text'] if unit else None,
        'unit_locator': _span_locator(block['unit_page'], unit['spans']) if unit else None,
        'continuity': block.get('basis'), 'missing': missing.copy(),
    })
    _header_rows(table, page_index, block)
    for captions, values in block['rows']:
        row = len(table['rows']) + 1
        cells = [_cell(page_index, row, 1, captions, 'text')] if captions else []
        row_label = cells[0]['text'] if cells else None
        assigned = _row_columns(values, periods)
        gaps = [*missing]
        if not captions:
            gaps.append('missing_row_header')
        if periods and not assigned:
            gaps.append('column_layout_conflict')
        for index, (span, number) in enumerate(values):
            column = assigned[index] if assigned else index + 2
            value = _cell(page_index, row, column, [span], 'number' if number is not None else 'missing')
            value['numeric_lexeme'] = number
            period = periods[column - 2] if assigned else None
            raw = span['text'].lstrip()
            sign = None if number is None else ('negative' if number.startswith('-') else
                                               'explicit_positive' if raw.startswith('+') else 'unsigned')
            value['context'] = {'state': 'waiting_context' if gaps else 'observed_context', 'missing': gaps.copy(),
                                'row_label': row_label, 'unit_label': unit['text'] if unit else None,
                                'period_label': period['text'] if period else None,
                                'period_locator': _span_locator(block['columns_page'], [period]) if period else None,
                                'sign': sign}
            cells.append(value)
        table['rows'].append({'row': row, 'cells': cells})
        table['context']['missing'].extend(gap for gap in gaps if gap not in table['context']['missing'])


def extract_pdf_tables(pages: list) -> list[dict]:
    """Return structural table candidates. Even complete context requires fact verification."""
    result = []
    count = 0
    for group in _groups(pages):
        page = group[0]['page']
        index = page['page_index']
        indices = [block['page']['page_index'] for block in group]
        table = {'name': _heading_name(group[0]) or f'PDF table on page {index + 1}',
                 'locator': {'page_index': index, 'page_indices': indices,
                             'printed_page': page.get('printed_page'), 'pdf_page_label': page.get('pdf_page_label')},
                 'rows': [], 'merges': [], 'header_rows': [], 'context': {'missing': [], 'pages': []}}
        for block in group:
            _record_block(table, block)
        count += sum(len(row['cells']) for row in table['rows'])
        if count > MAX_CELLS:
            raise ExtractionError('extraction_limit')
        table['waiting_context'] = bool(table['context']['missing'])
        table['context']['state'] = 'waiting_context' if table['waiting_context'] else 'observed_context'
        result.append(table)
    return result
