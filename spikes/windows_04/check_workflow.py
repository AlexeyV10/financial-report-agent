"""Exercise the private path contract using staged, read-only app files and own data."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
OWN_PDF_SHA = 'c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451'
CORE = ('__init__', 'fact_admission', 'financial_calculator', 'calculation_contracts',
        'catalog', 'document_extraction', 'retrieval_v2', 'contracts_v2', 'contracts',
        'application_paths')


def sha(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def files(root):
    return {path.relative_to(root).as_posix(): sha(path)
            for path in root.rglob('*') if path.is_file()}


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def prepare_install(runtime_build, demo, install):
    manifest = json.loads((runtime_build / 'runtime-manifest.json').read_bytes())
    expected_lock = sha(ROOT / 'spikes/windows_03/runtime_lock.json')
    if manifest['lock_sha256'] != expected_lock:
        raise ValueError('Expected the locked WIN-03 runtime')
    runtime = install / 'runtime'
    shutil.copytree(runtime_build / 'runtime', runtime)
    if files(runtime) != {entry['path']: entry['sha256'] for entry in manifest['files']}:
        raise ValueError('The staged runtime differs from the verified manifest')

    app = install / 'app'
    for name in CORE:
        relative = Path('src/financial_assistant') / (name + '.py')
        copy(ROOT / relative, app / relative)
    for module in ('adapter.py', 'common.py', 'renderer.py'):
        relative = Path('spikes/windows_01') / module
        copy(ROOT / relative, app / relative)
    copy(Path(__file__).with_name('workspace_demo.py'), app / 'spikes/windows_04/workspace_demo.py')
    for name in ('manifest.json', 'catalog.json', 'dictionary.json', 'admission.json'):
        copy(demo / name, app / 'assets/demo' / name)
    for path in install.rglob('*'):
        if path.is_file():
            path.chmod(stat.S_IREAD)
    try:
        with (app / 'assets/demo/manifest.json').open('r+b'):
            pass
    except PermissionError:
        return files(install)
    raise RuntimeError('The installation fixture is writable')


def prepare_vault(root, workspace_id, pdf, relative):
    source = root / relative
    copy(pdf, source)
    marker = {'schema': 'workspace-context-1', 'workspace_id': workspace_id, 'resources': [
        {'id': 'own-demo-v1', 'path': relative, 'bytes': source.stat().st_size, 'sha256': OWN_PDF_SHA}
    ]}
    (root / 'workspace.json').write_text(json.dumps(marker, ensure_ascii=False) + '\n', encoding='utf-8')
    return source


def run(install, app_data, vault, run_id, cwd):
    result = subprocess.run([
        str(install / 'runtime/python.exe'), '-I', '-B', '-X', 'utf8',
        str(install / 'app/spikes/windows_04/workspace_demo.py'), '--install-root', str(install),
        '--app-data', str(app_data), '--vault', str(vault), '--run-id', run_id,
    ], cwd=cwd, capture_output=True, timeout=30)
    if result.stderr:
        raise RuntimeError('Native worker returned unexpected diagnostics')
    return result.returncode, json.loads(result.stdout)


def success(install, app_data, vault, run_id, cwd, workspace_id):
    rc, result = run(install, app_data, vault, run_id, cwd)
    target = vault / 'runs' / (run_id + '.json')
    assert rc == 0 and result['workspace_id'] == workspace_id, result
    assert result['source_sha256'] == OWN_PDF_SHA and result['source_page'] == 1
    assert result['display'] == '15.00' and result['financial_status'] == 'answered'
    assert json.loads(target.read_bytes()) == result
    return result


def check(runtime_build, demo, output):
    if not output.is_relative_to(ROOT / 'tmp') or output == ROOT / 'tmp':
        raise ValueError('Use a fresh output under this checkout’s tmp/')
    pdf = demo / 'own-demo-v1.pdf'
    if sha(pdf) != OWN_PDF_SHA:
        raise ValueError('Expected the pinned own fictional PDF')
    output.mkdir(parents=True)
    install = output / 'Каталог установки'
    app_data = output / 'Пользовательские данные'
    cwd = output / 'Посторонний каталог'
    cwd.mkdir()
    app_data.mkdir()
    install_before = prepare_install(runtime_build, demo, install)

    vault_a, vault_b = (output / name for name in ('Хранилище А', 'Хранилище Б'))
    prepare_vault(vault_a, 'workspace-a', pdf, 'Первичные документы/own-demo-v1.pdf')
    source_b = prepare_vault(vault_b, 'workspace-b', pdf, 'Ресурсы/Пример.pdf')
    b_before = files(vault_b)
    result_a = success(install, app_data, vault_a, 'shared-run', cwd, 'workspace-a')
    assert files(vault_b) == b_before
    a_before = files(vault_a)
    result_b = success(install, app_data, vault_b, 'shared-run', cwd, 'workspace-b')
    assert files(vault_a) == a_before

    moved = output / 'Перенесённое хранилище А'
    assert vault_a.resolve().is_relative_to(output) and moved.resolve().is_relative_to(output)
    vault_a.rename(moved)
    result_moved = success(install, app_data, moved, 'relocated-run', cwd, 'workspace-a')
    assert not vault_a.exists()
    assert all(files(moved)[name] == digest for name, digest in a_before.items())

    baseline = files(vault_b)
    away = source_b.with_name('own-fixture-held.pdf')
    assert source_b.resolve().is_relative_to(output) and away.resolve().is_relative_to(output)
    source_b.rename(away)
    assert run(install, app_data, vault_b, 'missing-run', cwd) == (3, {'error': 'source_missing'})
    away.rename(source_b)
    source_bytes = source_b.read_bytes()
    source_b.write_bytes(source_bytes[:-1] + bytes([source_bytes[-1] ^ 1]))
    assert source_b.stat().st_size == len(source_bytes)
    assert run(install, app_data, vault_b, 'changed-run', cwd) == (3, {'error': 'source_hash_mismatch'})
    source_b.write_bytes(source_bytes)
    assert files(vault_b) == baseline
    assert run(install, app_data, vault_b, 'shared-run', cwd) == (3, {'error': 'duplicate_run'})
    assert files(install) == install_before and files(vault_b) == baseline and files(cwd) == {}

    report = {'schema': 'win04-workspace-proof-1', 'workspace_a': result_a,
              'workspace_b': result_b, 'after_relocation': result_moved,
              'readonly_install_write_denied': True, 'install_files_unchanged': len(install_before),
              'cwd_files_unchanged': True, 'duplicate_run_refused_without_mutation': True,
              'missing_source': 'source_missing', 'same_length_changed_source': 'source_hash_mismatch',
              'negative_workflow_preserved_vault_files': True, 'isolated_worker': True, 'model_calls': 0}
    (output / 'workflow.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', type=Path, required=True)
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise RuntimeError('This checks Windows read-only files and a Windows runtime')
    check(args.runtime_build.resolve(), args.demo.resolve(), args.out.resolve())


if __name__ == '__main__':
    main()
