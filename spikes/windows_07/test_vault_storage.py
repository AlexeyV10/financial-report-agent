"""Focused SQLite vault checks using only owned, local synthetic fixtures."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.vault_backup import backup_store, restore_store
from financial_assistant.vault_storage import (
    APPLICATION_ID, DB_FILENAME, SCHEMA_VERSION, VaultStorageError, VaultStore, verify_storage_file,
)


ORIGINAL_A = b'%PDF-1.4 own vault fixture A'
ORIGINAL_B = b'%PDF-1.4 own vault fixture B'
EXTRACTOR = 'own-extractor-1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class VaultStorageTests(unittest.TestCase):
    def setUp(self):
        scratch = (ROOT / 'tmp').resolve()
        scratch.mkdir(exist_ok=True)
        temporary = TemporaryDirectory(prefix='win07-vault-', dir=scratch)
        self.base = Path(temporary.name).resolve()
        self.assertTrue(self.base.is_relative_to(scratch))
        self.addCleanup(temporary.cleanup)
        install = self.base / 'Каталог установки'
        install.mkdir()
        self.paths = ApplicationPaths(install, self.base / 'Данные приложения')
        self.vault = self.make_workspace('vault-a', 'Хранилище А')

    def marker(self, vault, workspace_id):
        marker = dict(schema='workspace-context-1', workspace_id=workspace_id, resources=[])
        (vault / 'workspace.json').write_text(json.dumps(marker), encoding='utf-8')

    def make_workspace(self, workspace_id, name):
        vault = self.base / name
        vault.mkdir()
        self.marker(vault, workspace_id)
        return WorkspaceContext.open(self.paths, vault)

    def assert_code(self, code, call, *args, **kwargs):
        with self.assertRaises(VaultStorageError) as raised:
            call(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def import_revision(self, store, document_id, data, text, extractor=EXTRACTOR):
        return store.import_revision(document_id, data, expected_sha256=sha(data), text=text,
                                     extractor=extractor)

    def test_two_cyrillic_vaults_do_not_share_identity_documents_or_fts(self):
        other = self.make_workspace('vault-b', 'Хранилище Б')
        with VaultStore(self.vault, create=True) as first, VaultStore(other, create=True) as second:
            one = self.import_revision(first, 'same-document', ORIGINAL_A, 'Собственный резерв')
            two = self.import_revision(second, 'same-document', ORIGINAL_B, 'Собственный фонд')
            self.assertEqual(first.workspace_id, 'vault-a')
            self.assertEqual(second.workspace_id, 'vault-b')
            self.assertEqual(first.path.parent, self.vault.vault_root)
            self.assertEqual(second.path.parent, other.vault_root)
            self.assertNotEqual(one['sha256'], two['sha256'])
            self.assertEqual([row['sha256'] for row in first.search('РЕЗЕРВ')], [sha(ORIGINAL_A)])
            self.assertEqual(first.search('фонд'), [])
            self.assertEqual(second.search('резерв'), [])
            self.assertEqual([row['sha256'] for row in second.search('ФОНД')], [sha(ORIGINAL_B)])
            self.assert_code('original_missing', second.read_original, sha(ORIGINAL_A))

    def test_append_only_versions_and_exact_duplicate_reuse_original_bytes(self):
        with VaultStore(self.vault, create=True) as store:
            first = self.import_revision(store, 'own-document', ORIGINAL_A, 'Первая версия')
            duplicate = self.import_revision(store, 'own-document', ORIGINAL_A, 'Первая версия')
            reprocessed = self.import_revision(store, 'own-document', ORIGINAL_A, 'Уточнённый текст')
            another_extractor = self.import_revision(store, 'own-document', ORIGINAL_A, 'Уточнённый текст',
                                                    extractor='own-extractor-2')
            later_original = self.import_revision(store, 'own-document', ORIGINAL_B, 'Другой оригинал')
            old_duplicate = self.import_revision(store, 'own-document', ORIGINAL_A, 'Первая версия')
            alias = self.import_revision(store, 'alias-document', ORIGINAL_A, 'Переиспользование байтов')
            self.assertEqual(first, dict(document_id='own-document', version=1, revision=1,
                                         sha256=sha(ORIGINAL_A), duplicate=False))
            self.assertEqual(duplicate, dict(first, duplicate=True))
            self.assertEqual(old_duplicate, duplicate)
            self.assertEqual((reprocessed['version'], reprocessed['revision']), (1, 2))
            self.assertEqual((another_extractor['version'], another_extractor['revision']), (1, 3))
            self.assertEqual((later_original['version'], later_original['revision']), (2, 1))
            self.assertEqual((alias['version'], alias['revision']), (1, 1))
            versions = {row['version']: row for row in store.list_versions('own-document')}
            self.assertEqual([row['revision'] for row in versions[1]['revisions']], [1, 2, 3])
            self.assertEqual([row['revision'] for row in versions[2]['revisions']], [1])
            self.assertEqual([versions[index]['sha256'] for index in (1, 2)], [sha(ORIGINAL_A), sha(ORIGINAL_B)])
            self.assertEqual(versions[1]['revisions'][0]['text_sha256'], sha('Первая версия'.encode('utf-8')))
            self.assertEqual({(row['version'], row['revision']) for row in store.search('текст')}, {(1, 2), (1, 3)})
            self.assertEqual(store.read_original(sha(ORIGINAL_A)), ORIGINAL_A)
            self.assertEqual(store.read_original(sha(ORIGINAL_B)), ORIGINAL_B)
            self.assertEqual(store.summary(), dict(documents=2, originals=2, versions=3, revisions=5, fts_rows=5))
            snapshot = store.summary()
            self.assert_code('source_hash_mismatch', store.import_revision, 'disallowed', ORIGINAL_A,
                             expected_sha256=sha(ORIGINAL_B), text='Текст', extractor=EXTRACTOR)
            self.assertEqual(store.summary(), snapshot)

    def test_user_query_is_a_literal_cyrillic_phrase(self):
        with VaultStore(self.vault, create=True) as store:
            self.import_revision(store, 'reserve', ORIGINAL_A, 'Только резерв')
            self.import_revision(store, 'fund', ORIGINAL_B, 'Только фонд')
            self.import_revision(store, 'literal', ORIGINAL_A, 'Точная фраза резерв OR фонд здесь')
            self.assertEqual({row['document_id'] for row in store.search('ФОНД')}, {'fund', 'literal'})
            self.assertEqual([row['document_id'] for row in store.search('резерв OR фонд')], ['literal'])
            self.assertEqual([row['document_id'] for row in store.search('резерв" OR "фонд')], ['literal'])

    def test_empty_v0_database_migrates_transactionally(self):
        path = self.vault.vault_root / DB_FILENAME
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('VACUUM')
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 0)
        self.assertGreater(path.stat().st_size, 0)
        empty_database = path.read_bytes()
        self.assert_code('storage_application_mismatch', VaultStore, self.vault)
        self.assertEqual(path.read_bytes(), empty_database)
        with VaultStore(self.vault, create=True) as store:
            self.assertEqual(store.summary(), dict(documents=0, originals=0, versions=0, revisions=0, fts_rows=0))
            self.import_revision(store, 'v0-migrated', ORIGINAL_A, 'Миграция проверена')
        verified = verify_storage_file(path, self.vault.workspace_id)
        self.assertEqual(verified['schema_version'], SCHEMA_VERSION)
        self.assertEqual(verified['application_id'], APPLICATION_ID)
        self.assertEqual(verified['revisions'], 1)

    def test_unknown_version_refuses_to_rewrite_existing_database(self):
        with VaultStore(self.vault, create=True) as store:
            self.import_revision(store, 'known', ORIGINAL_A, 'Сохраняемый объект')
            path = store.path
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('PRAGMA user_version = 99')
        before = path.read_bytes()
        self.assert_code('storage_version_mismatch', VaultStore, self.vault, create=True)
        self.assertEqual(path.read_bytes(), before)

    def test_database_owner_mismatch_does_not_rewrite_existing_database(self):
        with VaultStore(self.vault, create=True) as store:
            self.import_revision(store, 'known', ORIGINAL_A, 'Сохраняемый объект')
            path = store.path
        before = path.read_bytes()
        self.marker(self.vault.vault_root, 'incorrect-owner')
        rebound = WorkspaceContext.open(self.paths, self.vault.vault_root)
        self.assert_code('workspace_mismatch', VaultStore, rebound, create=True)
        self.assertEqual(path.read_bytes(), before)

    def test_real_sqlite_full_preserves_preexisting_original_and_metadata(self):
        with VaultStore(self.vault, create=True) as store:
            self.import_revision(store, 'protected', ORIGINAL_A, 'Уже сохранённый оригинал')
            summary, versions = store.summary(), store.list_versions('protected')
            connection = store._connection
            original_limit = connection.execute('PRAGMA max_page_count').fetchone()[0]
            allocated = connection.execute('PRAGMA page_count').fetchone()[0]
            self.assertEqual(connection.execute(f'PRAGMA max_page_count = {allocated}').fetchone()[0], allocated)
            try:
                oversized_blob = b'%PDF-own-full-test ' + b'x' * (256 * 1024)
                error = self.assert_code('storage_full', self.import_revision, store, 'protected',
                                         oversized_blob, 'Эта запись не помещается')
                cause = error.__cause__ or error.__context__
                self.assertEqual(getattr(cause, 'sqlite_errorcode', None), sqlite3.SQLITE_FULL)
                self.assertFalse(connection.in_transaction)
                self.assertEqual(store.summary(), summary)
                self.assertEqual(store.list_versions('protected'), versions)
                self.assertEqual(store.read_original(sha(ORIGINAL_A)), ORIGINAL_A)
            finally:
                connection.execute(f'PRAGMA max_page_count = {original_limit}')
            follow_up = self.import_revision(store, 'protected', ORIGINAL_B, 'Новая попытка после отказа')
            self.assertEqual((follow_up['version'], follow_up['revision']), (2, 1))

    def test_integrity_verifier_rejects_wrong_fts_text_revision_gap_and_same_size_blob_change(self):
        fixtures = (
            ('fts', 'UPDATE revision_fts SET text = ?', ('Здесь другой текст',)),
            ('revision', 'UPDATE revisions SET revision = 2', ()),
            ('blob', 'UPDATE originals SET data = ?', (ORIGINAL_B,)),
        )
        for name, statement, values in fixtures:
            with self.subTest(name=name):
                workspace = self.make_workspace('verify-' + name, 'Проверка целостности ' + name)
                with VaultStore(workspace, create=True) as store:
                    self.import_revision(store, 'own', ORIGINAL_A, 'Проверенная запись')
                    path = store.path
                verified = verify_storage_file(path, workspace.workspace_id)
                self.assertTrue(verified['original_hashes_ok'])
                self.assertTrue(verified['fts_consistency_ok'])
                self.assertEqual((verified['revisions'], verified['fts_rows']), (1, 1))

                with closing(sqlite3.connect(path)) as connection:
                    connection.execute(statement, values)
                    connection.commit()
                before = path.read_bytes()
                self.assert_code('storage_integrity_failed', verify_storage_file, path, workspace.workspace_id)
                self.assertEqual(path.read_bytes(), before)

    def test_backup_restores_exact_state_to_separate_vault_and_never_overwrites(self):
        target = self.base / 'Проверенная резервная копия.sqlite3'
        with VaultStore(self.vault, create=True) as store:
            self.import_revision(store, 'saved', ORIGINAL_A, 'Сохранённый резерв')
            self.import_revision(store, 'saved', ORIGINAL_A, 'Уточнённый резерв')
            expected = store.summary(), store.list_versions('saved'), store.search('резерв')
            installation_target = self.paths.install_root / 'Forbidden snapshot.sqlite3'
            self.assert_code('invalid_backup_path', backup_store, store, installation_target)
            self.assertFalse(installation_target.exists())
            backup = backup_store(store, target)
            previous = target.read_bytes()
            self.assert_code('backup_destination_exists', backup_store, store, target)
            self.import_revision(store, 'after-backup', ORIGINAL_B, 'Добавлен после резервной копии')
            self.assertEqual(store.summary()['documents'], 2)
            self.assertEqual(target.read_bytes(), previous)
        self.assertEqual(backup['schema'], 'win07-backup-1')
        self.assertEqual(backup['sha256'], sha(previous))
        self.assertEqual(backup['workspace_id'], self.vault.workspace_id)

        receiver = self.make_workspace(self.vault.workspace_id, 'Отдельное восстановление')
        restored = restore_store(receiver, target)
        self.assertEqual(restored['schema'], 'win07-restore-1')
        self.assertEqual(restored['backup_sha256'], backup['sha256'])
        with VaultStore(receiver) as store:
            self.assertNotEqual(store.path.parent, self.vault.vault_root)
            self.assertEqual((store.summary(), store.list_versions('saved'), store.search('резерв')), expected)
            self.assertEqual(store.read_original(sha(ORIGINAL_A)), ORIGINAL_A)
            restored_path = store.path
        restored_bytes = restored_path.read_bytes()
        self.assert_code('restore_destination_exists', restore_store, receiver, target)
        self.assertEqual(restored_path.read_bytes(), restored_bytes)
        self.assertEqual(target.read_bytes(), previous)

    def test_restore_refuses_wrong_owner_and_corrupt_backup_without_publication(self):
        target = self.base / 'Резервная копия.sqlite3'
        with VaultStore(self.vault, create=True) as store:
            self.import_revision(store, 'saved', ORIGINAL_A, 'Корректный оригинал')
            backup_store(store, target)
        before = target.read_bytes()
        wrong = self.make_workspace('different-owner', 'Чужое хранилище')
        self.assert_code('workspace_mismatch', restore_store, wrong, target)
        self.assertFalse((wrong.vault_root / DB_FILENAME).exists())

        corrupt = self.base / 'Испорченная копия.sqlite3'
        bad_bytes = b'Not a SQLite file. Own malformed test fixture.'
        corrupt.write_bytes(bad_bytes)
        receiver = self.make_workspace(self.vault.workspace_id, 'Неподменённое восстановление')
        sidecar = target.with_name(target.name + '-wal')
        sidecar.write_bytes(b'own sidecar fixture')
        self.assert_code('backup_snapshot_changed', restore_store, receiver, target)
        self.assertFalse((receiver.vault_root / DB_FILENAME).exists())
        with self.assertRaises(VaultStorageError) as rejected:
            restore_store(receiver, corrupt)
        self.assertIn(rejected.exception.code, {'storage_corrupt', 'storage_integrity_failed'})
        self.assertFalse((receiver.vault_root / DB_FILENAME).exists())
        self.assertEqual(corrupt.read_bytes(), bad_bytes)
        self.assertEqual(target.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
