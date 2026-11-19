"""Extract a captured office, text or PDF file by its exact digest."""

import argparse
import json
from pathlib import Path
import re
import sys


_SCHEMA = 'win12-extraction-1'
_SHA = re.compile(r'[0-9a-f]{64}')
_CODE = re.compile(r'[a-z][a-z0-9_]{0,63}')


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise ValueError('invalid_extraction_arguments')


def _arguments():
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument('--install-root', required=True, type=Path)
    parser.add_argument('--app-data', required=True, type=Path)
    parser.add_argument('--vault', required=True, type=Path)
    parser.add_argument('--asset-sha', required=True)
    parser.add_argument('--export-csv', action='store_true')
    args = parser.parse_args()
    if not _SHA.fullmatch(args.asset_sha):
        raise ValueError('invalid_asset_sha')
    return args


def _emit(status, *, scope=None, asset=None, file_type=None, error=None, data=None, preview=None):
    state = {'extracted': 'extracted', 'reused': 'extracted', 'unsupported': 'pending', 'error': 'failed'}[status]
    print_error = error if error is None or _CODE.fullmatch(error) else 'extraction_failed'
    payload = {'schema': _SCHEMA, 'status': status, 'error': print_error,
               'workspace_id': scope, 'asset_sha256': asset, 'file_type': file_type,
               'extraction_state': state, 'semantic_state': 'not_reviewed',
               'table_count': len(data['tables']) if data is not None else 0,
               'paragraph_count': len(data['paragraphs']) if data is not None else 0, 'preview': preview or []}
    encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('ascii')
    sys.stdout.buffer.write(encoded + b'\n')
    sys.stdout.buffer.flush()
    return 3 if status == 'error' else 0


def main():
    try:
        args = _arguments()
    except ValueError as error:
        return _emit('error', error=str(error))
    try:
        if not args.install_root.is_absolute() or not sys.flags.isolated or not sys.flags.no_user_site:
            return _emit('error', error='invalid_launch')
        install = args.install_root.resolve(strict=True)
        if (str(install).startswith(('\\\\', '//'))
                or Path(sys.prefix).resolve() != install / 'runtime'
                or Path(__file__).resolve() != install / 'app/spikes/windows_12/extract_cli.py'):
            return _emit('error', error='invalid_launch')
    except (OSError, ValueError):
        return _emit('error', error='invalid_launch')
    sys.path.append(str(install / 'app/src'))
    from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext, WorkspacePathError
    from financial_assistant.office_extraction import extract_capture, preview_rows
    from financial_assistant.office_extraction_common import ExtractionError
    from financial_assistant.text_extract import csv_export
    from financial_assistant.vault_storage import VaultStorageError, VaultStore

    scope = None
    try:
        workspace = WorkspaceContext.open(ApplicationPaths(args.install_root, args.app_data), args.vault)
        scope = workspace.workspace_id
        if args.export_csv:
            with VaultStore(workspace) as store:
                if store.get_capture(args.asset_sha)['file_type'] == 'pdf':
                    raise ExtractionError('pdf_table_export_unavailable')
        status, capture, data = extract_capture(workspace, args.asset_sha)
        file_type = capture['file_type']
        if args.export_csv:
            if data is None or len(data['tables']) != 1:
                raise ExtractionError('csv_export_requires_one_table')
            sys.stdout.buffer.write(csv_export(data['tables'][0]))
            sys.stdout.buffer.flush()
            return 0
        preview = preview_rows(data, file_type) if data is not None else []
        error = None
        if status == 'unsupported':
            error = 'pdf_ocr_pending' if file_type == 'pdf' else 'unsupported_extraction_type'
        return _emit(status, scope=scope, asset=args.asset_sha, file_type=file_type,
                     error=error, data=data, preview=preview)
    except (WorkspacePathError, VaultStorageError, ExtractionError) as error:
        return _emit('error', scope=scope, error=error.code)
    except (OSError, ValueError, TypeError):
        return _emit('error', scope=scope, error='extraction_failed')


if __name__ == '__main__':
    sys.exit(main())
