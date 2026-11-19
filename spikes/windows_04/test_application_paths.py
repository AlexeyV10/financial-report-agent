"""Own-fixture checks for the native workspace boundary."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant.application_paths import (
    ApplicationPaths,
    WorkspaceContext,
    WorkspacePathError,
    resolve_legacy_resource,
)


RESOURCE = 'own.demo'
SOURCE = 'documents/Учебный отчёт.pdf'
PDF_A = b'%PDF-own-a'
PDF_B = b'%PDF-own-b'


def source_record(data, relative=SOURCE, resource_id=RESOURCE):
    return dict(id=resource_id, path=relative, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


class ApplicationPathsTests(unittest.TestCase):
    def setUp(self):
        scratch = (ROOT / 'tmp').resolve()
        scratch.mkdir(exist_ok=True)
        directory = TemporaryDirectory(prefix='win04-paths-', dir=scratch)
        self.base = Path(directory.name).resolve()
        self.assertTrue(self.base.is_relative_to(scratch))
        self.addCleanup(directory.cleanup)

        self.install = self.base / 'Готовая установка'
        self.app_data = self.base / 'Данные приложения'
        self.install.mkdir()
        self.app_data.mkdir()
        self.paths = ApplicationPaths(self.install, self.app_data)
        self.vault_a = self.base / 'Хранилище А'
        self.vault_b = self.base / 'Хранилище Б'

    def write_registry(self, vault, workspace_id='vault-a', *, resources=None, **extra):
        vault.mkdir(exist_ok=True)
        if resources is None:
            resources = [source_record(PDF_A)]
        registry = dict(schema='workspace-context-1', workspace_id=workspace_id, resources=resources, **extra)
        (vault / 'workspace.json').write_text(json.dumps(registry, ensure_ascii=False), encoding='utf-8')

    def create_vault(self, vault, workspace_id, data):
        self.write_registry(vault, workspace_id, resources=[source_record(data)])
        path = vault / SOURCE
        path.parent.mkdir()
        path.write_bytes(data)
        return WorkspaceContext.open(self.paths, vault)

    def assert_code(self, code, action, *args):
        with self.assertRaises(WorkspacePathError) as raised:
            action(*args)
        self.assertEqual(raised.exception.code, code)

    def assert_invalid_resource_path(self, relative):
        self.write_registry(self.vault_a, resources=[source_record(PDF_A, relative)])

        def resolve():
            return WorkspaceContext.open(self.paths, self.vault_a).resolve_resource(RESOURCE)

        self.assert_code('invalid_relative_path', resolve)

    def test_require_absolute_roots_and_keep_install_and_app_data_separate(self):
        self.assert_code('invalid_root', ApplicationPaths, Path('relative-install'), self.app_data)
        self.assert_code('invalid_root', ApplicationPaths, self.install, Path('relative-app-data'))
        with patch('financial_assistant.application_paths._inspect',
                   side_effect=AssertionError('UNC paths must fail before filesystem inspection')):
            self.assert_code('invalid_root', ApplicationPaths, Path(r'\\server\share\install'), self.app_data)
        self.assert_code('root_overlap', ApplicationPaths, self.install, self.install)
        contained = self.install / 'private-data'
        contained.mkdir()
        self.assert_code('root_overlap', ApplicationPaths, self.install, contained)

        roots = (self.paths.cache_root, self.paths.models_root, self.paths.logs_root)
        self.assertEqual(len(set(roots)), len(roots))
        self.assertTrue(all(root.is_relative_to(self.app_data) for root in roots))
        asset = self.install / 'assets' / 'test.json'
        asset.parent.mkdir()
        asset.write_bytes(b'{}')
        self.assertEqual(self.paths.asset('assets/test.json'), asset)
        self.assertEqual(asset.read_bytes(), b'{}')
        self.assert_code('invalid_relative_path', self.paths.asset, '../private.json')

    def test_forbid_vault_in_installation_or_app_data(self):
        for directory in (self.install, self.app_data):
            with self.subTest(directory=directory.name):
                vault = directory / 'vault'
                self.write_registry(vault)
                self.assert_code('root_overlap', WorkspaceContext.open, self.paths, vault)

    def test_registry_rejects_unexpected_keys_and_duplicate_resource_ids(self):
        self.write_registry(self.vault_a, extra_key=True)
        self.assert_code('invalid_workspace', WorkspaceContext.open, self.paths, self.vault_a)
        self.write_registry(self.vault_a, resources=[source_record(PDF_A), source_record(PDF_B)])
        self.assert_code('duplicate_resource', WorkspaceContext.open, self.paths, self.vault_a)
        self.write_registry(self.vault_a, resources=[dict(source_record(PDF_A), bytes=True)])
        self.assert_code('invalid_resource_binding', WorkspaceContext.open, self.paths, self.vault_a)
        registry_path = self.vault_a / 'workspace.json'
        registry_path.write_text(
            '{"schema":"workspace-context-1","workspace_id":"a","workspace_id":"b","resources":[]}',
            encoding='utf-8',
        )
        self.assert_code('invalid_workspace', WorkspaceContext.open, self.paths, self.vault_a)

    def test_reject_unsafe_windows_spellings_before_using_the_path(self):
        for relative in ('../other/report.pdf', '/root/report.pdf', r'\root\report.pdf',
                         'C:drive-relative.pdf', 'C:/absolute.pdf', r'\\server\share\report.pdf',
                         'documents/report.pdf:alternate', 'documents/.. /report.pdf',
                         'documents/report.pdf.', 'documents/report.pdf ',
                         'documents/NUL', 'documents/CoN.pdf'):
            with self.subTest(relative=relative):
                self.assert_invalid_resource_path(relative)

    def test_source_absent_and_same_size_replacement_are_different_errors(self):
        first = self.create_vault(self.vault_a, 'vault-a', PDF_A)
        source = first.resolve_resource(RESOURCE)
        self.assertEqual(source, self.vault_a / SOURCE)
        source.write_bytes(PDF_B)
        self.assert_code('source_hash_mismatch', first.resolve_resource, RESOURCE)
        source.write_bytes(PDF_B + b'extra')
        self.assert_code('source_size_mismatch', first.resolve_resource, RESOURCE)
        source.unlink()
        self.assert_code('source_missing', first.resolve_resource, RESOURCE)
        self.assert_code('resource_not_registered', first.resolve_resource, 'unknown')

    def test_resource_link_cannot_leave_vault(self):
        external = self.base / 'outside'
        external.mkdir()
        (external / 'own.pdf').write_bytes(PDF_A)
        self.write_registry(self.vault_a, resources=[source_record(PDF_A, 'link/own.pdf')])
        link = self.vault_a / 'link'
        try:
            link.symlink_to(external, target_is_directory=True)
        except OSError as error:
            if os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 1314):
                raise
            self.create_windows_junction(link, external)
        else:
            self.addCleanup(link.unlink)
        first = WorkspaceContext.open(self.paths, self.vault_a)
        self.assert_code('path_escape', first.resolve_resource, RESOURCE)

    def create_windows_junction(self, link, target):
        # Windows can create a directory junction without the symlink privilege.
        shell = (Path(os.environ['SystemRoot'])
                 / 'System32/WindowsPowerShell/v1.0/powershell.exe')
        if not shell.is_file():
            self.skipTest('Windows PowerShell is unavailable for the junction fixture')
        self.assertTrue(link.resolve().is_relative_to(self.base))
        self.assertTrue(target.resolve().is_relative_to(self.base))
        result = subprocess.run(
            [str(shell), '-NoProfile', '-NonInteractive', '-Command',
             "$ErrorActionPreference='Stop'\n"
             'New-Item -ItemType Junction -Path $env:WIN04_LINK -Value $env:WIN04_TARGET | Out-Null'],
            env=dict(os.environ, WIN04_LINK=str(link), WIN04_TARGET=str(target)),
            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            self.skipTest('Windows does not permit creating a directory junction here')
        self.assertTrue(link.is_junction())
        self.addCleanup(link.rmdir)

    def test_same_logical_id_and_run_in_two_vaults_are_independent(self):
        first = self.create_vault(self.vault_a, 'vault-a', PDF_A)
        second = self.create_vault(self.vault_b, 'vault-b', PDF_B)
        self.assertEqual(first.resolve_resource(RESOURCE).read_bytes(), PDF_A)
        self.assertEqual(second.resolve_resource(RESOURCE).read_bytes(), PDF_B)

        receipt_a = self.vault_a / 'runs' / 'run-1.json'
        receipt_b = self.vault_b / 'runs' / 'run-1.json'
        self.assertEqual(first.write_receipt('run-1', {'workspace': 'a'}), receipt_a)
        self.assertEqual(second.write_receipt('run-1', {'workspace': 'b'}), receipt_b)
        original_a = receipt_a.read_bytes()
        self.assertNotEqual(original_a, receipt_b.read_bytes())
        self.assert_code('duplicate_run', first.write_receipt, 'RUN-1', {'workspace': 'replacement'})
        self.assertEqual(receipt_a.read_bytes(), original_a)
        self.assert_code('invalid_run_id', first.write_receipt, '../outside', {})
        self.assert_code('invalid_run_id', first.write_receipt, 'CoN', {})
        self.assertEqual(list((self.vault_a / 'runs').iterdir()), [receipt_a])

    def test_concurrent_writers_cannot_replace_a_receipt(self):
        vault = self.create_vault(self.vault_a, 'vault-a', PDF_A)
        ready = Barrier(2)

        def publish(writer):
            ready.wait(timeout=5)
            try:
                vault.write_receipt('same-run', {'writer': writer})
            except WorkspacePathError as error:
                return error.code, writer
            return 'written', writer

        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(publish, ('one', 'two')))
        self.assertCountEqual([code for code, _ in outcomes], ['written', 'duplicate_run'])
        winner = next(writer for code, writer in outcomes if code == 'written')
        directory = self.vault_a / 'runs'
        receipt = directory / 'same-run.json'
        self.assertEqual(json.loads(receipt.read_bytes()), {'writer': winner})
        self.assertEqual(list(directory.iterdir()), [receipt])

    def test_existing_closed_vault_reopens_at_its_new_root(self):
        first = self.create_vault(self.vault_a, 'vault-a', PDF_A)
        receipt = first.write_receipt('run-before-moving', {'fixture': 'a'})
        previous_bytes = receipt.read_bytes()
        relocated = self.base / 'Перенесённое хранилище'
        self.assertTrue(self.vault_a.resolve().is_relative_to(self.base))
        self.assertTrue(relocated.resolve().is_relative_to(self.base))
        self.vault_a.rename(relocated)

        reopened = WorkspaceContext.open(self.paths, relocated)
        self.assertEqual(reopened.workspace_id, first.workspace_id)
        self.assertEqual(reopened.resolve_resource(RESOURCE), relocated / SOURCE)
        self.assertEqual((relocated / 'runs' / receipt.name).read_bytes(), previous_bytes)
        self.assertFalse(self.vault_a.exists())

    def test_legacy_registry_maps_only_explicit_pinned_relative_paths(self):
        legacy_root = self.base / 'Отдельная папка legacy'
        legacy_root.mkdir()
        source = legacy_root / SOURCE
        source.parent.mkdir()
        source.write_bytes(PDF_A)
        pin = source_record(PDF_A)
        del pin['id']
        bindings = {RESOURCE: pin}
        self.assertEqual(resolve_legacy_resource(legacy_root, bindings, RESOURCE), source)
        self.assert_code('resource_not_registered', resolve_legacy_resource, legacy_root, bindings, 'unlisted')
        self.assert_code('invalid_relative_path', resolve_legacy_resource, legacy_root,
                         {RESOURCE: dict(pin, path=str(source))}, RESOURCE)
        source.write_bytes(PDF_B)
        self.assert_code('source_hash_mismatch', resolve_legacy_resource, legacy_root, bindings, RESOURCE)


if __name__ == '__main__':
    unittest.main()
