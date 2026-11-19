"""Check the installed SQLite CLI plus a process stopped immediately before COMMIT."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sqlite3
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.vault_storage import DB_FILENAME, VaultStore


def crash_import(install, app_data, vault, marker):
    workspace = WorkspaceContext.open(ApplicationPaths(install, app_data), vault)
    data = b'A distinct fictional original written only in the interrupted transaction.'

    def abort_at_commit(action, operation, unused_path, unused_db, unused_trigger):
        if action == sqlite3.SQLITE_TRANSACTION and operation == 'COMMIT':
            with marker.open('x', encoding='ascii') as stream:
                stream.write('reached commit boundary\n')
                stream.flush()
                os.fsync(stream.fileno())
            os._exit(93)
        return sqlite3.SQLITE_OK

    with VaultStore(workspace) as store:
        store._connection.set_authorizer(abort_at_commit)
        store.import_revision('aborted-document', data, expected_sha256=hashlib.sha256(data).hexdigest(),
                              text='Аварийная пробная строка', extractor='crash-fixture')
    raise RuntimeError('Crash probe did not reach COMMIT')


def invoke(install, app_data, vault, cwd, *args):
    native = install / 'runtime/python.exe'
    script = install / 'app/spikes/windows_07/vault_cli.py'
    outcome = subprocess.run([str(native), '-I', '-B', '-X', 'utf8', str(script),
                              '--install-root', str(install), '--app-data', str(app_data),
                              '--vault', str(vault), *args], cwd=cwd, capture_output=True, timeout=21)
    assert not outcome.stderr, outcome.stderr.decode('utf-8', errors='replace')
    return outcome.returncode, json.loads(outcome.stdout)


def check(args, output):
    if not output.is_relative_to(ROOT / 'tmp') or output == ROOT / 'tmp':
        raise ValueError('Use a new output under this checkout’s tmp/')
    output.mkdir(parents=True)
    old = runpy.run_path(str(ROOT / 'spikes/windows_04/check_workflow.py'))
    install, app_data, cwd, vault_a, vault_b, restore_vault = (output / leaf for leaf in (
        'Установка хранилища', 'Данные ассистента', 'Пустой каталог',
        'Хранилище А', 'Хранилище Б', 'Хранилище после восстановления',
    ))
    app_data.mkdir()
    cwd.mkdir()
    old['prepare_install'](args.runtime_build.resolve(), args.demo.resolve(), install)
    for relative in ('src/financial_assistant/vault_storage.py', 'src/financial_assistant/vault_backup.py',
                     'spikes/windows_07/vault_cli.py'):
        target = install / 'app' / relative
        old['copy'](ROOT / relative, target)
        target.chmod(stat.S_IREAD)
    before_install = old['files'](install)

    pdf = args.demo.resolve() / 'own-demo-v1.pdf'
    assert old['sha'](pdf) == old['OWN_PDF_SHA']
    source_a = old['prepare_vault'](vault_a, 'vault-a', pdf, 'Отчёты/Пример.pdf')
    old['prepare_vault'](vault_b, 'vault-b', pdf, 'Страницы/Пример.pdf')
    old['prepare_vault'](restore_vault, 'vault-a', pdf, 'Отчёты/Пример.pdf')
    rc, first = invoke(install, app_data, vault_a, cwd, 'import-own')
    assert rc == 0 and first['display'] == '15.00' and first['source_page'] == 1, first
    assert first['stored']['version'] == first['stored']['revision'] == 1 and not first['stored']['duplicate']
    assert first['stored']['sha256'] == first['source_sha256'] == old['OWN_PDF_SHA']
    assert not (vault_b / DB_FILENAME).exists()
    rc, duplicate = invoke(install, app_data, vault_a, cwd, 'import-own')
    assert rc == 0 and duplicate['stored']['duplicate'] and duplicate['stored']['revision'] == 1
    rc, other = invoke(install, app_data, vault_b, cwd, 'import-own')
    assert rc == 0 and other['workspace_id'] != first['workspace_id'] and not other['stored']['duplicate']

    paths = ApplicationPaths(install, app_data)
    workspace_a = WorkspaceContext.open(paths, vault_a)
    held = source_a.with_name('own-original-held.pdf')
    assert source_a.resolve().is_relative_to(output) and held.resolve().is_relative_to(output)
    source_a.rename(held)
    try:
        with VaultStore(workspace_a) as stored_without_source:
            assert stored_without_source.read_original(old['OWN_PDF_SHA']) == pdf.read_bytes()
    finally:
        held.rename(source_a)
    with VaultStore(workspace_a) as store:
        source_data = store.read_original(old['OWN_PDF_SHA'])
        assert source_data == pdf.read_bytes()
        revision = store.import_revision('own-demo-v1', source_data, expected_sha256=old['OWN_PDF_SHA'],
                                         text='Проверочная редакция расходов', extractor='synthetic-review-v2')
        assert revision['version'] == 1 and revision['revision'] == 2 and not revision['duplicate']
        baseline = store.summary()
        assert (baseline['originals'], baseline['versions'], baseline['revisions'], baseline['fts_rows']) == (1, 1, 2, 2)
    rc, search_original = invoke(install, app_data, vault_a, cwd, 'search', '--query', 'Operating profit')
    assert rc == 0 and len(search_original['matches']) == 1 and search_original['matches'][0]['revision'] == 1
    rc, search_new = invoke(install, app_data, vault_a, cwd, 'search', '--query', 'редакция расходов')
    assert rc == 0 and len(search_new['matches']) == 1 and search_new['matches'][0]['revision'] == 2
    rc, other_search = invoke(install, app_data, vault_b, cwd, 'search', '--query', 'редакция расходов')
    assert rc == 0 and not other_search['matches']

    marker = output / 'write-interrupted.txt'
    crash = subprocess.run([str(install / 'runtime/python.exe'), '-I', '-B', str(Path(__file__).resolve()),
                            '--crash-before-commit', str(install), str(app_data), str(vault_a), str(marker)],
                           cwd=cwd, capture_output=True, timeout=20)
    assert crash.returncode == 93 and marker.read_text(encoding='ascii') == 'reached commit boundary\n', crash.stderr
    with VaultStore(workspace_a) as reopened:
        assert reopened.summary() == baseline and not reopened.list_versions('aborted-document')
        assert reopened.read_original(old['OWN_PDF_SHA']) == source_data
        assert not reopened.search('Аварийная')

    backup_path = app_data / 'Резервная копия.sqlite3'
    rc, backup = invoke(install, app_data, vault_a, cwd, 'backup', '--backup-file', str(backup_path))
    assert rc == 0 and backup_path.is_file(), backup
    rc, restore = invoke(install, app_data, restore_vault, cwd, 'restore', '--backup-file', str(backup_path))
    assert rc == 0 and restore['workspace_id'] == 'vault-a', restore
    with VaultStore(WorkspaceContext.open(paths, restore_vault)) as restored:
        assert restored.summary() == baseline and restored.read_original(old['OWN_PDF_SHA']) == source_data
        assert restored.search('редакция расходов') == search_new['matches']
    assert old['files'](install) == before_install and old['files'](cwd) == {}

    report = {'schema': 'win07-installed-storage-proof-1', 'source_sha256': old['OWN_PDF_SHA'],
              'display': first['display'], 'source_page': first['source_page'], 'independent_vaults': True,
              'idempotent_import': True, 'original_bytes_preserved': True, 'stored_bytes_survive_absent_input': True,
              'revision_1_and_2_separate': True,
              'utf8_fts': True, 'actual_worker_exit_before_commit': crash.returncode,
              'uncommitted_original_revision_and_index_absent': True, 'baseline_after_reopen': baseline,
              'backup': backup, 'restore': restore, 'restored_to_distinct_vault': True,
              'install_files_unchanged': len(before_install), 'model_calls': 0}
    (output / 'storage-proof.json').write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=True))


def main():
    if len(sys.argv) == 6 and sys.argv[1] == '--crash-before-commit':
        crash_import(*(Path(value) for value in sys.argv[2:]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', type=Path, required=True)
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check(args, args.out.resolve())


if __name__ == '__main__':
    main()
