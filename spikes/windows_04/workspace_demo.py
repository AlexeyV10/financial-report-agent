"""One native worker action over an explicitly selected local workspace."""

import argparse
import json
from pathlib import Path
import sys


SOURCE_ID = 'own-demo-v1'
SOURCE_SHA = 'c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451'


def bootstrap(install_root):
    if not install_root.is_absolute() or not sys.flags.isolated or not sys.flags.no_user_site:
        return False
    install = install_root.resolve()
    return (Path(__file__).resolve() == install / 'app/spikes/windows_04/workspace_demo.py'
            and Path(sys.prefix).resolve() == install / 'runtime')


def execute(args):
    from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
    from adapter import DemoAdapter
    from renderer import PdfiumRenderer

    paths = ApplicationPaths(args.install_root, args.app_data)
    workspace = WorkspaceContext.open(paths, args.vault)
    source = workspace.resolve_resource(SOURCE_ID)
    for name in ('catalog.json', 'dictionary.json', 'admission.json'):
        paths.asset('app/assets/demo/' + name)
    manifest = paths.asset('app/assets/demo/manifest.json')

    adapter = DemoAdapter(manifest.parent)
    if adapter.manifest['sha256'] != SOURCE_SHA:
        raise ValueError('Unexpected fixture identity')
    adapter.pdf = source
    result = adapter.run(args.run_id)
    frame = PdfiumRenderer().render(adapter, 1, 0, 1)
    receipt = {
        'schema': 'win04-workspace-demo-1',
        'workspace_id': workspace.workspace_id,
        'run_id': args.run_id,
        'source_id': SOURCE_ID,
        'source_sha256': frame['sha256'],
        'source_page': frame['page'],
        'source_highlight': frame['rect'],
        'operation': result['financial_result']['operation_id'],
        'display': result['financial_result']['display_value'],
        'financial_status': result['financial_status'],
        'model_calls': 0,
    }
    workspace.write_receipt(args.run_id, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--app-data', type=Path, required=True)
    parser.add_argument('--vault', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()

    if not bootstrap(args.install_root):
        print(json.dumps({'error': 'application_launch_invalid'}))
        return 2
    app = args.install_root.resolve() / 'app'
    sys.path.extend([str(app / 'src'), str(app / 'spikes/windows_01')])
    from financial_assistant.application_paths import WorkspacePathError

    try:
        print(json.dumps(execute(args), ensure_ascii=True))
    except WorkspacePathError as error:
        print(json.dumps({'error': error.code}))
        return 3
    except (OSError, KeyError, ValueError):
        print(json.dumps({'error': 'demo_input_invalid'}))
        return 4
    return 0


if __name__ == '__main__':
    sys.exit(main())
