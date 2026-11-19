"""Verify owned Windows processes and the installed supervised CLI."""

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import runpy
import stat
import subprocess
import sys
from threading import Event, Thread
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from financial_assistant.job_supervisor import JobSupervisor
from financial_assistant.typed_ipc import TypedIpcError, exchange, make_request


def wait_for_marker(marker):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            identifiers = json.loads(marker.read_bytes())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.05)
            continue
        assert set(identifiers) == {'worker', 'child'}
        assert len(set(identifiers.values())) == 2 and all(type(pid) is int for pid in identifiers.values())
        return identifiers
    raise TimeoutError('No owned worker fixture marker')


class ObservedProcesses:
    def __init__(self, ids):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handles = []
        try:
            for pid in ids:
                handle = self.kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, no termination access.
                if not handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handles.append(handle)
            assert all(self.kernel.WaitForSingleObject(handle, 0) == 258 for handle in self.handles)
        except BaseException:
            self.close()
            raise

    def stopped(self):
        return all(self.kernel.WaitForSingleObject(handle, 4000) == 0 for handle in self.handles)

    def close(self):
        for handle in self.handles:
            self.kernel.CloseHandle(handle)
        self.handles.clear()


def fixture_args(marker):
    return [sys.executable, '-I', '-B', str(Path(__file__).with_name('owned_worker_fixture.py')), str(marker)]


def check_stop(output, *, use_cancel):
    label = 'cancel' if use_cancel else 'deadline'
    marker = output / (label + '.json')
    cancellation = Event()
    result = []

    def test_worker():
        try:
            frame = make_request('b' * 64, label)
            exchange(fixture_args(marker), frame, cwd=output, timeout=30 if use_cancel else 5.0,
                     cancel_event=cancellation, own_tree=True)
        except TypedIpcError as error:
            result.append(error.code)

    thread = Thread(target=test_worker, daemon=True)
    thread.start()
    try:
        observed = ObservedProcesses(wait_for_marker(marker).values())
        try:
            if use_cancel:
                cancellation.set()
            thread.join(8)
            assert not thread.is_alive()
            assert result == ['worker_cancelled' if use_cancel else 'worker_timeout'], result
            assert observed.stopped()
        finally:
            observed.close()
    finally:
        cancellation.set()
        thread.join(3)
    return {'error': result[0], 'both_processes_confirmed_stopped': True, 'premature_reply_discarded': True}


def crash_controller(journal, marker):
    def execute(request, *, cancel_event, timeout, report_progress):
        report_progress(10)
        return exchange(fixture_args(marker), request, cwd=marker.parent, timeout=timeout,
                        cancel_event=cancel_event, own_tree=True)

    with JobSupervisor(journal, execute, lambda request, response: response) as supervisor:
        supervisor.submit(make_request('c' * 64, 'crash-owned'), timeout=30.0)
        supervisor.wait('crash-owned', timeout=35.0)


def check_host_crash(output):
    journal, marker = output / 'crash-jobs', output / 'crash.json'
    child = subprocess.Popen([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
                              '--crash-controller', str(journal), str(marker)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        observed = ObservedProcesses(wait_for_marker(marker).values())
        try:
            child.kill()  # Exact test-owned controller handle.
            child.wait(timeout=5)
            assert observed.stopped()
        finally:
            observed.close()
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
    with JobSupervisor(journal, lambda *_args, **_kwargs: None, lambda _request, response: response) as reopened:
        job = reopened.get('crash-owned')
    assert job['state'] == 'interrupted' and job['response'] is None
    return {'controller_killed': True, 'both_processes_confirmed_stopped': True, 'reopen_state': job['state'],
            'financial_result_recovered': False}


def check_installed(args, output):
    old = runpy.run_path(str(ROOT / 'spikes/windows_04/check_workflow.py'))
    install, vault, app_data, cwd = (output / leaf for leaf in (
        'Установка supervisor', 'Хранилище supervisor', 'Данные ассистента', 'Рабочая папка',
    ))
    cwd.mkdir()
    app_data.mkdir()
    old['prepare_install'](args.runtime_build, args.demo, install)
    for relative in ('src/financial_assistant/application_service.py', 'src/financial_assistant/typed_ipc.py',
                     'src/financial_assistant/windows_job.py', 'src/financial_assistant/job_supervisor.py',
                     'spikes/windows_05/service_cli.py', 'spikes/windows_06/supervised_service.py'):
        target = install / 'app' / relative
        old['copy'](ROOT / relative, target)
        target.chmod(stat.S_IREAD)
    install_before = old['files'](install)
    old['prepare_vault'](vault, 'workspace-supervisor', args.demo / 'own-demo-v1.pdf', 'Примеры/source.pdf')
    cli = [str(install / 'runtime/python.exe'), '-I', '-B', '-X', 'utf8',
           str(install / 'app/spikes/windows_05/service_cli.py'), '--install-root', str(install),
           '--app-data', str(app_data), '--vault', str(vault), '--run-id', 'supervised-own', '--supervised']

    def invoke():
        result = subprocess.run(cli, cwd=cwd, capture_output=True, timeout=25)
        assert not result.stderr, result.stderr.decode('utf-8', errors='replace')
        return result.returncode, json.loads(result.stdout)

    status, response = invoke()
    assert status == 0 and response['status'] == 'completed' and response['result']['display'] == '15.00', response
    assert response['result']['source_sha256'] == old['OWN_PDF_SHA']
    receipt = vault / 'runs/supervised-own.json'
    original = receipt.read_bytes()
    assert json.loads(original) == response
    files_before = old['files'](vault)
    replay_status, replay = invoke()
    assert replay_status == 0 and replay == response and receipt.read_bytes() == original
    assert old['files'](vault) == files_before and old['files'](install) == install_before
    assert old['files'](cwd) == {}
    jobs = list((vault / 'jobs').glob('*.json'))
    assert len(jobs) == 1
    job = json.loads(jobs[0].read_bytes())
    assert job['state'] == 'completed' and job['response'] == response
    return {'display': response['result']['display'], 'source_sha256': response['result']['source_sha256'],
            'source_page': response['result']['source_page'], 'idempotent_cli_restart': True,
            'install_files_unchanged': len(install_before), 'event_count': len(job['events']), 'model_calls': 0}


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--crash-controller':
        crash_controller(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', type=Path, required=True)
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.runtime_build = args.runtime_build.resolve()
    args.demo = args.demo.resolve()
    output = args.out.resolve()
    if sys.platform != 'win32' or not output.is_relative_to(ROOT / 'tmp') or output == ROOT / 'tmp':
        raise ValueError('Use a new output under this Windows checkout’s tmp/')
    output.mkdir(parents=True)
    unrelated = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(60)'])
    try:
        report = {'schema': 'win06-windows-supervision-proof-1',
                  'cancel': check_stop(output, use_cancel=True),
                  'deadline': check_stop(output, use_cancel=False),
                  'crash': check_host_crash(output), 'installed_cli': check_installed(args, output)}
        assert unrelated.poll() is None
        report['unrelated_control_stayed_alive'] = True
    finally:
        if unrelated.poll() is None:
            unrelated.terminate()
            unrelated.wait(timeout=5)
    (output / 'supervision.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
