"""Transactional metadata, immutable originals and literal FTS within one vault."""

from contextlib import closing, contextmanager
import hashlib
from pathlib import Path
import re
import sqlite3
import stat
from time import monotonic

from .application_paths import WorkspaceContext, WorkspacePathError, _component, _inspect, _root


DB_FILENAME = "vault.sqlite3"
APPLICATION_ID = int.from_bytes(b"PPVS", "big")
SCHEMA_VERSION = 1
CAPTURE_SCHEMA_VERSION = 2
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024 * 1024
MAX_QUERY_BYTES = 4096
MIN_SQLITE = (3, 44, 0)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA = re.compile(r"[a-f0-9]{64}")
_COUNTS = ("documents", "originals", "versions", "revisions", "fts_rows")
CAPTURE_FILE_TYPES = ("pdf", "xlsx", "docx", "png", "jpeg", "tiff", "csv", "txt")
_SCHEMA = {
    "vault_metadata": "CREATE TABLE vault_metadata (workspace_id TEXT PRIMARY KEY NOT NULL) STRICT",
    "documents": "CREATE TABLE documents (document_id TEXT PRIMARY KEY NOT NULL) STRICT",
    "originals": (
        "CREATE TABLE originals (sha256 TEXT PRIMARY KEY NOT NULL, byte_count INTEGER NOT NULL "
        "CHECK (byte_count BETWEEN 0 AND 16777216), data BLOB NOT NULL CHECK (length(data) = byte_count)) STRICT"
    ),
    "document_versions": (
        "CREATE TABLE document_versions (id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents, "
        "version INTEGER NOT NULL CHECK (version > 0), sha256 TEXT NOT NULL REFERENCES originals, "
        "UNIQUE (document_id, version), UNIQUE (document_id, sha256)) STRICT"
    ),
    "revisions": (
        "CREATE TABLE revisions (id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL REFERENCES document_versions, "
        "revision INTEGER NOT NULL CHECK (revision > 0), extractor TEXT NOT NULL, text TEXT NOT NULL, "
        "text_sha256 TEXT NOT NULL, UNIQUE (version_id, revision), UNIQUE (version_id, extractor, text_sha256)) STRICT"
    ),
    "revision_fts": "CREATE VIRTUAL TABLE revision_fts USING fts5(text, tokenize='unicode61')",
}
_CAPTURE_TABLE = (
    "CREATE TABLE captures (sha256 TEXT PRIMARY KEY NOT NULL REFERENCES originals "
    "CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'), "
    "file_type TEXT NOT NULL CHECK (file_type IN ("
    + ", ".join(f"'{file_type}'" for file_type in CAPTURE_FILE_TYPES) + "))) STRICT"
)
_SCHEMAS = {SCHEMA_VERSION: _SCHEMA, CAPTURE_SCHEMA_VERSION: {**_SCHEMA, "captures": _CAPTURE_TABLE}}
_FTS_SHADOWS = {"revision_fts_" + suffix for suffix in ("data", "idx", "content", "docsize", "config")}
_SQLITE_ERRORS = {
    sqlite3.SQLITE_FULL: "storage_full", sqlite3.SQLITE_BUSY: "storage_busy",
    sqlite3.SQLITE_LOCKED: "storage_busy", sqlite3.SQLITE_READONLY: "storage_readonly",
    sqlite3.SQLITE_CORRUPT: "storage_corrupt", sqlite3.SQLITE_NOTADB: "storage_corrupt",
}


class VaultStorageError(ValueError):
    """A storage failure code without private paths or raw SQLite messages."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@contextmanager
def _sqlite_errors():
    try:
        yield
    except sqlite3.Error as error:
        primary = getattr(error, "sqlite_errorcode", 0) & 0xff
        raise VaultStorageError(_SQLITE_ERRORS.get(primary, "storage_database_error")) from None


def _identifier(value, code):
    if type(value) is not str or not _ID.fullmatch(value):
        raise VaultStorageError(code)
    return value


def _digest(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise VaultStorageError("invalid_digest")
    return value


def _text_bytes(value, maximum, error):
    if type(value) is not str or len(value) > maximum or "\0" in value:
        raise VaultStorageError(error)
    try:
        raw = value.encode("utf-8")
    except UnicodeError:
        raise VaultStorageError(error) from None
    if len(raw) > maximum:
        raise VaultStorageError(error)
    return raw


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _checked_path(value):
    try:
        path = Path(value)
        root = _root(path.parent)
        path = root / _component(path.name)
        info = _inspect(path)
        if info is not None and not stat.S_ISREG(info.st_mode):
            raise VaultStorageError("invalid_storage_path")
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = _inspect(path.with_name(path.name + suffix))
            if sidecar is not None and not stat.S_ISREG(sidecar.st_mode):
                raise VaultStorageError("invalid_storage_path")
    except (TypeError, WorkspacePathError):
        raise VaultStorageError("invalid_storage_path") from None
    return path, info is not None


def _connect(path, mode):
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise VaultStorageError("sqlite_version_unsupported")
    connection = sqlite3.connect(path.as_uri() + "?mode=" + mode, uri=True, timeout=5, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        if hasattr(connection, "setconfig") and hasattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE"):
            connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise VaultStorageError("storage_journal_mode_unsupported")
    except BaseException:
        connection.close()
        raise
    return connection


def _metadata(connection):
    return (connection.execute("PRAGMA application_id").fetchone()[0],
            connection.execute("PRAGMA user_version").fetchone()[0])


def _empty_schema(connection):
    return connection.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone() is None


def _check_identity(connection, workspace_id):
    application_id, version = _metadata(connection)
    if application_id != APPLICATION_ID:
        raise VaultStorageError("storage_application_mismatch")
    if version not in _SCHEMAS:
        raise VaultStorageError("storage_version_mismatch")
    rows = connection.execute("SELECT type, name, sql FROM sqlite_schema")
    definitions, shadows = {}, set()
    for kind, name, definition in rows:
        if kind == "index" and name.startswith("sqlite_autoindex_") and definition is None:
            continue
        if kind != "table":
            raise VaultStorageError("storage_schema_mismatch")
        if name in _FTS_SHADOWS:
            shadows.add(name)
        else:
            definitions[name] = definition
    if definitions != _SCHEMAS[version] or shadows != _FTS_SHADOWS:
        raise VaultStorageError("storage_schema_mismatch")
    if connection.execute("SELECT workspace_id FROM vault_metadata LIMIT 2").fetchall() != [(workspace_id,)]:
        raise VaultStorageError("workspace_mismatch")
    return version


def _initialize(connection, workspace_id):
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        if _metadata(connection) == (0, 0) and _empty_schema(connection):
            for definition in _SCHEMA.values():
                connection.execute(definition)
            connection.execute("INSERT INTO vault_metadata (workspace_id) VALUES (?)", (workspace_id,))
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        _check_identity(connection, workspace_id)


def _summary(connection):
    counts = connection.execute(
        "SELECT (SELECT count(*) FROM documents), (SELECT count(DISTINCT sha256) FROM document_versions), "
        "(SELECT count(*) FROM document_versions), (SELECT count(*) FROM revisions), "
        "(SELECT count(*) FROM revision_fts)"
    ).fetchone()
    return dict(zip(_COUNTS, counts, strict=True))


def _ensure_original(connection, digest, data):
    row = connection.execute("SELECT byte_count, data FROM originals WHERE sha256=?", (digest,)).fetchone()
    if row is None:
        connection.execute("INSERT INTO originals VALUES (?, ?, ?)", (digest, len(data), data))
    elif row != (len(data), data):
        raise VaultStorageError("storage_integrity_failed")


def _checked_original(digest, length, data):
    if type(data) is not bytes or len(data) != length or _sha(data) != digest:
        raise VaultStorageError("storage_integrity_failed")
    return data


class VaultStore:
    """One explicit workspace owns one database connection. Close it after use."""

    def __init__(self, workspace: WorkspaceContext, *, create=False):
        if not isinstance(workspace, WorkspaceContext) or type(create) is not bool:
            raise VaultStorageError("invalid_workspace")
        self.workspace = workspace
        self.workspace_id = _identifier(workspace.workspace_id, "invalid_workspace")
        self.path, exists = _checked_path(workspace.vault_root / DB_FILENAME)
        if not exists and not create:
            raise VaultStorageError("storage_missing")
        with _sqlite_errors():
            connection = _connect(self.path, "rwc" if create else "rw")
            try:
                if create:
                    _initialize(connection, self.workspace_id)
                else:
                    with connection:
                        connection.execute("BEGIN")
                        _check_identity(connection, self.workspace_id)
            except BaseException:
                connection.close()
                raise
        self._connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self):
        self._connection.close()

    def capture_original(self, data: bytes, file_type: str) -> dict:
        """Store the detected file's exact bytes without creating any indexed version."""
        if type(data) is not bytes or not data:
            raise VaultStorageError("invalid_capture")
        if len(data) > MAX_CAPTURE_BYTES:
            raise VaultStorageError("capture_too_large")
        if type(file_type) is not str or file_type not in CAPTURE_FILE_TYPES:
            raise VaultStorageError("invalid_file_type")

        digest = _sha(data)
        connection = self._connection
        with _sqlite_errors(), connection:
            connection.execute("BEGIN IMMEDIATE")
            if _check_identity(connection, self.workspace_id) == SCHEMA_VERSION:
                connection.execute(_CAPTURE_TABLE)
                connection.execute(f"PRAGMA user_version={CAPTURE_SCHEMA_VERSION}")
            _ensure_original(connection, digest, data)
            prior = connection.execute("SELECT file_type FROM captures WHERE sha256=?", (digest,)).fetchone()
            if prior is None:
                connection.execute("INSERT INTO captures VALUES (?, ?)", (digest, file_type))
            elif prior[0] not in CAPTURE_FILE_TYPES:
                raise VaultStorageError("storage_integrity_failed")
            elif prior[0] != file_type:
                raise VaultStorageError("capture_type_mismatch")
        return {"sha256": digest, "byte_count": len(data), "file_type": file_type, "duplicate": prior is not None}

    def get_capture(self, sha256: str) -> dict:
        digest = _digest(sha256)
        connection = self._connection
        with _sqlite_errors(), connection:
            connection.execute("BEGIN")
            if _check_identity(connection, self.workspace_id) == SCHEMA_VERSION:
                raise VaultStorageError("capture_missing")
            row = connection.execute(
                "SELECT o.byte_count, o.data, c.file_type FROM captures c "
                "LEFT JOIN originals o ON o.sha256=c.sha256 WHERE c.sha256=?", (digest,),
            ).fetchone()
            if row is None:
                raise VaultStorageError("capture_missing")
            length, data, file_type = row
            if file_type not in CAPTURE_FILE_TYPES or length == 0:
                raise VaultStorageError("storage_integrity_failed")
            _checked_original(digest, length, data)
        return {"sha256": digest, "byte_count": length, "file_type": file_type}

    def import_revision(self, document_id: str, data: bytes, *, expected_sha256: str,
                        text: str, extractor: str) -> dict:
        document_id = _identifier(document_id, "invalid_document_id")
        digest = _digest(expected_sha256)
        if type(data) is not bytes:
            raise VaultStorageError("invalid_capture")
        if len(data) > MAX_CAPTURE_BYTES:
            raise VaultStorageError("capture_too_large")
        if _sha(data) != digest:
            raise VaultStorageError("source_hash_mismatch")
        text_digest = _sha(_text_bytes(text, MAX_TEXT_BYTES, "invalid_text"))
        _text_bytes(extractor, 256, "invalid_extractor")
        if not extractor.strip():
            raise VaultStorageError("invalid_extractor")

        connection = self._connection
        with _sqlite_errors(), connection:
            connection.execute("BEGIN IMMEDIATE")
            _ensure_original(connection, digest, data)

            connection.execute("INSERT INTO documents VALUES (?) ON CONFLICT(document_id) DO NOTHING", (document_id,))
            version_row = connection.execute(
                "SELECT id, version FROM document_versions WHERE document_id=? AND sha256=?", (document_id, digest)
            ).fetchone()
            if version_row is None:
                version_id, version = connection.execute(
                    "INSERT INTO document_versions (document_id, version, sha256) "
                    "SELECT ?, COALESCE(MAX(version), 0) + 1, ? FROM document_versions WHERE document_id=? "
                    "RETURNING id, version", (document_id, digest, document_id)
                ).fetchone()
            else:
                version_id, version = version_row

            prior = connection.execute(
                "SELECT revision, text FROM revisions WHERE version_id=? AND extractor=? AND text_sha256=?",
                (version_id, extractor, text_digest)
            ).fetchone()
            if prior is None:
                revision_id, revision = connection.execute(
                    "INSERT INTO revisions (version_id, revision, extractor, text, text_sha256) "
                    "SELECT ?, COALESCE(MAX(revision), 0) + 1, ?, ?, ? FROM revisions WHERE version_id=? "
                    "RETURNING id, revision", (version_id, extractor, text, text_digest, version_id)
                ).fetchone()
                connection.execute("INSERT INTO revision_fts (rowid, text) VALUES (?, ?)", (revision_id, text))
            else:
                revision, prior_text = prior
                if prior_text != text:
                    raise VaultStorageError("storage_integrity_failed")
        return {"document_id": document_id, "version": version, "revision": revision,
                "sha256": digest, "duplicate": prior is not None}

    def read_original(self, sha256: str) -> bytes:
        digest = _digest(sha256)
        with _sqlite_errors():
            row = self._connection.execute("SELECT byte_count, data FROM originals WHERE sha256=?", (digest,)).fetchone()
        if row is None:
            raise VaultStorageError("original_missing")
        length, data = row
        return _checked_original(digest, length, data)

    def list_versions(self, document_id: str) -> list:
        document_id = _identifier(document_id, "invalid_document_id")
        versions = {}
        with _sqlite_errors():
            rows = self._connection.execute(
                "SELECT v.version, v.sha256, o.byte_count, r.revision, r.extractor, r.text_sha256 "
                "FROM document_versions v JOIN originals o ON o.sha256=v.sha256 "
                "JOIN revisions r ON r.version_id=v.id WHERE v.document_id=? ORDER BY v.version, r.revision",
                (document_id,)
            )
            for version, digest, length, revision, extractor, text_digest in rows:
                if version not in versions:
                    versions[version] = {"version": version, "sha256": digest, "bytes": length, "revisions": []}
                versions[version]["revisions"].append({"revision": revision, "extractor": extractor,
                                                        "text_sha256": text_digest})
        return list(versions.values())

    def search(self, query: str, *, limit=20) -> list:
        _text_bytes(query, MAX_QUERY_BYTES, "invalid_query")
        if not query.strip():
            raise VaultStorageError("invalid_query")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise VaultStorageError("invalid_limit")
        literal = '"' + query.replace('"', '""') + '"'
        with _sqlite_errors():
            rows = self._connection.execute(
                "SELECT v.document_id, v.version, r.revision, v.sha256, r.extractor "
                "FROM revision_fts JOIN revisions r ON r.id=revision_fts.rowid "
                "JOIN document_versions v ON v.id=r.version_id WHERE revision_fts MATCH ? "
                "ORDER BY v.document_id, v.version, r.revision LIMIT ?", (literal, limit)
            ).fetchall()
        fields = ("document_id", "version", "revision", "sha256", "extractor")
        return [dict(zip(fields, row, strict=True)) for row in rows]

    def summary(self) -> dict:
        with _sqlite_errors():
            return _summary(self._connection)

    def copy_into(self, sqlite_destination_connection: sqlite3.Connection) -> None:
        dest = sqlite_destination_connection
        source = self._connection
        if not isinstance(dest, sqlite3.Connection) or dest is source:
            raise VaultStorageError("invalid_backup_destination")
        deadline = monotonic() + 5

        def progress(status, _remaining, _total):
            if status != sqlite3.SQLITE_DONE and monotonic() >= deadline:
                code = "storage_busy" if status in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} else "backup_timeout"
                raise VaultStorageError(code)

        with _sqlite_errors():
            if (dest.in_transaction or _metadata(dest) != (0, 0) or not _empty_schema(dest)):
                raise VaultStorageError("invalid_backup_destination")
            if source.in_transaction:
                raise VaultStorageError("storage_busy")
            source.backup(dest, pages=64, progress=progress, sleep=0.025)


def _check_contents(connection, version):
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise VaultStorageError("storage_integrity_failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise VaultStorageError("storage_integrity_failed")
    for digest, length, data in connection.execute("SELECT sha256, byte_count, data FROM originals"):
        _checked_original(digest, length, data)
    for digest, text in connection.execute("SELECT text_sha256, text FROM revisions"):
        if _sha(_text_bytes(text, MAX_TEXT_BYTES, "storage_integrity_failed")) != digest:
            raise VaultStorageError("storage_integrity_failed")
    orphaned = "SELECT 1 FROM originals o LEFT JOIN document_versions v ON v.sha256=o.sha256 WHERE v.id IS NULL"
    if version == CAPTURE_SCHEMA_VERSION:
        placeholders = ", ".join("?" for _ in CAPTURE_FILE_TYPES)
        if connection.execute(
            "SELECT 1 FROM captures c JOIN originals o ON o.sha256=c.sha256 "
            f"WHERE o.byte_count=0 OR c.file_type NOT IN ({placeholders}) LIMIT 1", CAPTURE_FILE_TYPES,
        ).fetchone() is not None:
            raise VaultStorageError("storage_integrity_failed")
        orphaned += " AND NOT EXISTS (SELECT 1 FROM captures c WHERE c.sha256=o.sha256)"
    invalid = (
        "SELECT 1 FROM revisions r LEFT JOIN revision_fts f ON f.rowid=r.id WHERE f.rowid IS NULL OR f.text IS NOT r.text LIMIT 1",
        "SELECT 1 FROM revision_fts f LEFT JOIN revisions r ON r.id=f.rowid WHERE r.id IS NULL LIMIT 1",
        "SELECT 1 FROM document_versions v LEFT JOIN revisions r ON r.version_id=v.id "
        "GROUP BY v.id HAVING MIN(r.revision) IS NOT 1 OR MAX(r.revision) <> COUNT(r.id) LIMIT 1",
        "SELECT 1 FROM documents d LEFT JOIN document_versions v ON v.document_id=d.document_id "
        "GROUP BY d.document_id HAVING MIN(v.version) IS NOT 1 OR MAX(v.version) <> COUNT(v.id) LIMIT 1",
        orphaned + " LIMIT 1",
    )
    if any(connection.execute(query).fetchone() is not None for query in invalid):
        raise VaultStorageError("storage_integrity_failed")


def verify_storage_file(path: Path, workspace_id: str) -> dict:
    """Verify an exact, already initialized database without modifying it."""
    workspace_id = _identifier(workspace_id, "invalid_workspace")
    path, exists = _checked_path(path)
    if not exists:
        raise VaultStorageError("storage_missing")
    with _sqlite_errors(), closing(_connect(path, "ro")) as connection, connection:
        connection.execute("BEGIN")
        version = _check_identity(connection, workspace_id)
        _check_contents(connection, version)
        counts = _summary(connection)
        if version == CAPTURE_SCHEMA_VERSION:
            counts["captures"], = connection.execute("SELECT count(*) FROM captures").fetchone()
    return {"workspace_id": workspace_id, "application_id": APPLICATION_ID, "schema_version": version,
            "integrity_ok": True, "foreign_keys_ok": True, "original_hashes_ok": True, "fts_consistency_ok": True,
            **counts}
