"""Focused WIN-13 table tests from independent visual geometry."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from financial_assistant.pdf_table_ir import extract_pdf_tables


def _page(index, *rows):
    lines = []
    position = 0
    for row, fields in enumerate(rows):
        top = 20 + row * 20
        spans = []
        for text, left, width in fields:
            span = {'text': text, 'bbox': [left, top, left + width, top + 9],
                    'pdf_box': [left, 391 - top, left + width, 400 - top],
                    'char_start': position, 'char_end': position + len(text)}
            spans.append(span)
            position += len(text) + 1
        lines.append({'text': ' '.join(item['text'] for item in spans),
                      'bbox': [spans[0]['bbox'][0], top, spans[-1]['bbox'][2], top + 9], 'spans': spans})
    return {'page_index': index, 'printed_page': str(index + 7), 'pdf_page_label': f'label-{index}',
            'lines': lines, 'rotation': 0, 'bounds': [0, 0, 500, 400], 'width': 500, 'height': 400}


_UNITS = [('Currency and scale: RUB million', 30, 140)]
_YEARS = [('Metric', 30, 30), ('2025', 200, 28), ('2024', 350, 28)]
_DATA = [('Revenue', 30, 45), ('(1 200,25)', 200, 52), ('+125', 350, 32)]


def _values(table):
    return [cell for row in table['rows'] for cell in row['cells'] if cell['kind'] in {'number', 'missing'}]


class PdfTableIrTest(unittest.TestCase):
    def test_signed_numeric_tokens_keep_exact_native_and_period_locations(self):
        pages = [_page(0, _UNITS, _YEARS, _DATA, [('Profit', 30, 40), ('18', 200, 16), ('n/a', 350, 24)])]
        table, = extract_pdf_tables(pages)
        self.assertFalse(table['waiting_context'])
        self.assertEqual(table['locator']['printed_page'], '7')
        self.assertEqual(table['locator']['pdf_page_label'], 'label-0')
        cells = _values(table)
        self.assertEqual([cell['numeric_lexeme'] for cell in cells], ['-1200.25', '125', '18', None])
        self.assertEqual([cell['context']['sign'] for cell in cells], ['negative', 'explicit_positive', 'unsigned', None])
        self.assertEqual([cell['context']['period_label'] for cell in cells], ['2025', '2024', '2025', '2024'])
        self.assertEqual(cells[0]['text'], '(1 200,25)')
        self.assertEqual(cells[0]['locator']['pdf_box'], pages[0]['lines'][2]['spans'][1]['pdf_box'])
        self.assertEqual(cells[0]['locator']['char_end'], pages[0]['lines'][2]['spans'][1]['char_end'])
        self.assertEqual(cells[0]['context']['period_locator']['bbox'], pages[0]['lines'][1]['spans'][1]['bbox'])

    def test_missing_row_period_and_scale_remain_waiting(self):
        page = _page(0, [('RUB', 30, 28)], [('120', 200, 22), ('100', 350, 22)])
        table, = extract_pdf_tables([page])
        self.assertTrue(table['waiting_context'])
        for cell in _values(table):
            self.assertEqual(cell['context']['state'], 'waiting_context')
            self.assertEqual(set(cell['context']['missing']),
                             {'missing_period_header', 'missing_unit_scale', 'missing_row_header'})
            self.assertIsNone(cell['context']['row_label'])
            self.assertIsNone(cell['context']['period_label'])

    def test_merged_heading_and_inline_unit_use_observed_spans(self):
        page = _page(0, [('Financial performance', 198, 182)],
                     [_UNITS[0], *_YEARS[1:]], _DATA)
        table, = extract_pdf_tables([page])
        self.assertEqual(table['header_rows'], [1, 2])
        self.assertEqual(table['merges'], [{'page_index': 0, 'row': 1, 'start_column': 2, 'end_column': 3}])
        self.assertEqual(table['context']['pages'][0]['unit_label'], _UNITS[0][0])
        self.assertFalse(table['waiting_context'])

    def test_explicit_continuation_uses_original_page_context_only_for_same_layout(self):
        first = _page(0, _UNITS, _YEARS, _DATA)
        marker = [('Continuation of the financial table', 30, 145)]
        body = [('Profit', 30, 40), ('18', 200, 15), ('−4', 350, 15)]
        next_page = _page(1, marker, body)
        linked, = extract_pdf_tables([first, next_page])
        self.assertEqual(linked['locator']['page_indices'], [0, 1])
        self.assertEqual(linked['context']['pages'][1]['continuity'], 'explicit_continuation')
        self.assertEqual(linked['context']['pages'][1]['unit_locator']['page_index'], 0)
        self.assertEqual(_values(linked)[-1]['context']['period_locator']['page_index'], 0)
        self.assertEqual(_values(linked)[-1]['locator']['page_index'], 1)
        shifted = _page(1, marker, [body[0], ('18', 209, 15), body[2]])
        for unlinked in (shifted, _page(2, marker, body), _page(1, body)):
            _, separate = extract_pdf_tables([first, unlinked])
            self.assertTrue(separate['waiting_context'])
            self.assertIsNone(separate['context']['pages'][0]['continuity'])
            self.assertTrue(all(cell['context']['period_label'] is None for cell in _values(separate)))

    def test_repeat_rejects_incompatible_period_order_and_geometry(self):
        first = _page(0, _UNITS, _YEARS, _DATA)
        repeat = _page(1, _UNITS, _YEARS, _DATA)
        linked, = extract_pdf_tables([first, repeat])
        self.assertEqual(linked['context']['pages'][1]['continuity'], 'repeated_context')
        for header in ([('Metric', 30, 30), ('2024', 200, 28), ('2025', 350, 28)],
                       [('Metric', 30, 30), ('2025', 210, 28), ('2024', 350, 28)]):
            self.assertEqual(len(extract_pdf_tables([first, _page(1, _UNITS, header, _DATA)])), 2)

    def test_duplicate_column_candidates_do_not_receive_a_period(self):
        page = _page(0, _UNITS, _YEARS, [('Revenue', 30, 50), ('12', 195, 10), ('10', 218, 10)])
        table, = extract_pdf_tables([page])
        self.assertEqual(table['context']['missing'], ['column_layout_conflict'])
        self.assertTrue(all(cell['context']['period_label'] is None for cell in _values(table)))


if __name__ == '__main__':
    unittest.main()
