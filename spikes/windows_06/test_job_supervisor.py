"""Deterministic tests of the native job supervisor and durable recovery."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, Lock
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant import job_supervisor as jobs
from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.typed_ipc import TypedIpcError, decode_response, encode_response, make_request


FIRST_CONTEXT = 'a' * 64
OTHER_CONTEXT = 'b' * 64


def response(request, workspace_id='vault-a'):
    result = dict(workspace_id=workspace_id, source_id='own-demo-v1', source_sha256='c' * 64,
                  source_page=1, source_highlight=[2, 3, 20, 31], operation='operating_margin_v1',
                  display='15.00', financial_status='answered', model_calls=0)
    return decode_response(encode_response(request, result=result), request)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        scratch = (ROOT / 'tmp').resolve()
        scratch.mkdir(exist_ok=True)
        temporary = TemporaryDirectory(prefix='win06-jobs-', dir=scratch)
        self.base = Path(temporary.name).resolve()
        self.assertTrue(self.base.is_relative_to(scratch))
        self.addCleanup(temporary.cleanup)
        install = self.base / 'Подготовленная установка'
        install.mkdir()
        self.paths = ApplicationPaths(install, self.base / 'Данные приложения')
        self.workspace = self.make_workspace('vault-a', 'Хранилище А')

    def make_workspace(self, workspace_id, name):
        vault = self.base / name
        vault.mkdir()
        marker = dict(schema='workspace-context-1', workspace_id=workspace_id, resources=[])
        (vault / 'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
        return WorkspaceContext.open(self.paths, vault)

    @staticmethod
    def request(run_id, context_id=FIRST_CONTEXT):
        return make_request(context_id, run_id)

    def assert_code(self, code, call, *args, **kwargs):
        with self.assertRaises(jobs.JobSupervisorError) as raised:
            call(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)

    @property
    def journal(self):
        return self.workspace.vault_root / 'jobs'

    @staticmethod
    def publish():
        return Mock(side_effect=lambda request, candidate: candidate)

    def test_fifo_runs_only_one_worker_and_reports_progress(self):
        started = Event()
        release = Event()
        guard = Lock()
        order = []
        active = 0
        peak_active = 0

        def execute(request, *, cancel_event, timeout, report_progress):
            nonlocal active, peak_active
            with guard:
                active += 1
                peak_active = max(peak_active, active)
                order.append(request['run_id'])
            try:
                if request['run_id'] == 'first':
                    started.set()
                    if not release.wait(4):
                        raise RuntimeError('test gate was not released')
                report_progress(40)
                return response(request)
            finally:
                with guard:
                    active -= 1

        publish = self.publish()
        with jobs.JobSupervisor(self.journal, execute, publish) as supervisor:
            try:
                supervisor.submit(self.request('first'))
                self.assertTrue(started.wait(3))
                self.assertEqual(supervisor.submit(self.request('second'))['state'], 'queued')
                self.assertEqual(supervisor.submit(self.request('third'))['state'], 'queued')
                self.assertEqual(order, ['first'])
            finally:
                release.set()
            for name in ('first', 'second', 'third'):
                record = supervisor.wait(name, timeout=3)
                self.assertEqual(record['state'], 'completed')
                self.assertEqual(record['progress'], 100)
                self.assertTrue(any(event['kind'] == 'progress' and event['progress'] == 40
                                    for event in record['events']))
        self.assertEqual(order, ['first', 'second', 'third'])
        self.assertEqual([call.args[0]['run_id'] for call in publish.call_args_list], order)
        self.assertEqual(peak_active, 1)

    def test_same_submission_is_idempotent_but_same_id_with_other_context_is_denied(self):
        started = Event()
        release = Event()

        def execute(request, **_options):
            started.set()
            if not release.wait(4):
                raise RuntimeError('test gate was not released')
            return response(request)

        request = self.request('same-run')
        publish = self.publish()
        with jobs.JobSupervisor(self.journal, execute, publish) as supervisor:
            try:
                supervisor.submit(request)
                self.assertTrue(started.wait(3))
                initial = supervisor.get('same-run')
                self.assertEqual(initial['state'], 'running')
                self.assertEqual(supervisor.submit(deepcopy(request)), initial)
                self.assert_code('idempotency_conflict', supervisor.submit,
                                 self.request('same-run', OTHER_CONTEXT))
                self.assert_code('idempotency_conflict', supervisor.submit, self.request('SAME-RUN'))
                self.assert_code('wait_timeout', supervisor.wait, 'same-run', timeout=0.03)
                self.assertEqual(supervisor.get('same-run'), initial)
            finally:
                release.set()
            record = supervisor.wait('same-run', timeout=3)
            self.assertEqual(supervisor.submit(deepcopy(request)), record)
        publish.assert_called_once()

    def test_cancellation_of_queued_job_never_starts_worker(self):
        started = Event()
        release = Event()
        seen = []

        def execute(request, **_options):
            seen.append(request['run_id'])
            started.set()
            if not release.wait(4):
                raise RuntimeError('test gate was not released')
            return response(request)

        publish = self.publish()
        with jobs.JobSupervisor(self.journal, execute, publish) as supervisor:
            try:
                supervisor.submit(self.request('running'))
                self.assertTrue(started.wait(3))
                supervisor.submit(self.request('queued'))
                supervisor.cancel('queued')
                cancelled = supervisor.wait('queued', timeout=3)
                self.assertEqual(cancelled['state'], 'cancelled')
                self.assertIsNone(cancelled['response'])
            finally:
                release.set()
            self.assertEqual(supervisor.wait('running', timeout=3)['state'], 'completed')
        self.assertEqual(seen, ['running'])
        self.assertEqual([call.args[0]['run_id'] for call in publish.call_args_list], ['running'])

    def test_running_cancellation_ignores_late_progress_and_typed_success(self):
        started = Event()
        release = Event()
        callback_activity = []

        def execute(request, *, cancel_event, timeout, report_progress):
            report_progress(20)
            started.set()
            if not release.wait(4):
                raise RuntimeError('test gate was not released')
            report_progress(95)
            callback_activity.append(cancel_event.is_set())
            return response(request)

        publish = self.publish()
        with jobs.JobSupervisor(self.journal, execute, publish) as supervisor:
            try:
                supervisor.submit(self.request('active'))
                self.assertTrue(started.wait(3))
                supervisor.cancel('active')
            finally:
                release.set()
            final = supervisor.wait('active', timeout=3)
            self.assertEqual(final['state'], 'cancelled')
            self.assertIsNone(final['response'])
            self.assertEqual(final['progress'], 20)
            self.assertNotIn('completed', [event['state'] for event in final['events']])
            self.assertIn('cancel_requested', [event['kind'] for event in final['events']])
        self.assertEqual(callback_activity, [True])
        publish.assert_not_called()

    def test_transport_timeout_has_no_response_and_does_not_publish(self):
        observed_limits = []
        late_worker = []

        def execute(request, *, cancel_event, timeout, report_progress):
            observed_limits.append(timeout)
            if request['run_id'] == 'expires':
                raise TypedIpcError('worker_timeout')
            late_worker.append(cancel_event.wait(2))
            report_progress(80)
            return response(request)

        publish = self.publish()
        with jobs.JobSupervisor(self.journal, execute, publish) as supervisor:
            self.assert_code('invalid_timeout', supervisor.submit, self.request('bad'), timeout=0)
            supervisor.submit(self.request('expires'), timeout=0.75)
            terminal = supervisor.wait('expires', timeout=3)
            self.assertEqual(terminal['state'], 'timed_out')
            self.assertIsNone(terminal['response'])
            supervisor.submit(self.request('returns-late'), timeout=0.25)
            late_result = supervisor.wait('returns-late', timeout=3)
            self.assertEqual(late_result['state'], 'timed_out')
            self.assertIsNone(late_result['response'])
            self.assertEqual(late_result['progress'], 0)
        self.assertEqual(len(observed_limits), 2)
        self.assertGreater(observed_limits[0], 0)
        self.assertLessEqual(observed_limits[0], 0.75)
        self.assertEqual(late_worker, [True])
        publish.assert_not_called()

    def test_failed_job_requires_explicit_retry_with_new_id(self):
        def execute(request, **_options):
            if request['run_id'] == 'failed':
                return decode_response(encode_response(request, error='worker_exit'), request)
            return response(request)

        publish = self.publish()
        with jobs.JobSupervisor(self.journal, execute, publish) as supervisor:
            supervisor.submit(self.request('failed'))
            failure = supervisor.wait('failed', timeout=3)
            self.assertEqual(failure['state'], 'failed')
            self.assertEqual(failure['response']['error'], 'worker_exit')
            self.assertIsNone(failure['response']['result'])
            self.assertEqual(supervisor.submit(self.request('failed')), failure)
            self.assert_code('invalid_retry', supervisor.retry, 'failed', self.request('failed'))
            retry = supervisor.retry('failed', self.request('explicit-retry'))
            self.assertEqual(retry['prior_run_id'], 'failed')
            completed = supervisor.wait('explicit-retry', timeout=3)
            self.assertEqual(completed['state'], 'completed')
            self.assertEqual(completed['response']['run_id'], 'explicit-retry')
            self.assertEqual(supervisor.get('failed'), failure)
        self.assertEqual([call.args[0]['run_id'] for call in publish.call_args_list], ['explicit-retry'])

    @staticmethod
    def seed_record(journal, request, states, candidate=None):
        journal.mkdir()
        events = [dict(sequence=index, state=state, kind=state, progress=0, error=None)
                  for index, state in enumerate(states, start=1)]
        record = dict(schema='win06-job-1', request=request, state=states[-1], response=None,
                      events=events, timeout=10.0, progress=0, prior_run_id=None,
                      candidate_sha256=candidate, error=None, order=1)
        document = hashlib.sha256(request['run_id'].lower().encode('ascii')).hexdigest() + '.json'
        path = journal / document
        path.write_text(json.dumps(record), encoding='utf-8')
        return path

    def test_reopen_running_job_does_not_consult_receipt_or_invent_completion(self):
        request = self.request('unfinished')
        self.seed_record(self.journal, request, ('queued', 'running'))
        execute, publish = Mock(), Mock()
        recover = Mock(return_value=response(request))
        with jobs.JobSupervisor(self.journal, execute, publish, recover=recover) as reopened:
            record = reopened.get('unfinished')
            self.assertEqual(record['state'], 'interrupted')
            self.assertEqual(record['error'], 'supervisor_interrupted')
            self.assertIsNone(record['response'])
        with jobs.JobSupervisor(self.journal, execute, publish, recover=recover) as reopened:
            self.assertEqual(reopened.get('unfinished'), record)
        execute.assert_not_called()
        publish.assert_not_called()
        recover.assert_not_called()

    def test_reopen_pending_commit_requires_exact_bound_receipt(self):
        request = self.request('committing')
        exact = response(request)
        candidate = jobs.response_digest(exact)
        changed = deepcopy(exact)
        changed['result']['display'] = '14.00'
        for label, receipt in (('absent', None), ('changed', changed), ('exact', exact)):
            with self.subTest(label=label):
                journal = self.workspace.vault_root / ('jobs-' + label)
                self.seed_record(journal, request, ('queued', 'running', 'committing'), candidate)
                execute, publish = Mock(), Mock()
                recover = Mock(return_value=receipt)
                with jobs.JobSupervisor(journal, execute, publish, recover=recover) as reopened:
                    record = reopened.get('committing')
                    self.assertEqual(record['state'], 'completed' if label == 'exact' else 'interrupted')
                    self.assertEqual(record['response'], exact if label == 'exact' else None)
                with jobs.JobSupervisor(journal, execute, publish, recover=recover) as reopened:
                    self.assertEqual(reopened.get('committing'), record)
                execute.assert_not_called()
                publish.assert_not_called()
                recover.assert_called_once_with(request, candidate)

    def test_invalid_journal_preserves_data_and_releases_exclusive_lock(self):
        path = self.seed_record(self.journal, self.request('unfinished'), ('queued', 'running'))
        coherent = path.read_bytes()
        truncated = coherent[:-1]
        path.write_bytes(truncated)
        execute, publish, recover = Mock(), Mock(), Mock()
        self.assert_code('journal_corrupt', jobs.JobSupervisor, self.journal, execute, publish,
                         recover=recover)
        self.assertEqual(path.read_bytes(), truncated)
        path.write_bytes(coherent)
        with jobs.JobSupervisor(self.journal, execute, publish, recover=recover) as reopened:
            self.assertEqual(reopened.get('unfinished')['state'], 'interrupted')
        execute.assert_not_called()
        publish.assert_not_called()
        recover.assert_not_called()

    def test_vaults_are_independent_and_lock_excludes_second_owner(self):
        other_workspace = self.make_workspace('vault-b', 'Хранилище Б')
        other_journal = other_workspace.vault_root / 'jobs'
        request = self.request('same-run')
        publish_a, publish_b = self.publish(), self.publish()

        def execute_a(request, **_options):
            return response(request, 'vault-a')

        def execute_b(request, **_options):
            return response(request, 'vault-b')

        with jobs.JobSupervisor(self.journal, execute_a, publish_a) as first:
            self.assert_code('journal_in_use', jobs.JobSupervisor, self.journal, execute_a, publish_a)
            first.submit(request)
            first_record = first.wait('same-run', timeout=3)
            with jobs.JobSupervisor(other_journal, execute_b, publish_b) as second:
                self.assert_code('unknown_job', second.get, 'same-run')
                second.submit(request)
                second_record = second.wait('same-run', timeout=3)
            self.assertEqual(first.get('same-run'), first_record)
            self.assertEqual(first_record['response']['result']['workspace_id'], 'vault-a')
            self.assertEqual(second_record['response']['result']['workspace_id'], 'vault-b')
        with jobs.JobSupervisor(self.journal, execute_a, publish_a) as reopened:
            self.assertEqual(reopened.get('same-run'), first_record)
        publish_a.assert_called_once()
        publish_b.assert_called_once()


if __name__ == '__main__':
    unittest.main()
