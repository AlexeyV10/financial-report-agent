"""Render a previously cited source from the installed private runtime."""

import argparse
import json
from pathlib import Path
import sys


_SCHEMA = "win09-viewer-1"


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        raise ValueError("invalid_view_options")


def _start():
    parser = _ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--app-data", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resource-id", required=True)
    parser.add_argument("--page-index", type=int, required=True)
    parser.add_argument("--zoom-percent", type=int, required=True)
    parser.add_argument("--rotation", type=int, required=True)
    parser.add_argument("--dpi-percent", type=int, required=True)
    parser.add_argument("--crop-to-source", action="store_true")
    return parser.parse_args()


def _frame(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")


def _error(code):
    sys.stdout.buffer.write(_frame({"schema": _SCHEMA, "status": "error", "error": code}))
    sys.stdout.buffer.flush()
    return 3


def main():
    try:
        args = _start()
    except ValueError:
        return _error("invalid_view_options")
    try:
        if (not args.install_root.is_absolute() or args.install_root.drive.startswith("\\\\")
                or not sys.flags.isolated or not sys.flags.no_user_site):
            return _error("invalid_launch")
        root = args.install_root.resolve(strict=True)
        if (Path(__file__).resolve() != root / "app/spikes/windows_09/viewer_cli.py"
                or Path(sys.prefix).resolve() != root / "runtime"):
            return _error("invalid_launch")
    except (OSError, ValueError):
        return _error("invalid_launch")

    sys.path.append(str(root / "app/src"))
    from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext, WorkspacePathError
    from financial_assistant.document_viewer import MAX_FRAME_BYTES, DocumentViewerError, render_workspace_source

    try:
        paths = ApplicationPaths(args.install_root, args.app_data)
        workspace = WorkspaceContext.open(paths, args.vault)
        render = render_workspace_source
        if args.resource_id == "d0-own-v1":
            from financial_assistant.d0_viewer import render_d0_source
            render = render_d0_source
        response = render(workspace, args.run_id, args.resource_id, args.page_index,
                          args.zoom_percent, args.rotation, args.dpi_percent, args.crop_to_source)
        frame = _frame(response)
    except (DocumentViewerError, WorkspacePathError) as error:
        return _error(error.code)
    except (OSError, TypeError, ValueError, RecursionError):
        return _error("render_failed")
    if len(frame) > MAX_FRAME_BYTES:
        return _error("render_limit")
    sys.stdout.buffer.write(frame)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
