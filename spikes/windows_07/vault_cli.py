"""Installed CLI for the selected SQLite vault and the pinned fictional PDF."""

import argparse
import hashlib
import json
from pathlib import Path
import sys


SOURCE_ID = 'own-demo-v1'
SOURCE_BYTES = 2327
SOURCE_SHA256 = 'c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451'


def extract_own_text(payload):
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(payload) as document:
        page = document[0]
        try:
            text_page = page.get_textpage()
            try:
                return text_page.get_text_bounded()
            finally:
                text_page.close()
        finally:
            page.close()


def import_own(paths, workspace, store_type, error_type):
    from workspace_demo import calculate_workspace_demo

    source = workspace.resolve_resource(SOURCE_ID)
    with source.open('rb') as stream:
        data = stream.read(SOURCE_BYTES + 1)
    if len(data) != SOURCE_BYTES or hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise error_type('source_hash_mismatch')
    calculation = calculate_workspace_demo(paths, workspace, 'own-vault-import')
    text = extract_own_text(data)
    with store_type(workspace, create=True) as store:
        saved = store.import_revision(SOURCE_ID, data, expected_sha256=SOURCE_SHA256,
                                      text=text, extractor='pdfium-own-v1')
    return {'workspace_id': workspace.workspace_id, 'stored': saved, 'display': calculation['display'],
            'source_page': calculation['source_page'], 'source_sha256': calculation['source_sha256'],
            'source_highlight': calculation['source_highlight'], 'model_calls': 0}


def startup_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--app-data', type=Path, required=True)
    parser.add_argument('--vault', type=Path, required=True)
    parser.add_argument('operation', choices=('import-own', 'search', 'inspect', 'backup', 'restore'))
    parser.add_argument('--query')
    parser.add_argument('--backup-file', type=Path)
    args = parser.parse_args()
    if ((args.query is not None) != (args.operation == 'search')
            or (args.backup_file is not None) != (args.operation in {'backup', 'restore'})):
        parser.error('Only search takes --query; only backup and restore take --backup-file.')
    return args


def write_reply(payload):
    frame = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    sys.stdout.buffer.write(frame + b'\n')
    sys.stdout.buffer.flush()


def main():
    args = startup_args()
    if (not args.install_root.is_absolute() or args.install_root.drive.startswith('\\\\')
            or not sys.flags.isolated or not sys.flags.no_user_site):
        return 4
    root = args.install_root.resolve()
    if (Path(__file__).resolve() != root / 'app/spikes/windows_07/vault_cli.py'
            or Path(sys.prefix).resolve() != root / 'runtime'):
        return 4

    app = root / 'app'
    sys.path.extend(str(app / name) for name in ('src', 'spikes/windows_01', 'spikes/windows_04'))
    from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext, WorkspacePathError
    from financial_assistant.vault_backup import backup_store, restore_store
    from financial_assistant.vault_storage import VaultStorageError, VaultStore

    try:
        paths = ApplicationPaths(args.install_root, args.app_data)
        workspace = WorkspaceContext.open(paths, args.vault)
        if args.operation == 'import-own':
            result = import_own(paths, workspace, VaultStore, VaultStorageError)
        elif args.operation == 'restore':
            result = restore_store(workspace, args.backup_file)
        else:
            with VaultStore(workspace) as store:
                if args.operation == 'search':
                    result = {'workspace_id': workspace.workspace_id, 'matches': store.search(args.query)}
                elif args.operation == 'inspect':
                    result = {'workspace_id': workspace.workspace_id, 'counts': store.summary()}
                else:
                    result = backup_store(store, args.backup_file)
    except (WorkspacePathError, VaultStorageError) as error:
        write_reply({'error': error.code})
        return 3
    except (OSError, ValueError):
        write_reply({'error': 'vault_operation_failed'})
        return 3
    write_reply(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
