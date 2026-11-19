"""One closed request and one correlated response for the local WIN-05 worker."""

import json
import os
from queue import Empty, Queue
import re
import subprocess
from threading import Event, Thread, TIMEOUT_MAX
from time import monotonic


MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 65536
MAX_STDERR_BYTES = 65536

_IDENTITY = ("run_id", "context_id", "command")
_REQUEST_FIELDS = {"schema", *_IDENTITY, "arguments"}
_RESPONSE_FIELDS = {"schema", *_IDENTITY, "status", "result", "error"}
_RESULT_FIELDS = {"workspace_id", "source_id", "source_sha256", "source_page",
                  "source_highlight", "operation", "display", "financial_status", "model_calls"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA = re.compile(r"[0-9a-f]{64}")
_DISPLAY = re.compile(r"-?(?:0|[1-9][0-9]{0,17})\.[0-9]{2}")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_INT_MAX = 2**31 - 1


class TypedIpcError(ValueError):
    """A fixed public code without data from the child process's diagnostics."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _shape(value, fields):
    return type(value) is dict and value.keys() == fields


def _matches(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _invalid_constant(_value):
    raise ValueError("nonfinite JSON number")


def _decode(data, byte_limit, invalid, too_large):
    if type(data) is not bytes:
        raise TypedIpcError(invalid)
    if len(data) > byte_limit:
        raise TypedIpcError(too_large)
    if not data.endswith(b"\n") or data.count(b"\n") != 1 or b"\r" in data:
        raise TypedIpcError(invalid)
    try:
        return json.loads(data[:-1].decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=_invalid_constant)
    except (ValueError, RecursionError):
        raise TypedIpcError(invalid) from None


def _encode(value, byte_limit, invalid, too_large):
    try:
        data = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                + "\n").encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise TypedIpcError(invalid) from None
    if len(data) > byte_limit:
        raise TypedIpcError(too_large)
    return data


def _check_request(request):
    if (not _shape(request, _REQUEST_FIELDS) or request["schema"] != "win05-request-1"
            or not _matches(request["run_id"], _ID) or not _matches(request["context_id"], _SHA)
            or request["command"] != "own_margin"
            or not _shape(request["arguments"], {"resource_id"})
            or request["arguments"]["resource_id"] != "own-demo-v1"):
        raise TypedIpcError("invalid_request")


def make_request(context_id: str, run_id: str) -> dict:
    request = {"schema": "win05-request-1", "run_id": run_id, "context_id": context_id,
               "command": "own_margin", "arguments": {"resource_id": "own-demo-v1"}}
    _check_request(request)
    return request


def encode_request(request: dict) -> bytes:
    _check_request(request)
    return _encode(request, MAX_REQUEST_BYTES, "invalid_request", "request_too_large")


def decode_request(data: bytes) -> dict:
    request = _decode(data, MAX_REQUEST_BYTES, "invalid_request", "request_too_large")
    _check_request(request)
    return request


def _valid_result(result):
    if (not _shape(result, _RESULT_FIELDS) or not _matches(result["workspace_id"], _ID)
            or result["source_id"] != "own-demo-v1" or not _matches(result["source_sha256"], _SHA)
            or type(result["source_page"]) is not int or not 1 <= result["source_page"] <= _INT_MAX
            or result["operation"] != "operating_margin_v1" or not _matches(result["display"], _DISPLAY)
            or result["financial_status"] != "answered"
            or type(result["model_calls"]) is not int or result["model_calls"] != 0):
        return False
    rect = result["source_highlight"]
    return (type(rect) is list and len(rect) == 4
            and all(type(coordinate) is int and 0 <= coordinate <= _INT_MAX for coordinate in rect)
            and rect[0] < rect[2] and rect[1] < rect[3])


def _check_response(response, request):
    if not _shape(response, _RESPONSE_FIELDS) or response["schema"] != "win05-response-1":
        raise TypedIpcError("invalid_response")
    if any(response[key] != request[key] for key in _IDENTITY):
        raise TypedIpcError("response_mismatch")
    if response["status"] == "completed":
        valid = response["error"] is None and _valid_result(response["result"])
    else:
        valid = (response["status"] == "failed" and response["result"] is None
                 and _matches(response["error"], _ERROR_CODE))
    if not valid:
        raise TypedIpcError("invalid_response")


def encode_response(request: dict, *, result=None, error=None) -> bytes:
    _check_request(request)
    response = {"schema": "win05-response-1", **{key: request[key] for key in _IDENTITY},
                "status": "completed" if error is None else "failed", "result": result, "error": error}
    _check_response(response, request)
    return _encode(response, MAX_RESPONSE_BYTES, "invalid_response", "response_too_large")


def decode_response(data: bytes, request: dict) -> dict:
    _check_request(request)
    response = _decode(data, MAX_RESPONSE_BYTES, "invalid_response", "response_too_large")
    _check_response(response, request)
    return response


def _read_limited(stream, limit, overflow):
    data = bytearray()
    while True:
        block = stream.read(min(4096, limit + 1 - len(data)))
        if not block:
            return bytes(data)
        data.extend(block)
        if len(data) > limit:
            raise TypedIpcError(overflow)


def _write_request(stream, data):
    remaining = memoryview(data)
    while remaining:
        count = stream.write(remaining)
        if not count:
            raise TypedIpcError("worker_io_error")
        remaining = remaining[count:]


def _pipe_task(messages, name, stream, action, *args):
    try:
        with stream:
            value = action(stream, *args)
    except TypedIpcError as exc:
        value = exc
    except (OSError, ValueError):
        value = TypedIpcError("worker_io_error")
    messages.put((name, value))


def _worker_options(argv, cwd, timeout):
    try:
        if type(argv) not in {list, tuple} or not argv or type(timeout) not in {int, float}:
            raise ValueError()
        argv = tuple(os.fspath(argument) for argument in argv)
        cwd = os.fspath(cwd)
        if (any(type(argument) is not str or "\0" in argument for argument in argv) or not argv[0]
                or type(cwd) is not str or not cwd or "\0" in cwd or not 0 < timeout < TIMEOUT_MAX):
            raise ValueError()
    except (TypeError, ValueError):
        raise TypedIpcError("invalid_worker_options") from None
    return argv, cwd


def _remaining(deadline, cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise TypedIpcError("worker_cancelled")
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TypedIpcError("worker_timeout")
    return remaining


def _close_tree(job):
    try:
        job.close()
    except OSError:
        raise TypedIpcError("worker_tree_cleanup_failed") from None


def exchange(argv, request: dict, *, cwd, timeout=10.0, cancel_event=None, own_tree=False) -> dict:
    """Run trusted launcher argv with bounded pipes and optional Windows tree ownership.

    A worker using tree ownership must wait for stdin before starting any work or
    spawning descendants. Requests never supply argv, cwd or ownership options.
    """
    data = encode_request(request)
    request = decode_request(data)
    argv, cwd = _worker_options(argv, cwd, timeout)
    if type(own_tree) is not bool or (cancel_event is not None and not isinstance(cancel_event, Event)):
        raise TypedIpcError("invalid_worker_options")
    deadline = monotonic() + timeout
    job = None
    worker = None
    try:
        _remaining(deadline, cancel_event)
        if own_tree:
            try:
                from .windows_job import WindowsJob

                job = WindowsJob()
            except (ImportError, OSError):
                raise TypedIpcError("worker_tree_unavailable") from None
        try:
            worker = subprocess.Popen(argv, cwd=cwd, shell=False, close_fds=True, bufsize=0,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except (OSError, ValueError):
            raise TypedIpcError("worker_start_failed") from None
        if job is not None:
            try:
                job.attach(worker)
            except OSError:
                raise TypedIpcError("worker_tree_attach_failed") from None
        _remaining(deadline, cancel_event)

        messages = Queue()
        tasks = (("stdout", worker.stdout, _read_limited, MAX_RESPONSE_BYTES, "response_too_large"),
                 ("stderr", worker.stderr, _read_limited, MAX_STDERR_BYTES, "stderr_too_large"),
                 ("stdin", worker.stdin, _write_request, data))
        outputs = {}
        for task in tasks:
            Thread(target=_pipe_task, args=(messages, *task), daemon=True).start()
        while len(outputs) < len(tasks):
            remaining = _remaining(deadline, cancel_event)
            if job is not None and worker.poll() is not None:
                # Descendants can outlive the worker while retaining its pipe handles.
                _close_tree(job)
            if cancel_event is not None or job is not None:
                remaining = min(remaining, 0.05)
            try:
                name, value = messages.get(timeout=remaining)
            except Empty:
                continue
            if isinstance(value, TypedIpcError) and value.code != "worker_io_error":
                raise value
            outputs[name] = value

        while True:
            remaining = _remaining(deadline, cancel_event)
            try:
                exit_code = worker.wait(timeout=remaining if cancel_event is None else min(remaining, 0.05))
                break
            except subprocess.TimeoutExpired:
                continue
        _remaining(deadline, cancel_event)
        if exit_code:
            raise TypedIpcError("worker_exit")
        if any(isinstance(value, TypedIpcError) for value in outputs.values()):
            raise TypedIpcError("worker_io_error")
        return decode_response(outputs["stdout"], request)
    finally:
        try:
            if job is not None:
                _close_tree(job)
        finally:
            if worker is not None:
                try:
                    if worker.poll() is None:
                        worker.kill()
                        worker.wait(timeout=1.0)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                for stream in (worker.stdin, worker.stdout, worker.stderr):
                    try:
                        stream.close()
                    except OSError:
                        pass
