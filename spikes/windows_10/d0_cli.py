"""One fixed D0 worker invocation using the installed private Python runtime."""

import argparse
import json
from pathlib import Path
import sys


_SCHEMA = "win10-d0-1"


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise ValueError("invalid_arguments")


def _start():
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--app-data", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--provision", action="store_true")
    mode.add_argument("--run-id")
    parser.add_argument("--operation", choices=("direct", "delta", "relative", "scale", "margin"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--historical", action="store_true")
    source.add_argument("--question")
    args = parser.parse_args()
    if (args.provision and (args.operation is not None or args.historical or args.question is not None)) or (
            not args.provision and args.operation is None):
        raise ValueError("invalid_arguments")
    return args


def _framed(result):
    return (json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")


def _emit(result):
    sys.stdout.buffer.write(_framed(result))
    sys.stdout.buffer.flush()
    return 3 if result["status"] == "error" else 0


def _startup_error(code):
    return _emit({"schema": _SCHEMA, "status": "error", "operation": None, "run_id": None, "display": None,
                  "reason": code, "trace": [], "source_sha256": None, "source_page": None})


def main():
    try:
        args = _start()
    except ValueError:
        return _startup_error("invalid_arguments")
    try:
        if (not args.install_root.is_absolute() or args.install_root.drive.startswith("\\\\")
                or not sys.flags.isolated or not sys.flags.no_user_site):
            return _startup_error("invalid_launch")
        root = args.install_root.resolve(strict=True)
        if (Path(__file__).resolve() != root / "app/spikes/windows_10/d0_cli.py"
                or Path(sys.prefix).resolve() != root / "runtime"):
            return _startup_error("invalid_launch")
    except (OSError, ValueError):
        return _startup_error("invalid_launch")

    sys.path.append(str(root / "app/src"))
    from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext, WorkspacePathError
    from financial_assistant.d0_service import MAX_FRAME_BYTES, D0ServiceError, provision_d0, reply, run_d0, valid_run_id
    from financial_assistant.vault_storage import VaultStorageError

    operation = "provision" if args.provision else args.operation
    run_id = args.run_id if valid_run_id(args.run_id) else None
    try:
        paths = ApplicationPaths(args.install_root, args.app_data)
        if args.provision:
            provision_d0(paths, args.vault)
            result = reply("answered", operation, None, "ok")
        else:
            workspace = WorkspaceContext.open(paths, args.vault)
            result = run_d0(workspace, args.run_id, operation, historical=args.historical, question=args.question)
    except (D0ServiceError, WorkspacePathError, VaultStorageError) as error:
        result = reply("error", operation, run_id, error.code)
    except Exception:
        result = reply("error", operation, run_id, "d0_failed")
    if len(_framed(result)) > MAX_FRAME_BYTES:
        return _startup_error("output_limit")
    return _emit(result)


if __name__ == "__main__":
    sys.exit(main())
