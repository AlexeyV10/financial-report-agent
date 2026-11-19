"""One application service for the fixed, source-bound Windows margin operation."""

from collections.abc import Callable
import hashlib
import json
from pathlib import Path

from .application_paths import ApplicationPaths, WorkspaceContext, WorkspacePathError
from .typed_ipc import decode_response, encode_response


SOURCE_ID = 'own-demo-v1'
SOURCE_SHA256 = 'c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451'
ASSETS = ('manifest.json', 'catalog.json', 'dictionary.json', 'admission.json')


class ApplicationService:
    def __init__(self, paths: ApplicationPaths, vault_root: Path, calculator: Callable):
        self.paths = paths
        self.vault_root = vault_root
        self.calculator = calculator

    def context(self) -> tuple[WorkspaceContext, str]:
        workspace = WorkspaceContext.open(self.paths, self.vault_root)
        identity = hashlib.sha256()
        identity.update(json.dumps([
            'win05-demo-service-1', str(workspace.vault_root).casefold(), workspace.workspace_id,
            workspace.resource_registry_sha256,
        ], ensure_ascii=True, separators=(',', ':')).encode('ascii'))
        for name in ASSETS:
            with self.paths.asset('app/assets/demo/' + name).open('rb') as stream:
                identity.update(hashlib.file_digest(stream, 'sha256').digest())
        return workspace, identity.hexdigest()

    def evaluate(self, request: dict) -> bytes:
        try:
            workspace, context_id = self.context()
            if context_id != request['context_id']:
                return encode_response(request, error='stale_context')
            result = self.calculator(self.paths, workspace, request['run_id'])
        except WorkspacePathError as error:
            return encode_response(request, error=error.code)
        except (OSError, KeyError, ValueError):
            return encode_response(request, error='own_demo_invalid')
        result = {key: value for key, value in result.items() if key not in {'schema', 'run_id'}}
        return encode_response(request, result=result)

    def persist(self, request: dict, response: dict) -> dict:
        if response['status'] != 'completed':
            return response
        try:
            workspace, context_id = self.context()
            if context_id != request['context_id']:
                return self.failure(request, 'stale_context')
            result = response['result']
            if (result['workspace_id'] != workspace.workspace_id or result['source_id'] != SOURCE_ID
                    or result['source_sha256'] != SOURCE_SHA256):
                return self.failure(request, 'source_binding_mismatch')
            workspace.resolve_resource(SOURCE_ID)
            workspace.write_receipt(request['run_id'], response)
        except WorkspacePathError as error:
            return self.failure(request, error.code)
        except OSError:
            return self.failure(request, 'filesystem_access_error')
        return response

    @staticmethod
    def failure(request: dict, code: str) -> dict:
        return decode_response(encode_response(request, error=code), request)
