"""Explicit installation, application-data and vault paths for the Windows app."""

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from types import MappingProxyType


class WorkspacePathError(ValueError):
    """A stable path or resource failure without a private path in the message."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_DOS_DEVICE = re.compile(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]", re.I)
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _identifier(value, code):
    if type(value) is not str or not _ID.fullmatch(value):
        raise WorkspacePathError(code)
    return value


def _component(value):
    if (not value or value.endswith((".", " "))
            or any(ord(char) < 32 or char in '<>:"|?*' for char in value)
            or _DOS_DEVICE.fullmatch(value.split(".", 1)[0].rstrip(" "))):
        raise WorkspacePathError("invalid_relative_path")
    return value


def _relative(value):
    if type(value) is not str:
        raise WorkspacePathError("invalid_relative_path")
    return tuple(_component(part) for part in value.replace("\\", "/").split("/"))


def _inspect(path, *, missing=None):
    """Reject symlinks and Windows reparse points anywhere along an absolute path."""
    current = Path(path.anchor)
    try:
        info = current.lstat()
        for part in path.parts[1:]:
            if not stat.S_ISDIR(info.st_mode):
                raise WorkspacePathError("invalid_relative_path")
            current /= part
            info = current.lstat()
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT):
                raise WorkspacePathError("path_escape")
        return info
    except FileNotFoundError:
        if missing is not None:
            raise WorkspacePathError(missing) from None
        return None
    except OSError:
        raise WorkspacePathError("filesystem_access_error") from None


def _directory(path, *, create_later=False):
    info = _inspect(path, missing=None if create_later else "invalid_root")
    if info is not None and not stat.S_ISDIR(info.st_mode):
        raise WorkspacePathError("invalid_root")
    return path


def _root(value, *, create_later=False):
    try:
        path = Path(value)
    except TypeError:
        raise WorkspacePathError("invalid_root") from None
    if not path.is_absolute() or path.anchor.startswith(("\\\\", "//")):
        raise WorkspacePathError("invalid_root")
    try:
        for part in path.parts[1:]:
            _component(part)
    except WorkspacePathError:
        raise WorkspacePathError("invalid_root") from None
    _directory(path, create_later=create_later)
    try:
        path = path.resolve(strict=not create_later)
    except (OSError, RuntimeError):
        raise WorkspacePathError("invalid_root") from None
    if path.anchor.startswith(("\\\\", "//")):
        raise WorkspacePathError("invalid_root")
    return _directory(path, create_later=create_later)


def _require_disjoint(first, second):
    first_parts = tuple(part.casefold() for part in first.parts)
    second_parts = tuple(part.casefold() for part in second.parts)
    shared_length = min(len(first_parts), len(second_parts))
    if first_parts[:shared_length] == second_parts[:shared_length]:
        raise WorkspacePathError("root_overlap")


def _regular_file(path, missing="source_missing"):
    info = _inspect(path, missing=missing)
    if not stat.S_ISREG(info.st_mode):
        raise WorkspacePathError("invalid_source")
    return info


def _unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise WorkspacePathError("invalid_workspace")
        fields[key] = value
    return fields


@dataclass(frozen=True, slots=True)
class _ExactResource:
    parts: tuple[str, ...]
    size: int
    digest: str

    @classmethod
    def parse(cls, value):
        if (type(value) is not dict or value.keys() != {"path", "bytes", "sha256"}
                or type(value["bytes"]) is not int or value["bytes"] < 0
                or type(value["sha256"]) is not str or not _SHA256.fullmatch(value["sha256"])):
            raise WorkspacePathError("invalid_resource_binding")
        return cls(_relative(value["path"]), value["bytes"], value["sha256"])

    def resolve(self, root):
        path = root.joinpath(*self.parts)
        before = _regular_file(path)
        if before.st_size != self.size:
            raise WorkspacePathError("source_size_mismatch")
        try:
            with path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                if not os.path.samestat(before, opened):
                    raise WorkspacePathError("source_changed")
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
                after = os.fstat(stream.fileno())
        except FileNotFoundError:
            raise WorkspacePathError("source_missing") from None
        except OSError:
            raise WorkspacePathError("filesystem_access_error") from None
        current = _regular_file(path)
        if (not os.path.samestat(after, current) or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or after.st_size != current.st_size or after.st_mtime_ns != current.st_mtime_ns):
            raise WorkspacePathError("source_changed")
        if actual != self.digest:
            raise WorkspacePathError("source_hash_mismatch")
        return path


@dataclass(frozen=True, slots=True)
class ApplicationPaths:
    """Installation is read-only. A new app-data directory may be created later."""

    install_root: Path
    app_data_root: Path

    def __post_init__(self):
        install = _root(self.install_root)
        app_data = _root(self.app_data_root, create_later=True)
        _require_disjoint(install, app_data)
        object.__setattr__(self, "install_root", install)
        object.__setattr__(self, "app_data_root", app_data)

    def asset(self, relative_path: str) -> Path:
        path = self.install_root.joinpath(*_relative(relative_path))
        _regular_file(path)
        return path

    @property
    def cache_root(self) -> Path:
        return _directory(self.app_data_root / "cache", create_later=True)

    @property
    def models_root(self) -> Path:
        return _directory(self.app_data_root / "models", create_later=True)

    @property
    def logs_root(self) -> Path:
        return _directory(self.app_data_root / "logs", create_later=True)


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """A single vault verified from its own on-disk workspace.json marker."""

    paths: ApplicationPaths
    vault_root: Path
    workspace_id: str
    _resources: Mapping[str, _ExactResource]

    @classmethod
    def open(cls, paths: ApplicationPaths, vault_root: Path) -> "WorkspaceContext":
        root = _root(vault_root)
        _require_disjoint(root, paths.install_root)
        _require_disjoint(root, paths.app_data_root)
        marker = root / "workspace.json"
        _regular_file(marker, missing="invalid_workspace")
        try:
            content = json.loads(marker.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_fields)
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise WorkspacePathError("invalid_workspace") from None
        if (type(content) is not dict or content.keys() != {"schema", "workspace_id", "resources"}
                or content["schema"] != "workspace-context-1" or type(content["resources"]) is not list):
            raise WorkspacePathError("invalid_workspace")
        workspace_id = _identifier(content["workspace_id"], "invalid_workspace")
        resources = {}
        seen = set()
        for row in content["resources"]:
            if type(row) is not dict or row.keys() != {"id", "path", "bytes", "sha256"}:
                raise WorkspacePathError("invalid_resource_binding")
            resource_id = _identifier(row["id"], "invalid_resource_id")
            if resource_id.lower() in seen:
                raise WorkspacePathError("duplicate_resource")
            seen.add(resource_id.lower())
            resources[resource_id] = _ExactResource.parse({key: row[key] for key in ("path", "bytes", "sha256")})
        return cls(paths, root, workspace_id, MappingProxyType(resources))

    def resolve_resource(self, resource_id: str) -> Path:
        """Check current bytes before returning a path for immediate use."""
        key = _identifier(resource_id, "invalid_resource_id")
        resource = self._resources.get(key)
        if resource is None:
            raise WorkspacePathError("resource_not_registered")
        return resource.resolve(self.vault_root)

    @property
    def resource_registry_sha256(self) -> str:
        bindings = [
            (key, '/'.join(resource.parts), resource.size, resource.digest)
            for key, resource in sorted(self._resources.items())
        ]
        encoded = json.dumps(bindings, ensure_ascii=True, separators=(',', ':')).encode('ascii')
        return hashlib.sha256(encoded).hexdigest()

    def write_receipt(self, run_id: str, payload: dict) -> Path:
        key = _identifier(run_id, "invalid_run_id").lower()
        try:
            filename = _component(key + ".json")
        except WorkspacePathError:
            raise WorkspacePathError("invalid_run_id") from None
        try:
            text = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
            if type(payload) is not dict or json.loads(text) != payload:
                raise ValueError()
            data = (text + "\n").encode("utf-8")
        except (ValueError, TypeError, RecursionError):
            raise WorkspacePathError("invalid_receipt") from None

        _directory(self.vault_root)
        directory = _directory(self.vault_root / "runs", create_later=True)
        target = directory / filename
        pending = None
        try:
            directory.mkdir(exist_ok=True)
            _directory(directory)
            if _inspect(target) is not None:
                raise WorkspacePathError("duplicate_run")
            with tempfile.NamedTemporaryFile(dir=directory, prefix="receipt-", suffix=".pending", delete=False) as stream:
                pending = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            _directory(directory)
            # Same-directory publication is atomic. POSIX rename would replace an existing file.
            if os.name == "nt":
                pending.rename(target)
                pending = None
            else:
                os.link(pending, target)
        except FileExistsError:
            raise WorkspacePathError("duplicate_run") from None
        except OSError:
            raise WorkspacePathError("filesystem_access_error") from None
        finally:
            if pending is not None:
                try:
                    _directory(directory)
                    pending.unlink(missing_ok=True)
                except (OSError, WorkspacePathError):
                    # Preserve the publication outcome if a separate cleanup fails.
                    pass
        return target


def resolve_legacy_resource(legacy_root: Path, bindings: Mapping[str, dict], resource_id: str) -> Path:
    """Verify an explicitly mapped exact resource below a caller-supplied legacy root."""
    key = _identifier(resource_id, "invalid_resource_id")
    if not isinstance(bindings, Mapping):
        raise WorkspacePathError("invalid_resource_binding")
    if key not in bindings:
        raise WorkspacePathError("resource_not_registered")
    return _ExactResource.parse(bindings[key]).resolve(_root(legacy_root))
