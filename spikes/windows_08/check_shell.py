"""Build and exercise a native shell against only the project's own fixture."""

import argparse
import json
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.vault_storage import DB_FILENAME, VaultStore


MODULES = ('application_service', 'typed_ipc', 'job_supervisor', 'windows_job', 'vault_storage', 'vault_backup')
ENTRIES = ('windows_05/service_cli.py', 'windows_06/supervised_service.py', 'windows_07/vault_cli.py')


def stage(args, output):
    if not output.is_relative_to(ROOT / 'tmp') or output == ROOT / 'tmp':
        raise ValueError('Use a fresh output path under tmp/')
    output.mkdir(parents=True)
    install, app_data, cwd, vault_a, vault_b = (output / name for name in (
        'Установка оболочки', 'Данные оболочки', 'Пустой каталог', 'Проект А', 'Проект Б',
    ))
    cwd.mkdir()
    app_data.mkdir()
    old = runpy.run_path(str(ROOT / 'spikes/windows_04/check_workflow.py'))
    old['prepare_install'](args.runtime_build.resolve(), args.demo.resolve(), install)
    files = [f'src/financial_assistant/{name}.py' for name in MODULES]
    files += [f'spikes/{name}' for name in ENTRIES]
    for relative in files:
        path = install / 'app' / relative
        old['copy'](ROOT / relative, path)
        path.chmod(stat.S_IREAD)

    framework = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319'
    executable = install / 'ProjectPractice-WIN08.exe'
    args_csc = [str(framework / 'csc.exe'), '/nologo', '/target:winexe', '/platform:x64',
                '/codepage:65001', '/main:WindowsShell', '/out:' + str(executable),
                '/win32manifest:' + str(ROOT / 'spikes/windows_01/wpf.manifest')]
    for name in ('System.Runtime.Serialization', 'System.Xml.Linq', 'System.Web.Extensions', 'System.Xaml'):
        args_csc.append('/reference:' + name + '.dll')
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase', 'UIAutomationTypes'):
        args_csc.append('/reference:' + str(framework / 'WPF' / (name + '.dll')))
    args_csc += [str(ROOT / 'spikes/windows_05/TypedHost.cs'),
                 str(Path(__file__).with_name('ShellClient.cs')), str(Path(__file__).with_name('WindowsShell.cs'))]
    subprocess.run(args_csc, check=True, timeout=25)
    executable.chmod(stat.S_IREAD)
    config = executable.with_suffix('.exe.config')
    config.write_text(
        '<?xml version="1.0" encoding="utf-8"?><configuration><startup>'
        '<supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8"/></startup><runtime>'
        '<AppContextSwitchOverrides value="Switch.System.Windows.DoNotScaleForDpiChanges=false;'
        'Switch.System.Windows.DoNotUsePresentationDpiCapabilityTier2OrGreater=false"/>'
        '</runtime></configuration>\n', encoding='utf-8',
    )
    config.chmod(stat.S_IREAD)

    pdf = args.demo.resolve() / 'own-demo-v1.pdf'
    assert old['sha'](pdf) == old['OWN_PDF_SHA']
    old['prepare_vault'](vault_a, 'workspace-a', pdf, 'Отчёты/Учебный пример.pdf')
    source_b = old['prepare_vault'](vault_b, 'workspace-b', pdf, 'Отчёты/Отсутствующий пример.pdf')
    held = output / 'Контрольный PDF проекта Б.pdf'
    assert source_b.resolve().is_relative_to(output) and held.resolve().is_relative_to(output)
    source_b.rename(held)
    fixture = {'executable': str(executable), 'installation': str(install), 'app_data': str(app_data),
               'cwd': str(cwd), 'vault_a': str(vault_a), 'vault_b': str(vault_b)}
    (output / 'test-paths.private.json').write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return old, fixture


def run_probe(old, fixture, output):
    config = {key: Path(value) for key, value in fixture.items()}
    install, app_data, cwd, vault_a, vault_b = (config[key] for key in ('installation', 'app_data', 'cwd', 'vault_a', 'vault_b'))
    before = old['files'](install)
    command = [str(config['executable']), '--app-data', str(app_data), '--vault-a', str(vault_a),
               '--vault-b', str(vault_b), '--probe']
    process = subprocess.run(command, cwd=cwd, capture_output=True, timeout=75)
    assert process.returncode == 0, process.returncode
    native = json.loads((app_data / 'win08-shell-probe.json').read_bytes())
    paths = ApplicationPaths(install, app_data)
    with VaultStore(WorkspaceContext.open(paths, vault_a)) as store:
        counts = store.summary()
        assert counts['documents'] == counts['originals'] == counts['revisions'] == 1
        matches = store.search('Operating profit')
        assert len(matches) == 1 and matches[0]['document_id'] == 'own-demo-v1'
        assert old['sha'](vault_a / 'Отчёты/Учебный пример.pdf') == matches[0]['sha256']
    assert not (vault_b / DB_FILENAME).exists()
    assert not list((vault_b / 'runs').glob('*.json'))
    outcomes = [json.loads(path.read_bytes()) for path in (vault_a / 'runs').glob('*.json')]
    assert outcomes and all(item['result']['display'] == '15.00' and item['result']['source_page'] == 1
                            for item in outcomes)
    b_jobs = [json.loads(path.read_bytes()) for path in (vault_b / 'jobs').glob('*.json')]
    assert any(item['state'] == 'failed' and item['error'] == 'source_missing' for item in b_jobs)
    assert old['files'](install) == before and old['files'](cwd) == {}
    receipt = {'schema': 'win08-installed-shell-proof-1', 'native': native, 'vault_a_counts': counts,
               'successful_source_sha256': matches[0]['sha256'], 'successful_display': '15.00',
               'other_vault_db_absent': True, 'other_vault_no_receipt_on_missing_source': True,
               'install_files_unchanged': len(before), 'cwd_empty': True, 'model_calls': 0}
    (output / 'shell-proof.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', type=Path, required=True)
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    output = args.out.resolve()
    old, fixture = stage(args, output)
    if not args.prepare_only:
        run_probe(old, fixture, output)


if __name__ == '__main__':
    main()
