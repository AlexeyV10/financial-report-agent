"""Generate the own two-period D0 teaching report and its admitted source data."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant.contracts_v2 import digest
from financial_assistant.fact_admission import CalculationContext


RESOURCE_ID = 'd0-own-v1'
VERSION_ID = 'd0-own-v1-report'
ORG_ID = 'd0_own_group'
PAGE_SIZE = (460, 340)
HEADERS = (
    'OWN D0 FICTIONAL GROUP',
    'IFRS / consolidated nonfinancial group',
    'Full years: 01 Jan - 31 Dec 2025 / 2024',
    'Currency and scale: RUB million',
)
CELLS = (
    ('d0-revenue-2024', 'revenue', 'Revenue', 2024, '100', (331, 143, 388, 165)),
    ('d0-revenue-2025', 'revenue', 'Revenue', 2025, '120', (246, 143, 303, 165)),
    ('d0-operating-profit-2025', 'operating_profit', 'Operating profit', 2025, '18', (246, 116, 303, 138)),
)
SOURCE_PROVENANCE = {
    'status': 'assistant_checked',
    'method': 'Own fictional report, its currency, scale, periods and values checked against the generated page.',
    'human_reviewer': None,
}


def report_pdf():
    def text(x, y, size, value):
        escaped = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        return f'BT /F1 {size} Tf {x} {y} Td ({escaped}) Tj ET'

    drawing = [
        '0.06 0.26 0.18 rg', text(35, 300, 19, HEADERS[0]),
        '0.12 0.15 0.14 rg', *(text(35, y, 12, title) for y, title in zip((273, 251, 229), HEADERS[1:], strict=True)),
        '0.90 0.96 0.92 rg 32 175 371 27 re f', '0.12 0.15 0.14 rg',
        text(38, 184, 12, 'Metric'), text(252, 184, 12, '2025'), text(337, 184, 12, '2024'),
        '0.71 0.78 0.74 RG 32 142 m 403 142 l S 32 115 m 403 115 l S',
        text(38, 151, 12, 'Revenue'), text(38, 124, 12, 'Operating profit'),
        *(text(rect[0] + 6, rect[1] + 8, 12, value) for _, _, _, _, value, rect in CELLS),
        text(337, 124, 11, 'n/a'),
        text(35, 76, 10, 'Own teaching example. The publication date is unknown.'),
        text(35, 54, 10, 'Page 1 / Own D0 teaching example.'),
    ]
    stream = ('\n'.join(drawing) + '\n').encode('ascii')
    width, height = PAGE_SIZE
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
        (f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents 4 0 R '
         '/Resources << /Font << /F1 5 0 R >> >> >>').encode('ascii'),
        f'<< /Length {len(stream)} >>\nstream\n'.encode('ascii') + stream + b'endstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f'{index} 0 obj\n'.encode('ascii') + body + b'\nendobj\n')
    xref = len(pdf)
    pdf.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode('ascii'))
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    pdf.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode('ascii'))
    return bytes(pdf)


def full_year(year):
    return {'kind': 'duration', 'duration_type': 'full_year', 'start': f'{year}-01-01', 'end': f'{year}-12-31'}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def metadata(template, pdf):
    template_catalog = json.loads((template / 'catalog.json').read_bytes())
    if template_catalog['catalog_id'] != 'windows01-own-v1' or len(template_catalog['documents']) != 1:
        raise ValueError('The template must be the own WIN-01 demo')
    document = deepcopy(template_catalog['documents'][0])
    if document['sha256'] != 'c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451':
        raise ValueError('The template differs from the pinned own demo')
    source_sha = hashlib.sha256(pdf).hexdigest()
    document.update(document_id=RESOURCE_ID, organization_id=ORG_ID, version_id=VERSION_ID,
                    sha256=source_sha, byte_length=len(pdf), report_period=full_year(2025),
                    provenance=SOURCE_PROVENANCE)
    document['availability']['local_resource_id'] = RESOURCE_ID
    document['rights'].update(note='Own generated D0 teaching report, redistribution permitted for this fixture.',
                              checked_on='2026-11-19')
    dictionary = json.loads((template / 'dictionary.json').read_bytes())
    definitions = {metric['metric_id']: metric['definition_id'] for metric in template_catalog['metrics']}
    facts, evidence = [], []
    for fact_id, metric, row, year, raw, _ in CELLS:
        proof = dict(evidence_id=f'{fact_id}-evidence', document_id=RESOURCE_ID, version_id=VERSION_ID,
                     document_sha256=source_sha, metric_id=metric, definition_id=definitions[metric],
                     period=full_year(year), currency='RUB', scale=1000000, raw_value=raw,
                     locator=dict(kind='synthetic', record_id=fact_id, row_label=row, column_label=str(year),
                                  unit_header='RUB million'), numeric_encoding='decimal_string',
                     provenance=SOURCE_PROVENANCE)
        facts.append(dict(fact_id=fact_id, organization_id=ORG_ID, document_id=RESOURCE_ID,
                          version_id=VERSION_ID, metric_id=metric, definition_id=definitions[metric],
                          original_label=row, value=raw, currency='RUB', scale=1000000, period=full_year(year),
                          evidence_id=proof['evidence_id'], evidence_digest=digest(proof),
                          provenance=SOURCE_PROVENANCE,
                          origin_role='reported_period' if year == 2025 else 'comparative_period'))
        evidence.append(proof)
    organization = {'organization_id': ORG_ID, 'name': 'Учебная группа D0', 'aliases': ['own d0 fictional group'],
                    'consolidation': 'group', 'accounting_standards': ['IFRS']}
    catalog = dict(template_catalog, catalog_id='windows10-own-d0-v1', organizations=[organization],
                   documents=[document], facts=facts, evidence=evidence)
    admission = {
        'admission_version': '1.0', 'context_id': 'win10-own-d0-admission', 'data_origin': 'synthetic',
        'catalog_id': catalog['catalog_id'], 'resource_policy': 'required_for_real',
        'comparability_records': [],
        'component_digests': {key: digest(item) for key, item in dict(
            catalog=catalog, dictionary=dictionary, bindings=None, checks=None).items()},
    }
    manifest = {'schema': 'win10-own-fixture-1', 'resource_id': RESOURCE_ID, 'sha256': source_sha,
                'bytes': len(pdf), 'page': 1, 'cells': {fact_id: rect for fact_id, _, _, _, _, rect in CELLS},
                'headers': HEADERS}
    return catalog, dictionary, admission, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-demo', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    output = args.out.resolve()
    if not output.is_relative_to(ROOT / 'tmp') or output == ROOT / 'tmp':
        raise ValueError('The own PDF must stay in this checkout’s ignored tmp/')
    pdf = report_pdf()
    catalog, dictionary, admission, manifest = metadata(args.legacy_demo.resolve(), pdf)
    output.mkdir(parents=True)
    report = output / 'report.pdf'
    report.write_bytes(pdf)
    for name, data in (('catalog', catalog), ('dictionary', dictionary), ('admission', admission),
                       ('manifest', manifest)):
        write_json(output / f'{name}.json', data)
    for source, target in (('config.json', 'retrieval_config.json'), ('search_lexicon.json', 'search_lexicon.json')):
        shutil.copyfile(ROOT / 'data/extraction/kp3_pdf_v1' / source, output / target)
    CalculationContext(catalog, dictionary, admission, resources={RESOURCE_ID: str(report)}).validate()
    print(json.dumps({'resource_id': RESOURCE_ID, 'sha256': manifest['sha256'], 'bytes': manifest['bytes']}))


if __name__ == '__main__':
    main()
