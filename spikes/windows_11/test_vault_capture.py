"""Transactional original-only capture against real SQLite and backup files."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.vault_backup import backup_store, restore_store
from financial_assistant.vault_storage import (
    CAPTURE_SCHEMA_VERSION, DB_FILENAME, MAX_CAPTURE_BYTES, SCHEMA_VERSION, VaultStorageError,
    VaultStore, verify_storage_file,
)


CSV = "Показатель,Сумма\nВыручка,120\n".encode()
TEXT = "Образец сохранённого оригинала".encode()
EMPTY_SUMMARY = dict(documents=0, originals=0, versions=0, revisions=0, fts_rows=0)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class VaultCaptureTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        temp = TemporaryDirectory(dir=scratch, prefix="vault11-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        install = self.base / "Установка"
        install.mkdir()
        self.paths = ApplicationPaths(install, self.base / "Данные приложения")
        self.vault = self.workspace("vault-a", "Хранилище А")

    def workspace(self, identity, name):
        root = self.base / name
        root.mkdir()
        marker = {"schema": "workspace-context-1", "workspace_id": identity, "resources": []}
        (root / "workspace.json").write_text(json.dumps(marker), encoding="utf-8")
        return WorkspaceContext.open(self.paths, root)

    def assert_code(self, code, operation, *args, **kwargs):
        with self.assertRaises(VaultStorageError) as failure:
            operation(*args, **kwargs)
        self.assertEqual(failure.exception.code, code)
        return failure.exception

    def assert_v1(self, connection):
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone(), (SCHEMA_VERSION,))
        self.assertIsNone(connection.execute("SELECT name FROM sqlite_schema WHERE name='captures'").fetchone())

    def test_legacy_vault_stays_v1_until_first_capture_and_reuses_indexed_bytes(self):
        path = self.vault.vault_root / DB_FILENAME
        digest = sha(CSV)
        with VaultStore(self.vault, create=True) as store:
            store.import_revision("already-indexed", CSV, expected_sha256=digest, text="Годовая выручка",
                                  extractor="legacy-test")
            self.assert_v1(store._connection)
            indexed = store.summary(), store.list_versions("already-indexed"), store.search("выручка")
        original_v1 = path.read_bytes()

        for create in (False, True):
            with VaultStore(self.vault, create=create) as store:
                self.assert_v1(store._connection)
                self.assertEqual((store.summary(), store.list_versions("already-indexed"),
                                  store.search("выручка")), indexed)
                self.assert_code("capture_missing", store.get_capture, digest)
        with VaultStore(self.vault) as store:
            legacy_backup = backup_store(store, self.base / "Резерв v1.sqlite3")
        self.assertEqual(legacy_backup["schema_version"], SCHEMA_VERSION)
        self.assertNotIn("captures", legacy_backup)
        self.assertEqual(path.read_bytes(), original_v1)

        with VaultStore(self.vault) as store:
            stored = store.capture_original(CSV, "csv")
            self.assertEqual(stored, dict(sha256=digest, byte_count=len(CSV), file_type="csv", duplicate=False))
            self.assertEqual(store._connection.execute("SELECT count(*) FROM originals").fetchone(), (1,))
            self.assertEqual(store._connection.execute("SELECT count(*) FROM captures").fetchone(), (1,))
            self.assertEqual((store.summary(), store.list_versions("already-indexed"), store.search("выручка")),
                             indexed)
        verified = verify_storage_file(path, self.vault.workspace_id)
        self.assertEqual((verified["schema_version"], verified["originals"], verified["captures"]), (2, 1, 1))

    def test_capture_only_deduplicates_locally_and_never_appears_in_search(self):
        other = self.workspace("vault-b", "Хранилище Б")
        digest = sha(CSV)
        metadata = dict(sha256=digest, byte_count=len(CSV), file_type="csv")
        with VaultStore(self.vault, create=True) as first, VaultStore(other, create=True) as second:
            self.assertEqual(first.capture_original(CSV, "csv"), dict(metadata, duplicate=False))
            self.assertEqual(first.get_capture(digest), metadata)
            self.assertEqual(first.read_original(digest), CSV)
            self.assertEqual(first.summary(), EMPTY_SUMMARY)
            self.assertEqual(first.search("Выручка"), [])
            self.assertEqual(first.list_versions("unindexed"), [])
            self.assert_code("original_missing", second.read_original, digest)
            self.assert_code("capture_missing", second.get_capture, digest)
            self.assertEqual(second.capture_original(CSV, "csv"), dict(metadata, duplicate=False))
            path = first.path

        before = path.read_bytes()
        with VaultStore(self.vault) as store:
            self.assertEqual(store.capture_original(CSV, "csv"), dict(metadata, duplicate=True))
            self.assert_code("capture_type_mismatch", store.capture_original, CSV, "txt")
        self.assertEqual(path.read_bytes(), before)

        with VaultStore(self.vault) as store:
            store.import_revision("approved-later", CSV, expected_sha256=digest, text="Факт разрешён отдельно",
                                  extractor="explicit-test")
            self.assertEqual(store.get_capture(digest), metadata)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM originals").fetchone(), (1,))
            self.assertEqual(store.summary(), dict(documents=1, originals=1, versions=1, revisions=1, fts_rows=1))
        self.assertEqual(verify_storage_file(other.vault_root / DB_FILENAME, other.workspace_id)["originals"], 0)

    def test_bad_arguments_leave_unmodified_v1(self):
        with VaultStore(self.vault, create=True) as store:
            before = store.path.read_bytes()
            for data, kind, code in (
                (b"", "txt", "invalid_capture"),
                (bytearray(TEXT), "txt", "invalid_capture"),
                (TEXT, "TXT", "invalid_file_type"),
                (TEXT, "unknown", "invalid_file_type"),
                (b"x" * (MAX_CAPTURE_BYTES + 1), "txt", "capture_too_large"),
            ):
                with self.subTest(code=code):
                    self.assert_code(code, store.capture_original, data, kind)
            self.assert_v1(store._connection)
            self.assertEqual(store.path.read_bytes(), before)

    def test_two_connections_serialize_first_capture_and_duplicate(self):
        barrier = Barrier(2, timeout=5)

        def capture():
            with VaultStore(self.vault) as store:
                barrier.wait()
                return store.capture_original(CSV, "csv")["duplicate"]

        with VaultStore(self.vault, create=True) as observer, ThreadPoolExecutor(max_workers=2) as pool:
            self.assert_v1(observer._connection)
            results = [pool.submit(capture) for _ in range(2)]
            self.assertEqual(sorted(result.result(timeout=15) for result in results), [False, True])
            self.assertEqual(observer.get_capture(sha(CSV))["file_type"], "csv")
            self.assertEqual(observer.summary(), EMPTY_SUMMARY)

    def test_real_disk_full_rolls_back_first_capture_and_migration(self):
        with VaultStore(self.vault, create=True) as store:
            store.import_revision("old", TEXT, expected_sha256=sha(TEXT), text="Прежняя запись", extractor="test")
            connection = store._connection
            allocated = connection.execute("PRAGMA page_count").fetchone()[0]
            original_limit = connection.execute("PRAGMA max_page_count").fetchone()[0]
            self.assertEqual(connection.execute(f"PRAGMA max_page_count = {allocated + 4}").fetchone(),
                             (allocated + 4,))
            before = store.path.read_bytes()
            attempted = []
            connection.set_trace_callback(attempted.append)
            large = b"row,700\n" * 32768
            try:
                failure = self.assert_code("storage_full", store.capture_original, large, "csv")
            finally:
                connection.set_trace_callback(None)
                connection.execute(f"PRAGMA max_page_count = {original_limit}")
            self.assertEqual(failure.__context__.sqlite_errorcode, sqlite3.SQLITE_FULL)
            self.assertTrue(any(line.startswith("CREATE TABLE captures ") for line in attempted))
            self.assertTrue(any(line.startswith("INSERT INTO originals ") for line in attempted))
            self.assertFalse(connection.in_transaction)
            self.assert_v1(connection)
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(store.read_original(sha(TEXT)), TEXT)
            self.assert_code("original_missing", store.read_original, sha(large))
            self.assertFalse(store.capture_original(CSV, "csv")["duplicate"])

    def test_metadata_write_failure_rolls_back_new_original_and_schema(self):
        with VaultStore(self.vault, create=True) as store:
            connection = store._connection
            before = store.path.read_bytes()

            def deny_capture_metadata(action, name, *_rest):
                return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and name == "captures" else sqlite3.SQLITE_OK

            connection.set_authorizer(deny_capture_metadata)
            try:
                self.assert_code("storage_database_error", store.capture_original, CSV, "csv")
            finally:
                connection.set_authorizer(None)
            self.assertFalse(connection.in_transaction)
            self.assert_v1(connection)
            self.assertEqual(store.path.read_bytes(), before)
            self.assert_code("original_missing", store.read_original, sha(CSV))

    def test_capture_backup_and_restore_preserve_zero_index_counts_and_exact_bytes(self):
        location = self.base / "Резерв захвата.sqlite3"
        restored_workspace = self.workspace(self.vault.workspace_id, "Отдельное восстановление")
        with VaultStore(self.vault, create=True) as store:
            store.capture_original(CSV, "csv")
            backup = backup_store(store, location)
        self.assertEqual(backup["schema_version"], CAPTURE_SCHEMA_VERSION)
        self.assertEqual(backup["captures"], 1)
        self.assertEqual({name: backup[name] for name in EMPTY_SUMMARY}, EMPTY_SUMMARY)
        restored = restore_store(restored_workspace, location)
        self.assertEqual((restored["schema_version"], restored["captures"]), (2, 1))
        self.assertEqual(restored["backup_sha256"], backup["sha256"])
        with VaultStore(restored_workspace) as store:
            self.assertEqual(store.get_capture(sha(CSV)), dict(sha256=sha(CSV), byte_count=len(CSV), file_type="csv"))
            self.assertEqual(store.read_original(sha(CSV)), CSV)
            self.assertEqual(store.summary(), EMPTY_SUMMARY)
        self.assert_code("restore_destination_exists", restore_store, restored_workspace, location)
        foreign = self.workspace("wrong", "Чужое восстановление")
        self.assert_code("workspace_mismatch", restore_store, foreign, location)
        self.assertFalse((foreign.vault_root / DB_FILENAME).exists())

    def test_verifier_refuses_corrupt_capture_metadata_blob_and_orphan(self):
        for variant, edits in (
            ("metadata", [("PRAGMA ignore_check_constraints=ON", ()),
                          ("UPDATE captures SET file_type='untrusted'", ())]),
            ("blob", [("UPDATE originals SET data=?", (CSV[:-1] + b"!",))]),
            ("orphan", [("DELETE FROM captures", ())]),
        ):
            with self.subTest(variant=variant):
                vault = self.workspace("capture-" + variant, "Проверка " + variant)
                with VaultStore(vault, create=True) as store:
                    store.capture_original(CSV, "csv")
                    path = store.path
                with closing(sqlite3.connect(path)) as connection, connection:
                    for sql, args in edits:
                        connection.execute(sql, args)
                before = path.read_bytes()
                self.assert_code("storage_integrity_failed", verify_storage_file, path, vault.workspace_id)
                self.assertEqual(path.read_bytes(), before)
                if variant != "orphan":
                    with VaultStore(vault) as store:
                        self.assert_code("storage_integrity_failed", store.get_capture, sha(CSV))
                        self.assert_code("storage_integrity_failed", store.capture_original, CSV, "csv")

    def test_future_and_mismatched_schema_are_refused_without_rewrite(self):
        for version, code in ((3, "storage_version_mismatch"), (1, "storage_schema_mismatch")):
            with self.subTest(version=version):
                vault = self.workspace("version-" + str(version), "Версия " + str(version))
                with VaultStore(vault, create=True) as store:
                    store.capture_original(CSV, "csv")
                    path = store.path
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute(f"PRAGMA user_version={version}")
                before = path.read_bytes()
                self.assert_code(code, VaultStore, vault, create=True)
                self.assert_code(code, verify_storage_file, path, vault.workspace_id)
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
