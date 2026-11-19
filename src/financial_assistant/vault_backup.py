"""Backup and restore the vault's SQLite store as a standalone database."""

from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from time import monotonic

from .application_paths import (
    WorkspaceContext, WorkspacePathError, _component, _inspect, _regular_file,
    _require_disjoint, _root,
)
from .vault_storage import DB_FILENAME, VaultStorageError, VaultStore, verify_storage_file


_SIDECARS = ("-journal", "-wal", "-shm")
_LIVE_SIDECAR_NAMES = {DB_FILENAME.casefold() + suffix for suffix in _SIDECARS}


def _file_path(value):
    try:
        path = Path(value)
        return _root(path.parent) / _component(path.name)
    except (TypeError, ValueError):
        raise VaultStorageError("invalid_backup_path") from None


def _require_absent(path, code):
    try:
        info = _inspect(path)
    except WorkspacePathError:
        raise VaultStorageError("invalid_backup_path") from None
    if info is not None:
        raise VaultStorageError(code)


def _snapshot_digest(path, *, flush=False):
    prior = _regular_file(path, missing="backup_missing")
    with path.open("r+b" if flush else "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.samestat(prior, opened):
            raise VaultStorageError("backup_snapshot_changed")
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if flush:
            os.fsync(stream.fileno())
        after = os.fstat(stream.fileno())
    current = _regular_file(path, missing="backup_missing")
    if any((not os.path.samestat(opened, info) or info.st_size != prior.st_size
            or info.st_mtime_ns != prior.st_mtime_ns) for info in (after, current)):
        raise VaultStorageError("backup_snapshot_changed")
    return {"sha256": digest, "bytes": current.st_size}


def _require_standalone(path):
    if any(_inspect(path.with_name(path.name + suffix)) is not None for suffix in _SIDECARS):
        raise VaultStorageError("backup_snapshot_changed")


def _publish_verified(target, workspace_id, writer, existing_code, failed_code):
    _require_absent(target, existing_code)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix="vault-snapshot-",
                                         suffix=".pending", delete=False) as stream:
            staged = Path(stream.name)
        with closing(sqlite3.connect(staged.as_uri() + "?mode=rw", uri=True)) as destination:
            writer(destination)
            mode, = destination.execute("PRAGMA journal_mode=DELETE").fetchone()
            if mode != "delete":
                raise VaultStorageError(failed_code)

        _require_standalone(staged)
        before = _snapshot_digest(staged)
        verified = verify_storage_file(staged, workspace_id)
        after = _snapshot_digest(staged, flush=True)
        if before != after:
            raise VaultStorageError("backup_snapshot_changed")

        _require_absent(target, existing_code)
        if os.name == "nt":
            # Windows rename refuses to replace a destination. POSIX rename does not.
            staged.rename(target)
        else:
            os.link(staged, target)
        return {**verified, **after}
    except FileExistsError:
        raise VaultStorageError(existing_code) from None
    except (OSError, sqlite3.Error):
        raise VaultStorageError(failed_code) from None
    except WorkspacePathError as error:
        raise VaultStorageError(error.code) from None
    finally:
        if staged is not None:
            for path in (staged, *(staged.with_name(staged.name + suffix) for suffix in _SIDECARS)):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    # Cleanup concerns only private staging files, never a published database.
                    pass


def backup_store(store: VaultStore, target: Path) -> dict:
    """Create a verified SQLite backup without writing installation assets or replacing a file."""
    target = _file_path(target)
    try:
        _require_disjoint(target, store.workspace.paths.install_root)
    except WorkspacePathError:
        raise VaultStorageError("invalid_backup_path") from None
    if target.parent == store.path.parent and target.name.casefold() in _LIVE_SIDECAR_NAMES:
        raise VaultStorageError("invalid_backup_path")
    result = _publish_verified(target, store.workspace_id, store.copy_into,
                               "backup_destination_exists", "backup_failed")
    return {"schema": "win07-backup-1", **result}


def restore_store(workspace: WorkspaceContext, backup: Path) -> dict:
    """Restore only the SQLite store in a separately selected vault of the same identity."""
    source = _file_path(backup)
    target = workspace.vault_root / DB_FILENAME
    _require_absent(target, "restore_destination_exists")
    try:
        _require_standalone(source)
        before = _snapshot_digest(source)
        verify_storage_file(source, workspace.workspace_id)
    except WorkspacePathError as error:
        raise VaultStorageError(error.code) from None
    except (OSError, sqlite3.Error):
        raise VaultStorageError("restore_failed") from None

    def copy(destination):
        deadline = monotonic() + 10.0

        def progress(status, remaining, total):
            if status != sqlite3.SQLITE_DONE and monotonic() >= deadline:
                raise VaultStorageError("restore_failed")

        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=0.1)) as connection:
            connection.backup(destination, pages=64, progress=progress, sleep=0.025)
        _require_standalone(source)
        if _snapshot_digest(source) != before:
            raise VaultStorageError("backup_snapshot_changed")

    result = _publish_verified(target, workspace.workspace_id, copy,
                               "restore_destination_exists", "restore_failed")
    return {"schema": "win07-restore-1", "backup_sha256": before["sha256"], **result}
