"""Run the same installed typed service through a CLI and a native WPF button."""

import argparse
import json
import os
from pathlib import Path
import runpy
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def staged_install(runtime_build, demo, install):
    old_stage = runpy.run_path(str(ROOT / 'spikes/windows_04/check_workflow.py'))
    old_stage['prepare_install'](runtime_build, demo, install)
    for relative in ('src/financial_assistant/application_service.py', 'src/financial_assistant/typed_ipc.py',
                     'spikes/windows_05/service_cli.py'):
        target = install / 'app' / relative
        old_stage['copy'](ROOT / relative, target)
        target.chmod(stat.S_IREAD)

    framework = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319'
    binary = install / 'ProjectPractice-WIN05.exe'
    compile_args = [str(framework / 'csc.exe'), '/nologo', '/target:winexe', '/platform:x64',
                    '/codepage:65001', '/out:' + str(binary),
                    '/reference:System.Runtime.Serialization.dll', '/reference:System.Xml.Linq.dll',
                    '/reference:System.Web.Extensions.dll', '/reference:System.Xaml.dll']
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase', 'UIAutomationTypes'):
        compile_args.append('/reference:' + str(framework / 'WPF' / (name + '.dll')))
    compile_args.append(str(Path(__file__).with_name('TypedHost.cs')))
    subprocess.run(compile_args, check=True, timeout=25)
    binary.chmod(stat.S_IREAD)
    return old_stage, binary


def invoke(argv, cwd, *, input_data=None):
    output = subprocess.run(argv, input=input_data, cwd=cwd, capture_output=True, timeout=35)
    if output.stderr:
        raise RuntimeError(f'Unexpected diagnostics from {Path(argv[0]).name}')
    return output.returncode, json.loads(output.stdout) if output.stdout else None


def service_args(install, app_data, vault):
    return [str(install / 'runtime/python.exe'), '-I', '-B', '-X', 'utf8',
            str(install / 'app/spikes/windows_05/service_cli.py'), '--install-root', str(install),
            '--app-data', str(app_data), '--vault', str(vault)]


def assert_failure(output, expected_code):
    assert output['schema'] == 'win05-response-1' and output['command'] == 'own_margin'
    assert output['status'] == 'failed' and output['error'] == expected_code
    assert output['result'] is None


def check(runtime_build, demo, output):
    if not output.is_relative_to(ROOT / 'tmp') or output == ROOT / 'tmp':
        raise ValueError('Choose a new output path under tmp/')
    output.mkdir(parents=True)
    install, app_data, cli_data, cwd, vault_a, vault_b = (output / name for name in (
        'Установка WIN-05', 'Данные нативного окна', 'Данные CLI', 'Посторонняя папка',
        'Хранилище A', 'Хранилище Б',
    ))
    app_data.mkdir()
    cli_data.mkdir()
    cwd.mkdir()
    old_stage, native_binary = staged_install(runtime_build, demo, install)
    inventory_before = old_stage['files'](install)

    pdf = demo / 'own-demo-v1.pdf'
    assert old_stage['sha'](pdf) == old_stage['OWN_PDF_SHA']
    old_stage['prepare_vault'](vault_a, 'workspace-a', pdf, 'PDF/own-demo-v1.pdf')
    source_b = old_stage['prepare_vault'](vault_b, 'workspace-b', pdf, 'Данные/Пример.pdf')

    cli = service_args(install, cli_data, vault_a)
    code, cli_reply = invoke(cli + ['--run-id', 'typed-cli'], cwd)
    assert code == 0 and cli_reply['status'] == 'completed' and cli_reply['result']['display'] == '15.00', cli_reply
    cli_receipt = vault_a / 'runs/typed-cli.json'
    assert json.loads(cli_receipt.read_bytes()) == cli_reply
    original_receipt = cli_receipt.read_bytes()
    duplicate_code, duplicate = invoke(cli + ['--run-id', 'TYPED-CLI'], cwd)
    assert duplicate_code == 3 and cli_receipt.read_bytes() == original_receipt
    assert_failure(duplicate, 'duplicate_run')

    wpf = [str(native_binary), '--app-data', str(app_data), '--vault', str(vault_b), '--probe', 'typed-wpf']
    wpf_code, _ = invoke(wpf, cwd)
    assert wpf_code == 0, wpf_code
    native = json.loads((app_data / 'win05-native-probe.json').read_bytes())
    assert native['button_activated'] is True and native['content_rendered'] is True
    assert native['run_id'] == 'typed-wpf' and native['display'] == '15.00' and native['source_page'] == 1
    wpf_reply = json.loads((vault_b / 'runs/typed-wpf.json').read_bytes())
    assert wpf_reply['status'] == 'completed' and wpf_reply['context_id'] == native['context_id']
    assert cli_reply['context_id'] != wpf_reply['context_id']
    for key in ('operation', 'source_id', 'source_sha256', 'source_page', 'source_highlight', 'display'):
        assert cli_reply['result'][key] == wpf_reply['result'][key]
    assert cli_reply['result']['workspace_id'] != wpf_reply['result']['workspace_id']

    before = old_stage['files'](vault_b)
    failure_data = output / 'Данные проверки отказа'
    failure_data.mkdir()
    held = source_b.with_name('own-fixture-held.pdf')
    assert source_b.resolve().is_relative_to(output) and held.resolve().is_relative_to(output)
    source_b.rename(held)
    try:
        native_error_code, _ = invoke([
            str(native_binary), '--app-data', str(failure_data), '--vault', str(vault_b), '--probe', 'wpf-missing',
        ], cwd)
        native_error = json.loads((failure_data / 'win05-native-probe.json').read_bytes())
        assert native_error_code == 3 and native_error['status'] == 'failed'
        assert native_error['error'] == 'source_missing' and native_error['display'] is None
        assert not (vault_b / 'runs/wpf-missing.json').exists()
    finally:
        held.rename(source_b)

    stale_request = {'schema': 'win05-request-1', 'run_id': 'stale-test', 'context_id': cli_reply['context_id'],
                     'command': 'own_margin', 'arguments': {'resource_id': 'own-demo-v1'}}
    data = json.dumps(stale_request, separators=(',', ':')).encode('ascii') + b'\n'
    code, stale = invoke(service_args(install, cli_data, vault_b) + ['--worker'], cwd, input_data=data)
    assert code == 0 and stale['context_id'] == cli_reply['context_id']
    assert_failure(stale, 'stale_context')
    assert old_stage['files'](vault_b) == before and old_stage['files'](install) == inventory_before
    assert old_stage['files'](cwd) == {}

    receipt = {'schema': 'win05-native-and-cli-proof-1', 'cli': cli_reply, 'native_probe': native,
               'native_receipt': wpf_reply, 'native_refusal_probe': native_error,
               'duplicate_refused_and_original_preserved': True,
               'cross_vault_context_refused': True, 'install_files_unchanged': len(inventory_before),
               'different_working_directory': True, 'model_calls': 0}
    (output / 'service-proof.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', type=Path, required=True)
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check(args.runtime_build.resolve(), args.demo.resolve(), args.out.resolve())


if __name__ == '__main__':
    main()
