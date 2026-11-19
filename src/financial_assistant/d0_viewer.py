"""Open the stored teaching report from a successful, source-bound D0 result."""

import hashlib
import json
import re

from .application_paths import WorkspacePathError
from .contracts_v2 import ContractError, digest
from .document_viewer import DocumentViewerError, PdfiumRenderer, VIEWER_SCHEMA
from .service_contracts import validate_answer
from .vault_storage import VaultStorageError, VaultStore


D0_SOURCE_ID = 'd0-own-v1'
D0_SOURCE_SHA256 = 'ebabc9e49fbde3063f63f98393a271734bc16d0686ea035938ccd8d90db2caf0'
D0_VERSION = 'd0-own-v1-report'
_LOCATOR_SCHEMA = 'win10-d0-source-1'
_RECEIPT_KEYS = {'schema', 'workspace_id', 'context_id', 'run_id', 'operation', 'source_id',
                 'source_sha256', 'source_page', 'version_id', 'cells', 'b_answer_sha256'}
_REVENUE = 'd0-revenue-2025'
_PRIOR = 'd0-revenue-2024'
_PROFIT = 'd0-operating-profit-2025'
_OPERATION_FACTS = {
    'direct_fact_v1': {_REVENUE, _PRIOR, _PROFIT},
    'absolute_change_v1': {_REVENUE, _PRIOR},
    'relative_change_v1': {_REVENUE, _PRIOR},
    'scale_v1': {_REVENUE, _PRIOR, _PROFIT},
    'operating_margin_v1': {_PROFIT, _REVENUE},
}
_CELL_RECTS = {
    _PRIOR: [331, 143, 388, 165], _REVENUE: [246, 143, 303, 165], _PROFIT: [246, 116, 303, 138],
}
_TABLE_TEXT = ('МСФО · группа · млн RUB\nПоказатель\t2025\t2024\n'
              'Выручка\t120\t100\nОперационная прибыль\t18\t—')


def source_context_id(workspace, manifest_sha256):
    return digest(['win10-d0-source-context-1', str(workspace.vault_root).casefold(), workspace.workspace_id,
                   workspace.resource_registry_sha256, manifest_sha256])


def _manifest_context(workspace):
    try:
        path = workspace.paths.asset('app/assets/d0/manifest.json')
        with path.open('rb') as stream:
            data = stream.read(16385)
        if len(data) > 16384:
            raise ValueError()
        manifest = json.loads(data)
        if (manifest['schema'] != 'win10-own-fixture-1' or manifest['resource_id'] != D0_SOURCE_ID
                or manifest['sha256'] != D0_SOURCE_SHA256 or manifest['page'] != 1
                or manifest['cells'] != _CELL_RECTS):
            raise ValueError()
    except (OSError, TypeError, ValueError, KeyError):
        raise DocumentViewerError('source_binding_mismatch') from None
    return source_context_id(workspace, hashlib.sha256(data).hexdigest())


def _archive(workspace):
    try:
        with VaultStore(workspace) as store:
            stored = store.list_versions(D0_SOURCE_ID)
            if sum(item['sha256'] == D0_SOURCE_SHA256 for item in stored) != 1:
                raise DocumentViewerError('original_missing')
            return store.read_original(D0_SOURCE_SHA256)
    except VaultStorageError as error:
        raise DocumentViewerError(error.code) from None


def _require_cells(operation, fact_ids):
    allowed = _OPERATION_FACTS.get(operation)
    actual = set(fact_ids)
    multi = operation in {'absolute_change_v1', 'relative_change_v1', 'operating_margin_v1'}
    if allowed is None or len(actual) != len(fact_ids) or (
            multi and actual != allowed) or (not multi and (len(actual) != 1 or not actual <= allowed)):
        raise DocumentViewerError('source_binding_mismatch')


def record_d0_source(workspace, answer, expected_operation):
    """Commit a viewer receipt after source validation, before exposing a number to UI."""
    try:
        validate_answer(answer)
    except (ContractError, TypeError, KeyError, ValueError):
        raise DocumentViewerError('receipt_invalid') from None
    if answer['method'] != 'B' or answer['financial_status'] != 'answered' or answer['model_calls'] != 0:
        raise DocumentViewerError('receipt_invalid')
    result = answer['financial_result']
    if result['operation_id'] != expected_operation:
        raise DocumentViewerError('source_binding_mismatch')
    input_facts = result['inputs']
    fact_ids = [item['fact_id'] for item in input_facts]
    _require_cells(expected_operation, fact_ids)
    if any(item['document_id'] != D0_SOURCE_ID or item['version_id'] != D0_VERSION
           or item['document_sha256'] != D0_SOURCE_SHA256 for item in input_facts):
        raise DocumentViewerError('source_binding_mismatch')
    context_id = _manifest_context(workspace)
    _archive(workspace)
    receipt = {'schema': _LOCATOR_SCHEMA, 'workspace_id': workspace.workspace_id, 'context_id': context_id,
               'run_id': answer['run_id'], 'operation': expected_operation, 'source_id': D0_SOURCE_ID,
               'source_sha256': D0_SOURCE_SHA256, 'source_page': 1, 'version_id': D0_VERSION,
               'cells': [{'fact_id': fact_id, 'rect_pdf': _CELL_RECTS[fact_id]} for fact_id in fact_ids],
               'b_answer_sha256': digest(answer)}
    workspace.write_receipt(answer['run_id'], receipt)
    return receipt


def _exact_rect(workspace, run_id):
    try:
        receipt = workspace.read_receipt(run_id)
        if (receipt.keys() != _RECEIPT_KEYS or receipt['schema'] != _LOCATOR_SCHEMA
                or receipt['workspace_id'] != workspace.workspace_id
                or receipt['context_id'] != _manifest_context(workspace)
                or receipt['run_id'] != run_id or receipt['source_id'] != D0_SOURCE_ID
                or receipt['source_sha256'] != D0_SOURCE_SHA256 or receipt['version_id'] != D0_VERSION
                or receipt['source_page'] != 1 or not re.fullmatch('[0-9a-f]{64}', receipt['b_answer_sha256'])):
            raise ValueError()
        cells = receipt['cells']
        _require_cells(receipt['operation'], [cell['fact_id'] for cell in cells])
        for cell in cells:
            if cell.keys() != {'fact_id', 'rect_pdf'} or cell['rect_pdf'] != _CELL_RECTS[cell['fact_id']]:
                raise ValueError()
        rectangles = [cell['rect_pdf'] for cell in cells]
    except (DocumentViewerError, WorkspacePathError):
        raise
    except (TypeError, KeyError, ValueError):
        raise DocumentViewerError('receipt_invalid') from None
    left, bottom, right, top = zip(*rectangles, strict=True)
    return min(left), min(bottom), max(right), max(top)


def render_d0_source(workspace, run_id, resource_id, page_index, zoom_percent, rotation, dpi_percent,
                     crop_to_source=False):
    if resource_id != D0_SOURCE_ID:
        raise DocumentViewerError('resource_not_authorized')
    if type(page_index) is not int or page_index != 0:
        raise DocumentViewerError('page_out_of_range')
    rect = _exact_rect(workspace, run_id)
    frame = PdfiumRenderer().render(_archive(workspace), page_index, zoom_percent, rotation, dpi_percent,
                                    source_rect=rect, crop_to_source=crop_to_source)
    printed = '1' if 'Page 1 / Own D0 teaching example.' in frame['page_text'] else None
    return {'schema': VIEWER_SCHEMA, 'status': 'ok', 'resource_id': D0_SOURCE_ID,
            'source_sha256': D0_SOURCE_SHA256, 'page_index': page_index, 'printed_page': printed,
            'zoom_percent': zoom_percent, 'rotation': rotation, 'dpi_percent': dpi_percent,
            'crop_to_source': crop_to_source, 'table_text': _TABLE_TEXT, **frame}
