"""Test the installed digital PDF pipeline against independently placed synthetic text."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.vault_storage import VaultStore
from own_pdf_fixtures import own_paginated_pdf, own_scan_pdf, own_unlabeled_pdf


def inspect(data):
    pages = data['pages']
    assert len(pages) == 2 and [page['page_index'] for page in pages] == [0, 1]
    assert [page['printed_page'] for page in pages] == ['7', '8']
    labels = [page['pdf_page_label'] for page in pages]
    assert all(labels) and labels != ['7', '8'] and len(set(labels)) == 2
    assert all(page['text_status'] == 'digital' for page in pages)
    assert data['provenance']['table_rules'] == 'win13-pdf-tables-1'
    for key in ('parser', 'config', 'environment'):
        fingerprint = dict(data['provenance'][key])
        claimed = fingerprint.pop('sha256')
        wire = json.dumps(fingerprint, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
        assert hashlib.sha256(wire).hexdigest() == claimed
    table, = data['tables']
    assert table['locator']['page_indices'] == [0, 1] and not table['waiting_context']
    contexts = table['context']['pages']
    assert contexts[0]['period_labels'] == ['2025', '2024']
    assert contexts[1]['period_labels'] == ['2025', '2024'] and contexts[1]['continuity']
    assert all('RUB million' in item['unit_label'] for item in contexts)
    cells = [cell for row in table['rows'] for cell in row['cells'] if cell['kind'] == 'number']
    negative = next(cell for cell in cells if cell['numeric_lexeme'] and cell['numeric_lexeme'].startswith('-'))
    assert negative['text'].startswith(('-', '('))
    for cell in cells:
        location = cell['locator']
        page = pages[location['page_index']]
        expected_x = {2: 315, 3: 420}[location['column']]
        box = location['pdf_box']
        assert expected_x - 2 <= box[0] <= expected_x + 5 and box[0] < box[2] <= expected_x + 65
        assert 0 <= location['char_start'] < location['char_end']
        assert any(span['char_start'] == location['char_start'] and span['char_end'] == location['char_end']
                   and span['pdf_box'] == box and span['text'] == cell['text']
                   for line in page['lines'] for span in line['spans'])
        assert cell['context']['row_label'] and cell['context']['unit_label']
        assert cell['context']['period_label'] == {2: '2025', 3: '2024'}[location['column']]
    return {'pages': len(pages), 'tables': 1, 'cells_with_exact_source': len(cells),
            'printed_pages': ['7', '8'], 'pdf_page_labels': labels,
            'continuation_basis': contexts[1]['continuity'], 'negative_lexeme': negative['numeric_lexeme'],
            'merged_header_candidates': len(table['merges']), 'parser': data['provenance']['parser'],
            'fingerprints_verified': True}


def check(args):
    importer = runpy.run_path(str(ROOT / 'spikes/windows_11/check_import.py'))
    native = runpy.run_path(str(ROOT / 'spikes/windows_08/check_shell.py'))
    worker = runpy.run_path(str(ROOT / 'spikes/windows_12/check_extract.py'))['run_worker']
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / 'tmp') or out == ROOT / 'tmp':
        raise ValueError('Use a fresh path under ignored tmp/')
    out.mkdir(parents=True)
    install, app_data, cwd, primary, other = [out / name for name in (
        'Установка', 'Данные', 'Пустой каталог', 'Проект А', 'Проект Б',
    )]
    app_data.mkdir()
    cwd.mkdir()
    importer['write_marker'](primary, 'win13-a')
    importer['write_marker'](other, 'win13-b')
    base, executable = native['stage_install'](args.runtime_build, args.legacy_demo, install)
    program = base['files'](install)

    paginated, unlabeled, scan = own_paginated_pdf(), own_unlabeled_pdf(), own_scan_pdf()
    chosen = out / 'Собственный пример.pdf'
    chosen.write_bytes(paginated)
    command = [str(executable), '--app-data', str(app_data), '--vault-a', str(primary),
               '--vault-b', str(other), '--probe-pdf-ir', str(chosen)]
    process = subprocess.run(command, cwd=cwd, capture_output=True, timeout=90)
    receipt_path = app_data / 'win13-pdf-ir-probe.json'
    assert receipt_path.is_file(), process.returncode
    proof = json.loads(receipt_path.read_bytes())
    assert process.returncode == 0 and proof['ok'], (proof['incomplete_step'], proof['failure_error'])
    assert proof['locator_verified'] and proof['same_preview'] and proof['scope_cleared']
    assert proof['extraction_status'] == 'extracted' and proof['reused_status'] == 'reused'
    assert proof['semantic_state'] == 'not_reviewed'

    digest = proof['asset_sha256']
    assert digest == hashlib.sha256(paginated).hexdigest()
    saved_path = primary / 'runs' / f'win13-pdf-ir-v1-{digest}.json'
    saved = saved_path.read_bytes()
    artifact = json.loads(saved)
    assert artifact['schema'] == 'win13-digital-pdf-ir-1' and artifact['asset_sha256'] == digest
    assert artifact['workspace_id'] == 'win13-a' and artifact['semantic_state'] == 'not_reviewed'
    measured = inspect(artifact['data'])
    code, frame = worker(install, app_data, cwd, primary, digest)
    assert code == 0 and frame['status'] == 'reused' and saved_path.read_bytes() == saved
    assert frame['preview'][0].startswith('PDF · страница 1 · ')
    code, denied = worker(install, app_data, cwd, other, digest)
    assert code == 3 and denied['preview'] == [] and denied['asset_sha256'] is None
    code, declined = worker(install, app_data, cwd, primary, digest, '--export-csv')
    assert code == 3 and declined['error'] == 'pdf_table_export_unavailable'

    extras = {}
    for key, contents in (('missing', unlabeled), ('scan', scan)):
        source = out / f'{key}.pdf'
        source.write_bytes(contents)
        captured = importer['invoke'](install, app_data, cwd, primary, source)
        assert captured['status'] == 'captured' and captured['file_type'] == 'pdf'
        asset = captured['asset_sha256']
        assert asset == hashlib.sha256(contents).hexdigest()
        receipt = primary / 'runs' / f'win13-pdf-ir-v1-{asset}.json'
        if key == 'missing':
            code, declined = worker(install, app_data, cwd, primary, asset, '--export-csv')
            assert code == 3 and declined['error'] == 'pdf_table_export_unavailable' and not receipt.exists()
        code, result = worker(install, app_data, cwd, primary, asset)
        assert code == 0 and result['semantic_state'] == 'not_reviewed'
        if key == 'scan':
            assert result['error'] == 'pdf_ocr_pending' and result['status'] == 'unsupported'
            assert result['extraction_state'] == 'pending' and not result['preview'] and not receipt.exists()
        else:
            assert result['status'] == 'extracted'
            waiting = json.loads(receipt.read_bytes())['data']
            assert waiting['pages'][0]['printed_page'] is None
            assert waiting['pages'][0]['pdf_page_label'] == 'Unlabeled-A'
            assert waiting['tables'] and all(table['waiting_context'] for table in waiting['tables'])
            assert {'missing_unit_header', 'missing_period_header'}.issubset(waiting['tables'][0]['context']['missing'])
        extras[key] = {'asset_sha256': asset, 'status': result['extraction_state'], 'error': result['error']}
    workspace = WorkspaceContext.open(ApplicationPaths(install, app_data), primary)
    with VaultStore(workspace) as store:
        assert store.summary()['fts_rows'] == 0
        for asset, original in ((digest, paginated), (extras['missing']['asset_sha256'], unlabeled),
                                (extras['scan']['asset_sha256'], scan)):
            assert store.read_original(asset) == original
            capture = store.get_capture(asset)
            assert capture['file_type'] == 'pdf' and capture['byte_count'] == len(original)
    assert base['files'](install) == program and base['files'](cwd) == {}
    result = {'schema': 'win13-digital-pdf-proof-1', 'native': proof, 'digital': measured, 'extras': extras,
              'cross_vault_refused': True, 'pdf_export_refused': True, 'archive_bytes_unchanged': True,
              'indexed_rows': 0, 'program_hashes_unchanged': len(program)}
    wire = json.dumps(result, indent=2) + '\n'
    (out / 'pdf-ir-proof.json').write_text(wire, encoding='utf-8')
    print(wire, end='')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', type=Path, required=True)
    parser.add_argument('--legacy-demo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    check(parser.parse_args())


if __name__ == '__main__':
    main()
