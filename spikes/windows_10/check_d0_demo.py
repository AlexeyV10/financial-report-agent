"""Read the generated own primary PDF and independently verify the D0 evidence cells."""

import argparse
import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    'd0-revenue-2024': ('Revenue', 2024, '100'),
    'd0-revenue-2025': ('Revenue', 2025, '120'),
    'd0-operating-profit-2025': ('Operating profit', 2025, '18'),
}


def read_json(path):
    return json.loads(path.read_bytes())


def check_primary(pack):
    manifest = read_json(pack / 'manifest.json')
    catalog = read_json(pack / 'catalog.json')
    pdf = (pack / 'report.pdf').read_bytes()
    digest = hashlib.sha256(pdf).hexdigest()
    assert manifest['sha256'] == digest and manifest['bytes'] == len(pdf)
    assert manifest['resource_id'] == 'd0-own-v1' and manifest['page'] == 1
    assert set(manifest['cells']) == set(EXPECTED)
    (source,) = catalog['documents']
    assert source['document_id'] == manifest['resource_id'] and source['sha256'] == digest
    assert source['version_id'] == 'd0-own-v1-report' and source['pdf_pages'] == 1
    assert source['accounting_standard'] == 'IFRS' and catalog['organizations'][0]['consolidation'] == 'group'
    assert source['publication']['precision'] == 'unknown' and source['publication']['value'] is None
    assert source['fetched_at'] is None and source['signed_on'] is None
    assert source['provenance']['human_reviewer'] is None
    facts = {row['fact_id']: row for row in catalog['facts']}
    evidence = {row['evidence_id']: row for row in catalog['evidence']}
    with pdfium.PdfDocument(pdf) as document:
        assert len(document) == 1
        page = document[0]
        try:
            assert page.get_size() == (460.0, 340.0)
            text = page.get_textpage()
            try:
                body = text.get_text_bounded()
                for header in ('OWN D0 FICTIONAL GROUP', 'IFRS / consolidated nonfinancial group',
                               'Full years: 01 Jan - 31 Dec 2025 / 2024', 'Currency and scale: RUB million',
                               'Page 1 / Own D0 teaching example.'):
                    assert header in body
                for x, year in ((246, 2025), (331, 2024)):
                    assert text.get_text_bounded(x, 173, x + 57, 203).strip() == str(year)
                for fact_id, (label, year, raw) in EXPECTED.items():
                    fact = facts[fact_id]
                    proof = evidence[fact['evidence_id']]
                    rect = manifest['cells'][fact_id]
                    assert text.get_text_bounded(*rect).strip() == raw
                    assert text.get_text_bounded(30, rect[1], 165, rect[3]).strip() == label
                    assert fact['value'] == proof['raw_value'] == raw
                    assert fact['currency'] == proof['currency'] == 'RUB'
                    assert fact['scale'] == proof['scale'] == 1000000
                    assert fact['period']['start'] == f'{year}-01-01' and fact['period']['end'] == f'{year}-12-31'
                    assert proof['period'] == fact['period'] and proof['document_sha256'] == digest
                    assert proof['locator']['column_label'] == str(year) and proof['locator']['row_label'] == label
            finally:
                text.close()
        finally:
            page.close()
    return {'schema': 'win10-own-d0-primary-check-1', 'source_sha256': digest, 'source_bytes': len(pdf),
            'page': 1, 'precise_pdf_cells_checked': len(EXPECTED), 'same_group_and_ifrs': True,
            'currency': 'RUB', 'scale': 1000000, 'publication': 'unknown', 'human_reviewed': False,
            'expected_display': {'direct': '120', 'delta': '20', 'relative': '20.00', 'scale': '0.12', 'margin': '15.00'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    options = parser.parse_args()
    output = options.out.resolve()
    if not output.is_relative_to(ROOT / 'tmp') or output.is_dir():
        raise ValueError('Write the receipt inside the ignored tmp/')
    result = check_primary(options.pack.resolve())
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
