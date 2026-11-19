"""Connect the installed typed application service to the Windows job supervisor."""

import json

from financial_assistant.application_paths import WorkspacePathError
from financial_assistant.job_supervisor import JobSupervisor, JobSupervisorError, response_digest
from financial_assistant.typed_ipc import TypedIpcError, decode_response, exchange


def recover_receipt(service, request, candidate_digest):
    try:
        workspace, context_id = service.context()
        if context_id != request['context_id']:
            return None
        workspace.resolve_resource(request['arguments']['resource_id'])
        saved = workspace.read_receipt(request['run_id'])
        framed = json.dumps(saved, separators=(',', ':'), ensure_ascii=True).encode('ascii') + b'\n'
        if saved.get('status') != 'completed' or response_digest(saved) != candidate_digest:
            return None
        return decode_response(framed, request)
    except (WorkspacePathError, TypedIpcError, OSError, ValueError):
        return None


def run_supervised(service, vault_root, worker_argv, request, *, cwd):
    def execute(frame, *, cancel_event, timeout, report_progress):
        report_progress(10)
        response = exchange(worker_argv, frame, cwd=cwd, cancel_event=cancel_event, timeout=timeout, own_tree=True)
        report_progress(90)
        return response

    def recover(frame, digest):
        return recover_receipt(service, frame, digest)

    try:
        with JobSupervisor(vault_root / 'jobs', execute, service.persist, recover) as supervisor:
            job = supervisor.submit(request, timeout=10.0)
            if job['state'] != 'completed':
                job = supervisor.wait(request['run_id'], timeout=12.0)
    except JobSupervisorError as error:
        return service.failure(request, error.code)
    if job['state'] == 'completed':
        try:
            workspace, context_id = service.context()
            if context_id != request['context_id']:
                return service.failure(request, 'stale_context')
            workspace.resolve_resource(request['arguments']['resource_id'])
            if workspace.read_receipt(request['run_id']) != job['response']:
                return service.failure(request, 'receipt_mismatch')
        except WorkspacePathError as error:
            return service.failure(request, error.code)
    if job['response'] is not None:
        return job['response']
    return service.failure(request, job.get('error') or 'job_incomplete')
