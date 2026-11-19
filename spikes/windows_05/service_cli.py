"""Installed command line and fixed worker entrypoint for the WIN-05 service."""

import argparse
import json
from pathlib import Path
import sys


def startup_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--app-data', type=Path, required=True)
    parser.add_argument('--vault', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--run-id')
    mode.add_argument('--worker', action='store_true')
    return parser.parse_args()


def print_final(response, *, success):
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=True, separators=(',', ':')).encode('ascii') + b'\n')
    sys.stdout.buffer.flush()
    return 0 if success else 3


def main():
    args = startup_args()
    if (not args.install_root.is_absolute() or args.install_root.drive.startswith('\\\\')
            or not sys.flags.isolated or not sys.flags.no_user_site):
        return 4
    root = args.install_root.resolve()
    script = root / 'app/spikes/windows_05/service_cli.py'
    if Path(__file__).resolve() != script or Path(sys.prefix).resolve() != root / 'runtime':
        return 4

    app = root / 'app'
    sys.path.extend([str(app / 'src'), str(app / 'spikes/windows_01'), str(app / 'spikes/windows_04')])
    from financial_assistant.application_paths import ApplicationPaths, WorkspacePathError
    from financial_assistant.application_service import ApplicationService
    from financial_assistant.typed_ipc import MAX_REQUEST_BYTES, TypedIpcError, decode_request, exchange, make_request
    from workspace_demo import calculate_workspace_demo

    request = None
    try:
        paths = ApplicationPaths(args.install_root, args.app_data)
        service = ApplicationService(paths, args.vault, calculate_workspace_demo)
        if args.worker:
            request = decode_request(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
            sys.stdout.buffer.write(service.evaluate(request))
            sys.stdout.buffer.flush()
            return 0

        _, context_id = service.context()
        request = make_request(context_id, args.run_id)
        worker_argv = [str(root / 'runtime/python.exe'), '-I', '-B', '-X', 'utf8', str(script),
                       '--install-root', str(paths.install_root), '--app-data', str(paths.app_data_root),
                       '--vault', str(args.vault), '--worker']
        response = service.persist(request, exchange(worker_argv, request, cwd=root))
    except TypedIpcError as error:
        if args.worker or request is None:
            return 4
        response = service.failure(request, error.code)
    except (WorkspacePathError, OSError):
        return 4
    return print_final(response, success=response['status'] == 'completed')


if __name__ == '__main__':
    sys.exit(main())
