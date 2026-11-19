"""Persistent single-worker queue for the typed application service."""

from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from threading import Condition, Event, Thread, Timer, TIMEOUT_MAX
from time import monotonic

from .application_paths import WorkspacePathError, _directory, _inspect, _root
from .typed_ipc import TypedIpcError, decode_request, decode_response, encode_request, encode_response


_TERMINAL = frozenset({"completed", "failed", "cancelled", "timed_out", "interrupted"})
_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"committing", "failed", "cancelled", "timed_out", "interrupted"},
    "committing": {"completed", "failed", "interrupted"},
}
_FIELDS = {"schema", "request", "state", "response", "events", "timeout", "progress",
           "prior_run_id", "candidate_sha256", "error", "order"}
_EVENT_FIELDS = {"sequence", "state", "kind", "progress", "error"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA = re.compile(r"[0-9a-f]{64}")
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_MAX_JOURNAL_BYTES = 131072


class JobSupervisorError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def response_digest(response: dict) -> str:
    """Hash compact sorted JSON, independent of whitespace in the receipt file."""
    return hashlib.sha256(_json_bytes(response)).hexdigest()


def _checked_response(request, response):
    try:
        wire = _json_bytes(response) + b"\n"
    except (ValueError, TypeError, RecursionError):
        raise TypedIpcError("invalid_response") from None
    return decode_response(wire, request)


def _matches(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None


def _key(run_id):
    if not _matches(run_id, _ID):
        raise JobSupervisorError("invalid_run_id")
    return run_id.lower()


def _filename(key):
    return hashlib.sha256(key.encode("ascii")).hexdigest() + ".json"


def _timeout(value):
    if type(value) not in {int, float} or not 0 < value < TIMEOUT_MAX:
        raise JobSupervisorError("invalid_timeout")
    return float(value)


def _event(record, kind):
    return {"sequence": len(record["events"]) + 1, "state": record["state"], "kind": kind,
            "progress": record["progress"], "error": record["error"]}


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise JobSupervisorError("journal_corrupt")
        value[key] = item
    return value


def _validate_journal(record):
    if type(record) is not dict or record.keys() != _FIELDS or record["schema"] != "win06-job-1":
        raise JobSupervisorError("journal_corrupt")
    encode_request(record["request"])
    _timeout(record["timeout"])
    state = record["state"]
    candidate = record["candidate_sha256"]
    if (type(state) is not str or state not in _TERMINAL.union(_TRANSITIONS)
            or type(record["order"]) is not int or record["order"] < 1
            or (record["prior_run_id"] is not None and not _matches(record["prior_run_id"], _ID))
            or (candidate is not None and not _matches(candidate, _SHA))
            or (state in {"committing", "completed"} and candidate is None)):
        raise JobSupervisorError("journal_corrupt")

    events = record["events"]
    if type(events) is not list or not 1 <= len(events) <= 110:
        raise JobSupervisorError("journal_corrupt")
    previous_state, previous_progress = None, 0
    for sequence, event in enumerate(events, 1):
        if (type(event) is not dict or event.keys() != _EVENT_FIELDS
                or type(event["sequence"]) is not int or event["sequence"] != sequence
                or type(event["progress"]) is not int or not previous_progress <= event["progress"] <= 100
                or type(event["state"]) is not str or type(event["kind"]) is not str
                or (event["error"] is not None and not _matches(event["error"], _CODE))):
            raise JobSupervisorError("journal_corrupt")
        if event["state"] == previous_state:
            valid_transition = previous_state == "running" and event["kind"] in {"progress", "cancel_requested"}
        else:
            allowed = {"queued"} if previous_state is None else _TRANSITIONS.get(previous_state, set())
            valid_transition = event["state"] in allowed and event["kind"] == event["state"]
        if not valid_transition:
            raise JobSupervisorError("journal_corrupt")
        previous_state, previous_progress = event["state"], event["progress"]
    if (state != previous_state or type(record["progress"]) is not int
            or record["progress"] != previous_progress or record["error"] != events[-1]["error"]):
        raise JobSupervisorError("journal_corrupt")

    response = record["response"]
    if state in {"completed", "failed"}:
        response = _checked_response(record["request"], response)
        if response["status"] != state or response["error"] != record["error"]:
            raise JobSupervisorError("journal_corrupt")
        if state == "completed" and (response_digest(response) != candidate or record["progress"] != 100):
            raise JobSupervisorError("journal_corrupt")
    elif response is not None or ((state in _TERMINAL) != _matches(record["error"], _CODE)):
        raise JobSupervisorError("journal_corrupt")


def _lock_journal(directory):
    path = directory / "owner.lock"
    info = _inspect(path)
    if info is not None and not stat.S_ISREG(info.st_mode):
        raise JobSupervisorError("invalid_journal_root")
    stream = path.open("a+b")
    try:
        if not os.path.samestat(os.fstat(stream.fileno()), _inspect(path, missing="invalid_root")):
            raise JobSupervisorError("invalid_journal_root")
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise JobSupervisorError("journal_in_use") from None
    except Exception:
        stream.close()
        raise
    return stream


@dataclass(slots=True)
class _Active:
    key: str
    deadline: float
    cancel_event: Event = field(default_factory=Event)
    cancel_requested: bool = False
    deadline_exceeded: bool = False


class JobSupervisor:
    """Hold one journal owner. Trusted execute must release its worker on cancellation."""

    def __init__(self, root: Path, execute, publish, recover=None):
        if not callable(execute) or not callable(publish) or (recover is not None and not callable(recover)):
            raise JobSupervisorError("invalid_callbacks")
        self._execute, self._publish, self._recover = execute, publish, recover
        try:
            self.root = _root(root, create_later=True)
            if self.root == self.root.parent:
                raise JobSupervisorError("invalid_journal_root")
            _directory(self.root.parent)
            self.root.mkdir(exist_ok=True)
            _directory(self.root)
            self._owner = _lock_journal(self.root)
        except (OSError, WorkspacePathError):
            raise JobSupervisorError("invalid_journal_root") from None

        self._condition = Condition()
        self._jobs = {}
        self._queue = deque()
        self._active = None
        self._closing = False
        self._fatal = None
        try:
            self._load()
            self._order = max((job["order"] for job in self._jobs.values()), default=0)
            self._thread = Thread(target=self._work, name="win06-supervisor", daemon=True)
            self._thread.start()
        except BaseException:
            self._owner.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def _load(self):
        orders = set()
        try:
            for path in self.root.glob("*.json"):
                info = _inspect(path, missing="invalid_root")
                if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_JOURNAL_BYTES:
                    raise JobSupervisorError("journal_corrupt")
                with path.open("rb") as stream:
                    raw = stream.read(_MAX_JOURNAL_BYTES + 1)
                if len(raw) > _MAX_JOURNAL_BYTES:
                    raise JobSupervisorError("journal_corrupt")
                record = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
                _validate_journal(record)
                key = _key(record["request"]["run_id"])
                if key in self._jobs or path.name != _filename(key) or record["order"] in orders:
                    raise JobSupervisorError("journal_corrupt")
                self._jobs[key] = record
                orders.add(record["order"])
        except (OSError, ValueError, TypeError, RecursionError):
            raise JobSupervisorError("journal_corrupt") from None

        for key, job in sorted(self._jobs.items(), key=lambda item: item[1]["order"]):
            if job["state"] == "queued":
                self._queue.append(key)
            elif job["state"] in {"running", "committing"}:
                recovery = self._recover_candidate(job["request"], job["candidate_sha256"]) if job["state"] == "committing" else None
                if recovery is None:
                    self._update(key, "interrupted", state="interrupted", error="supervisor_interrupted")
                else:
                    self._update(key, "completed", state="completed", response=recovery, progress=100)

    def _recover_candidate(self, request, digest):
        if self._recover is None:
            return None
        try:
            recovered = self._recover(deepcopy(request), digest)
            response = _checked_response(request, recovered)
        except Exception:
            return None
        if response["status"] != "completed" or response_digest(response) != digest:
            return None
        return response

    def _store(self, key, record):
        destination = self.root / _filename(key)
        pending = None
        try:
            _directory(self.root)
            info = _inspect(destination)
            if info is not None and not stat.S_ISREG(info.st_mode):
                raise JobSupervisorError("journal_write_failed")
            with tempfile.NamedTemporaryFile(dir=self.root, prefix="job-", suffix=".pending", delete=False) as stream:
                pending = Path(stream.name)
                stream.write(_json_bytes(record) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            _directory(self.root)
            pending.replace(destination)
            pending = None
        except (OSError, WorkspacePathError):
            raise JobSupervisorError("journal_write_failed") from None
        finally:
            if pending is not None:
                try:
                    _directory(self.root)
                    pending.unlink(missing_ok=True)
                except (OSError, WorkspacePathError):
                    pass
        self._jobs[key] = record

    def _update(self, key, kind, **fields):
        record = deepcopy(self._jobs[key])
        record.update(fields)
        record["events"].append(_event(record, kind))
        self._store(key, record)

    def _check_open(self):
        if self._fatal is not None:
            raise JobSupervisorError(self._fatal)
        if self._closing:
            raise JobSupervisorError("supervisor_closed")

    def _lookup(self, key):
        job = self._jobs.get(key)
        if job is None:
            raise JobSupervisorError("unknown_job")
        return job

    def _submit(self, request, timeout, prior_run_id=None):
        self._check_open()
        request = decode_request(encode_request(request))
        timeout = _timeout(timeout)
        key = _key(request["run_id"])
        if key in self._jobs:
            existing = self._jobs[key]
            if (existing["request"] != request or existing["timeout"] != timeout
                    or (prior_run_id is not None and prior_run_id != existing["prior_run_id"])):
                raise JobSupervisorError("idempotency_conflict")
            return deepcopy(existing)

        record = {"schema": "win06-job-1", "request": request, "state": "queued", "response": None,
                  "events": [], "timeout": timeout, "progress": 0, "prior_run_id": prior_run_id,
                  "candidate_sha256": None, "error": None, "order": self._order + 1}
        record["events"].append(_event(record, "queued"))
        self._store(key, record)
        self._order += 1
        self._queue.append(key)
        self._condition.notify_all()
        return deepcopy(record)

    def submit(self, request: dict, *, timeout=10.0) -> dict:
        with self._condition:
            return self._submit(request, timeout)

    def get(self, run_id: str) -> dict:
        with self._condition:
            return deepcopy(self._lookup(_key(run_id)))

    def wait(self, run_id: str, *, timeout) -> dict:
        key = _key(run_id)
        deadline = monotonic() + _timeout(timeout)
        with self._condition:
            while self._lookup(key)["state"] not in _TERMINAL:
                if self._fatal is not None:
                    raise JobSupervisorError(self._fatal)
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise JobSupervisorError("wait_timeout")
                self._condition.wait(remaining)
            return deepcopy(self._jobs[key])

    def cancel(self, run_id: str) -> dict:
        key = _key(run_id)
        with self._condition:
            self._check_open()
            job = self._lookup(key)
            if job["state"] == "queued":
                self._update(key, "cancelled", state="cancelled", error="cancelled")
            elif job["state"] == "running" and not self._active.cancel_event.is_set():
                self._update(key, "cancel_requested")
                self._active.cancel_requested = True
                self._active.cancel_event.set()
            self._condition.notify_all()
            return deepcopy(self._jobs[key])

    def retry(self, prior_run_id: str, request: dict, *, timeout=10.0) -> dict:
        request = decode_request(encode_request(request))
        with self._condition:
            prior = self._lookup(_key(prior_run_id))
            if (prior["state"] not in _TERMINAL - {"completed"}
                    or _key(request["run_id"]) == _key(prior_run_id)
                    or {**prior["request"], "run_id": request["run_id"]} != request):
                raise JobSupervisorError("invalid_retry")
            return self._submit(request, timeout, prior["request"]["run_id"])

    def close(self):
        with self._condition:
            self._closing = True
            if self._active is not None:
                self._active.cancel_event.set()
            self._condition.notify_all()
        self._thread.join(5.0)
        if self._thread.is_alive():
            raise JobSupervisorError("close_timeout")
        self._owner.close()

    def _expire(self, attempt):
        with self._condition:
            if self._active is attempt and self._jobs[attempt.key]["state"] == "running":
                attempt.deadline_exceeded = True
                attempt.cancel_event.set()

    def _progress(self, attempt, progress):
        if type(progress) is not int or not 0 <= progress <= 100:
            raise JobSupervisorError("invalid_progress")
        with self._condition:
            if (self._active is attempt and not attempt.cancel_event.is_set()
                    and self._jobs[attempt.key]["state"] == "running"
                    and monotonic() < attempt.deadline
                    and progress > self._jobs[attempt.key]["progress"]):
                self._update(attempt.key, "progress", progress=progress)
                self._condition.notify_all()

    def _run(self, attempt, request, timeout):
        timer = Timer(max(0, attempt.deadline - monotonic()), self._expire, (attempt,))
        timer.daemon = True
        timer.start()
        try:
            result = self._execute(deepcopy(request), cancel_event=attempt.cancel_event, timeout=timeout,
                                   report_progress=lambda value: self._progress(attempt, value))
            response = _checked_response(request, result)
        except (TypedIpcError, JobSupervisorError) as error:
            code = error.code if _matches(error.code, _CODE) else "worker_failed"
            response = decode_response(encode_response(request, error=code), request)
        except Exception:
            response = decode_response(encode_response(request, error="worker_failed"), request)
        finally:
            timer.cancel()
        return response

    def _before_publish(self, attempt, response):
        key = attempt.key
        if attempt.cancel_requested:
            self._update(key, "cancelled", state="cancelled", error="cancelled")
        elif self._closing:
            self._update(key, "interrupted", state="interrupted", error="supervisor_closed")
        elif attempt.deadline_exceeded or monotonic() >= attempt.deadline or response["error"] == "worker_timeout":
            self._update(key, "timed_out", state="timed_out", error="worker_timeout")
        elif response["status"] == "failed":
            self._update(key, "failed", state="failed", response=response, error=response["error"])
        else:
            digest = response_digest(response)
            self._update(key, "committing", state="committing", candidate_sha256=digest)
            return digest
        return None

    def _commit(self, key, request, response, candidate):
        try:
            final = _checked_response(request, self._publish(deepcopy(request), deepcopy(response)))
            if final["status"] == "completed" and response_digest(final) != candidate:
                raise TypedIpcError("response_mismatch")
        except Exception as error:
            # The callback may have created a valid receipt before raising.
            final = self._recover_candidate(request, candidate)
            code = error.code if isinstance(error, TypedIpcError) and _matches(error.code, _CODE) else "publish_failed"
        with self._condition:
            if final is None:
                self._update(key, "interrupted", state="interrupted", error=code)
            elif final["status"] == "completed":
                self._update(key, "completed", state="completed", response=final, progress=100)
            else:
                self._update(key, "failed", state="failed", response=final, error=final["error"])

    def _work(self):
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closing or self._queue)
                    if self._closing:
                        return
                    key = self._queue.popleft()
                    job = self._jobs[key]
                    if job["state"] != "queued":
                        continue
                    self._update(key, "running", state="running")
                    attempt = _Active(key, monotonic() + job["timeout"])
                    self._active = attempt
                    self._condition.notify_all()
                response = self._run(attempt, job["request"], job["timeout"])
                with self._condition:
                    candidate = self._before_publish(attempt, response)
                    self._condition.notify_all()
                if candidate is not None:
                    self._commit(key, job["request"], response, candidate)
                with self._condition:
                    self._active = None
                    self._condition.notify_all()
        except JobSupervisorError as error:
            with self._condition:
                self._fatal = error.code
                if self._active is not None:
                    self._active.cancel_event.set()
                self._condition.notify_all()
