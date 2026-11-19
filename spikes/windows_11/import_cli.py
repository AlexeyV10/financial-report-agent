"""Capture a structurally accepted local file without producing financial facts."""

import argparse
import json
from pathlib import Path
import re
import sys


_SCHEMA = 'win11-import-1'
_ERROR_CODE = re.compile(r'[a-z][a-z0-9_]{0,63}')


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise ValueError('invalid_import_arguments')


def _arguments():
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument('--install-root', required=True, type=Path)
    parser.add_argument('--app-data', required=True, type=Path)
    parser.add_argument('--vault', required=True, type=Path)
    parser.add_argument('--path', required=True, type=Path)
    return parser.parse_args()


def _emit(status, *, workspace_id=None, error=None, capture=None):
    accepted = capture is not None
    body = {'schema': _SCHEMA, 'status': status, 'workspace_id': workspace_id,
            'error': error if error is None or _ERROR_CODE.fullmatch(error) else 'import_failed',
            'asset_sha256': capture['sha256'] if accepted else None,
            'byte_count': capture['byte_count'] if accepted else None,
            'file_type': capture['file_type'] if accepted else None,
            'file_state': 'accepted' if accepted else 'rejected' if status == 'rejected' else 'unavailable',
            'extraction_state': 'pending' if accepted else 'not_started',
            'semantic_state': 'not_reviewed' if accepted else 'not_started'}
    frame = json.dumps(body, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('ascii') + b'\n'
    sys.stdout.buffer.write(frame)
    sys.stdout.buffer.flush()
    return 3 if status == 'error' else 0


def main():
    try:
        args = _arguments()
    except ValueError:
        return _emit('error', error='invalid_import_arguments')
    try:
        if not args.install_root.is_absolute() or not sys.flags.isolated or not sys.flags.no_user_site:
            return _emit('error', error='invalid_launch')
        install = args.install_root.resolve(strict=True)
        if (str(install).startswith(('\\\\', '//'))
                or Path(__file__).resolve() != install / 'app/spikes/windows_11/import_cli.py'
                or Path(sys.prefix).resolve() != install / 'runtime'):
            return _emit('error', error='invalid_launch')
    except (OSError, ValueError):
        return _emit('error', error='invalid_launch')
    sys.path.append(str(install / 'app/src'))
    from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext, WorkspacePathError
    from financial_assistant.safe_import import ImportValidationError, classify_bytes, read_candidate
    from financial_assistant.vault_storage import VaultStorageError, VaultStore

    scope = None
    try:
        workspace = WorkspaceContext.open(ApplicationPaths(args.install_root, args.app_data), args.vault)
        scope = workspace.workspace_id
        data = read_candidate(args.path)
        file_type = classify_bytes(data)
        with VaultStore(workspace, create=True) as store:
            capture = store.capture_original(data, file_type)
    except ImportValidationError as error:
        return _emit('rejected', workspace_id=scope, error=error.code)
    except (VaultStorageError, WorkspacePathError) as error:
        return _emit('error', workspace_id=scope, error=error.code)
    except (OSError, ValueError):
        return _emit('error', workspace_id=scope, error='import_failed')
    status = 'duplicate' if capture['duplicate'] else 'captured'
    return _emit(status, workspace_id=scope, capture=capture)


if __name__ == '__main__':
    sys.exit(main())
