"""Exercise the Unicode native importer and verify its committed asset bytes."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
from pathlib import Path
import runpy
import subprocess
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.vault_storage import DB_FILENAME, VaultStore, verify_storage_file


CSV_SAMPLE = 'Период;Строка;Значение\n2025;Выручка;120\n2025;Прибыль;18\n2024;Выручка;100\n'.encode('utf-8')


def write_marker(vault, name):
    vault.mkdir()
    (vault / 'workspace.json').write_text(json.dumps({
        'schema': 'workspace-context-1', 'workspace_id': name, 'resources': [],
    }) + '\n', encoding='utf-8')


def read_json(path):
    return json.loads(path.read_bytes())


def invoke(installation, app_data, cwd, vault, input_file):
    process = subprocess.run([
        str(installation / 'runtime/python.exe'), '-I', '-B', '-X', 'utf8',
        str(installation / 'app/spikes/windows_11/import_cli.py'), '--install-root', str(installation),
        '--app-data', str(app_data), '--vault', str(vault), '--path', str(input_file),
    ], cwd=cwd, timeout=25, capture_output=True)
    assert process.returncode == 0 and process.stderr == b'', process.returncode
    assert process.stdout.count(b'\n') == 1 and process.stdout.endswith(b'\n') and b'\r' not in process.stdout
    frame = json.loads(process.stdout)
    assert frame['schema'] == 'win11-import-1'
    return frame


def check(args):
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / 'tmp') or out == ROOT / 'tmp':
        raise ValueError('Use a fresh test path below the checkout’s ignored tmp/')
    out.mkdir(parents=True)
    install, app_data, cwd, vault_a, vault_b = [out / name for name in (
        'Установка', 'Данные', 'Рабочий каталог', 'Хранилище А', 'Хранилище Б',
    )]
    app_data.mkdir()
    cwd.mkdir()
    write_marker(vault_a, 'win11-vault-a')
    write_marker(vault_b, 'win11-vault-b')
    native = runpy.run_path(str(ROOT / 'spikes/windows_08/check_shell.py'))
    prior, executable = native['stage_install'](args.runtime_build, args.legacy_demo, install)
    install_before = prior['files'](install)

    malformed = BytesIO()
    with ZipFile(malformed, 'w') as archive:
        archive.writestr('../synthetic-above.txt', 'own QA marker')
    invalid = out / 'Неподходящий архив.xlsx'
    invalid.write_bytes(malformed.getvalue())
    rejection = invoke(install, app_data, cwd, vault_b, invalid)
    assert rejection['status'] == 'rejected' and rejection['workspace_id'] == 'win11-vault-b'
    assert rejection['file_state'] == 'rejected' and rejection['error'] == 'archive_path_invalid'
    assert rejection['asset_sha256'] is None and rejection['file_type'] is None and rejection['byte_count'] is None
    assert rejection['extraction_state'] == rejection['semantic_state'] == 'not_started'
    assert not (vault_b / DB_FILENAME).exists()
    assert not (out / 'synthetic-above.txt').exists()

    fixture = out / 'Таблица с другим расширением.txt'
    fixture.write_bytes(CSV_SAMPLE)
    command = [str(executable), '--app-data', str(app_data), '--vault-a', str(vault_a),
               '--vault-b', str(vault_b), '--probe-import', str(fixture)]
    process = subprocess.run(command, cwd=cwd, capture_output=True, timeout=90)
    receipt_path = app_data / 'win11-import-probe.json'
    assert receipt_path.is_file(), process.returncode
    receipt = read_json(receipt_path)
    assert process.returncode == 0 and receipt['ok'], (receipt.get('incomplete_step'), receipt.get('failure_error'))
    assert receipt['schema'] == 'win11-import-probe-1'
    assert receipt['asset_sha256'] == hashlib.sha256(CSV_SAMPLE).hexdigest()
    assert receipt['file_type'] == 'csv' and receipt['byte_count'] == len(CSV_SAMPLE)
    assert receipt['captured_status'] == 'captured' and receipt['duplicate_status'] == 'duplicate'
    assert receipt['duplicate_same_asset'] and receipt['cleared_on_workspace_switch']
    assert receipt['file_state'] == 'accepted' and receipt['extraction_state'] == 'pending'
    assert receipt['semantic_state'] == 'not_reviewed'
    assert not (vault_b / DB_FILENAME).exists()

    def capture_other():
        return invoke(install, app_data, cwd, vault_b, fixture)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [future.result() for future in (pool.submit(capture_other), pool.submit(capture_other))]
    assert sorted(row['status'] for row in responses) == ['captured', 'duplicate']
    assert all(row['asset_sha256'] == receipt['asset_sha256'] and row['workspace_id'] == 'win11-vault-b'
               for row in responses)
    paths = ApplicationPaths(install, app_data)
    for selected in (vault_a, vault_b):
        context = WorkspaceContext.open(paths, selected)
        with VaultStore(context) as store:
            assert store.read_original(receipt['asset_sha256']) == CSV_SAMPLE
            assert store.search('Выручка') == []
            assert store.summary() == dict(documents=0, originals=0, versions=0, revisions=0, fts_rows=0)
        integrity = verify_storage_file(selected / DB_FILENAME, context.workspace_id)
        assert integrity['schema_version'] == 2 and integrity['captures'] == 1

    assert prior['files'](install) == install_before and prior['files'](cwd) == {}
    proof = {'schema': 'win11-native-import-proof-1', 'native': receipt,
             'archive_path_denied_before_vault_write': True, 'publication_or_admission_from_import': False,
             'concurrent_same_digest_single_capture': True, 'independent_vaults': True,
             'original_bytes_compared': True, 'indexed_rows_each': 0, 'install_files_unchanged': len(install_before)}
    (out / 'import-proof.json').write_text(json.dumps(proof, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(proof, indent=2, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', required=True, type=Path)
    parser.add_argument('--legacy-demo', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    check(parser.parse_args())


if __name__ == '__main__':
    main()
