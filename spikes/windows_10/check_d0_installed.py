"""Verify five calculations and source refusals through a staged Windows install."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {'direct': '120', 'delta': '20', 'relative': '20.00', 'scale': '0.12', 'margin': '15.00'}
SOURCE = 'ebabc9e49fbde3063f63f98393a271734bc16d0686ea035938ccd8d90db2caf0'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_hashes(root):
    return {path.relative_to(root).as_posix(): sha(path) for path in root.rglob('*') if path.is_file()}


def fixed_call(installation, app_data, vault, cwd, entry, *options):
    argv = [str(installation / 'runtime/python.exe'), '-I', '-B', '-X', 'utf8',
            str(installation / f'app/spikes/{entry}'), '--install-root', str(installation),
            '--app-data', str(app_data), '--vault', str(vault), *options]
    process = subprocess.run(argv, cwd=cwd, timeout=25, capture_output=True)
    assert process.returncode in {0, 3}, process.returncode
    assert not process.stderr and process.stdout.count(b'\n') == 1 and process.stdout.endswith(b'\n')
    return process.returncode, json.loads(process.stdout)


def source_path(vault):
    marker = json.loads((vault / 'workspace.json').read_bytes())
    resource, = [binding for binding in marker['resources'] if binding['id'] == 'd0-own-v1']
    target = (vault / resource['path']).resolve()
    assert target.is_relative_to(vault) and resource['sha256'] == sha(target) == SOURCE
    return target


def create_scopes(output):
    app_data = output / 'AppData'
    cwd = output / 'Пустой рабочий каталог'
    homes = output / 'workspaces'
    vault = homes / 'Учебный проект'
    other = homes / 'Второй проект'
    for path in (app_data, cwd, homes):
        path.mkdir()
    return app_data, cwd, vault, other


def run_check(installation, output):
    before = file_hashes(installation)
    app_data, cwd, vault, other = create_scopes(output)

    def d0(*options, selected=vault):
        return fixed_call(installation, app_data, selected, cwd, 'windows_10/d0_cli.py', *options)

    def calculate(operation, *options, run_id=None, selected=vault):
        return d0('--run-id', run_id or f'operations-{operation}', '--operation', operation, *options,
                  selected=selected)

    code, prepared = d0('--provision')
    assert code == 0 and prepared['operation'] == 'provision'
    source = source_path(vault)
    source_before = sha(source)
    answers = {}
    for operation, expected in EXPECTED.items():
        code, response = calculate(operation)
        assert code == 0 and response['status'] == 'answered', (operation, response.get('reason'))
        assert response['operation'] == operation and response['display'] == expected
        assert response['schema'] == 'win10-d0-1'
        assert response['source_sha256'] == SOURCE and response['source_page'] == 1
        assert {'search', 'fact_resolution', 'source_validation', 'calculation', 'result_validation'} <= set(response['trace'])
        answers[operation] = {'display': response['display'], 'trace_stages': response['trace'], 'source_page': 1}

    receipt = vault / 'runs/operations-direct.json'
    receipt_before = sha(receipt)
    duplicate_code, duplicate = calculate('direct')
    assert duplicate_code == 3 and duplicate['reason'] == 'duplicate_run' and duplicate['display'] is None
    assert sha(receipt) == receipt_before

    history_code, history = calculate('direct', '--historical', run_id='historical')
    assert history_code == 0 and history['status'] == 'blocked' and history['reason'] == 'publication_unknown'
    assert history['display'] is None and history['source_sha256'] is None
    clarify_code, clarify = calculate('direct', '--question', 'Какая выручка за 2025 год?', run_id='clarification')
    assert clarify_code == 0 and clarify['status'] == 'clarify' and clarify['reason'] == 'missing_organization'
    assert clarify['display'] is None and clarify['source_page'] is None

    def view(run_id, *, selected=vault, crop=False):
        flags = ('--crop-to-source',) if crop else ()
        return fixed_call(installation, app_data, selected, cwd, 'windows_09/viewer_cli.py',
                          '--run-id', run_id, '--resource-id', 'd0-own-v1', '--page-index', '0',
                          '--zoom-percent', '100', '--rotation', '0', '--dpi-percent', '100', *flags)

    view_code, visible = view('operations-margin')
    assert view_code == 0 and visible['status'] == 'ok' and visible['source_sha256'] == SOURCE
    assert visible['printed_page'] == '1' and visible['page_index'] == 0 and visible['highlight'] == [246, 175, 303, 224]
    assert all(label in visible['table_text'] for label in ('120', '100', '18'))
    crop_code, crop = view('operations-delta', crop=True)
    assert crop_code == 0 and crop['crop_to_source'] and crop['highlight'] == [12, 12, 154, 34]

    code, prepared_other = d0('--provision', selected=other)
    assert code == 0 and prepared_other['operation'] == 'provision'
    code, foreign = view('operations-margin', selected=other)
    assert code == 3 and foreign['error'] in {'receipt_invalid', 'receipt_missing'}
    held = output / 'held-source.private.pdf'
    assert not held.exists() and held.resolve().is_relative_to(output)
    source.rename(held)
    try:
        absent_code, absent = calculate('margin', run_id='missing-source')
        assert absent_code == 3 and absent['status'] == 'error' and absent['display'] is None, absent.get('reason')
        stored_code, stored = view('operations-margin')
        assert stored_code == 0 and stored == visible
        original = held.read_bytes()
        try:
            with source.open('xb') as corrupt_input:
                corrupt_input.write(bytes([original[0] ^ 1]) + original[1:])
            corrupt_code, corrupt = calculate('margin', run_id='corrupt-source')
            assert corrupt_code == 3 and corrupt['reason'] == 'source_hash_mismatch' and corrupt['display'] is None
        finally:
            source.unlink(missing_ok=True)
    finally:
        held.rename(source)
    assert sha(source) == source_before and file_hashes(installation) == before
    assert file_hashes(cwd) == {}
    return {'schema': 'win10-d0-installed-cli-proof-1', 'source_sha256': SOURCE, 'answers': answers,
            'unknown_publication': history['reason'], 'clarification': clarify['reason'],
            'technical_missing_source': absent['reason'], 'same_size_corruption_rejected': True,
            'duplicate_denied_without_rewriting_receipt': True, 'other_vault_rejected': True,
            'exact_archived_page_after_missing_source': True, 'program_hashes_unchanged': len(before),
            'model_calls': 0}


def check_native(installation, output):
    output.mkdir()
    app_data, cwd, vault, other = create_scopes(output)
    code, provision = fixed_call(installation, app_data, vault, cwd, 'windows_10/d0_cli.py', '--provision')
    assert code == 0 and provision['operation'] == 'provision'
    other.mkdir()
    (other / 'workspace.json').write_text(json.dumps({
        'schema': 'workspace-context-1', 'workspace_id': 'd0-empty', 'resources': [],
    }) + '\n', encoding='utf-8')
    before = file_hashes(installation)
    process = subprocess.run([
        str(installation / 'ProjectPractice-WIN10.exe'), '--app-data', str(app_data),
        '--vault-a', str(vault), '--vault-b', str(other), '--probe-d0',
    ], cwd=cwd, capture_output=True, timeout=100)
    path = app_data / 'win10-d0-probe.json'
    assert path.is_file(), process.returncode
    native = json.loads(path.read_bytes())
    assert process.returncode == 0 and native['ok'], (process.returncode, native['incomplete_step'])
    assert {row['operation']: row['display'] for row in native['operations']} == EXPECTED
    assert all(row['source_sha256'] == SOURCE and row['source_page'] == 1 for row in native['operations'])
    assert native['margin_source_opened'] and native['margin_source_alternative_verified']
    assert native['margin_source_printed_page'] == '1' and native['margin_source_highlight']
    assert native['clarify_result_empty'] and native['historical_result_empty']
    assert native['clear_on_workspace_change'] and native['documents_search_verified']
    assert file_hashes(installation) == before and file_hashes(cwd) == {}
    return native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--native', action='store_true')
    args = parser.parse_args()
    installation = args.installation.resolve()
    output = args.out.resolve()
    if (not output.is_relative_to(ROOT / 'tmp') or not installation.is_relative_to(ROOT / 'tmp')
            or output == ROOT / 'tmp' or installation.is_relative_to(output) or output.is_relative_to(installation)):
        raise ValueError('Use disjoint built and output folders below this checkout’s tmp/')
    output.mkdir(parents=True)
    report = run_check(installation, output)
    if args.native:
        report['native'] = check_native(installation, output / 'Nativetest')
    (output / 'd0-cli-proof.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
