"""Verified extraction from originals that were accepted in the selected vault."""

import json

from .application_paths import WorkspacePathError
from .docx_extract import extract_docx
from .office_extraction_common import ExtractionError
from .pdf_document_ir import extract_pdf_document
from .safe_import import ImportValidationError, classify_bytes
from .spreadsheet_extract import extract_xlsx
from .text_extract import extract_text
from .vault_storage import VaultStore


_DATA_SCHEMA = 'win12-structured-extraction-1'
_PDF_SCHEMA = 'win13-digital-pdf-ir-1'
_ARTIFACT_LIMIT = 1024 * 1024
_SUPPORTED = {'csv', 'xlsx', 'docx', 'txt', 'pdf'}
_PREVIEW_LIMIT = 16


def _archive(workspace, sha256):
    with VaultStore(workspace) as store:
        capture = store.get_capture(sha256)
        if capture['file_type'] not in _SUPPORTED:
            return capture, None
        data = store.read_original(sha256)
    if len(data) != capture['byte_count']:
        raise ExtractionError('capture_bytes_mismatch')
    try:
        found = classify_bytes(data)
    except ImportValidationError as error:
        raise ExtractionError(error.code) from None
    # A sparse CSV captured as plain text before WIN-12 stays a text asset.
    if found != capture['file_type'] and (found, capture['file_type']) != ('csv', 'txt'):
        raise ExtractionError('capture_type_mismatch')
    return capture, data


def _derive(data, file_type):
    if file_type == 'pdf':
        return extract_pdf_document(data)
    if file_type == 'xlsx':
        return extract_xlsx(data)
    if file_type == 'docx':
        return extract_docx(data)
    return extract_text(data, file_type)


def _artifact_key(sha256, file_type):
    prefix = 'win13-pdf-ir-v1-' if file_type == 'pdf' else 'win12-extract-v1-'
    return prefix + sha256


def _publish(workspace, artifact):
    run = _artifact_key(artifact['asset_sha256'], artifact['file_type'])
    try:
        workspace.write_receipt(run, artifact)
        return 'extracted'
    except WorkspacePathError as error:
        if error.code != 'duplicate_run':
            raise
    if workspace.read_receipt(run, max_bytes=_ARTIFACT_LIMIT) != artifact:
        raise ExtractionError('extraction_receipt_mismatch')
    return 'reused'


def extract_capture(workspace, sha256):
    capture, data = _archive(workspace, sha256)
    file_type = capture['file_type']
    structured = _derive(data, file_type) if data is not None else None
    if structured is None:
        return 'unsupported', capture, None
    schema = _PDF_SCHEMA if file_type == 'pdf' else _DATA_SCHEMA
    artifact = {'schema': schema, 'asset_sha256': sha256, 'workspace_id': workspace.workspace_id,
                'file_type': capture['file_type'], 'semantic_state': 'not_reviewed', 'data': structured}
    wire = (json.dumps(artifact, ensure_ascii=False, allow_nan=False, sort_keys=True) + '\n').encode('utf-8')
    if len(wire) > _ARTIFACT_LIMIT:
        raise ExtractionError('extraction_limit')
    return _publish(workspace, artifact), capture, structured


def _one_line(label, value):
    text = label + ('' if value is None else ' '.join(value.splitlines()))
    visible = ''.join(ch if ch.isprintable() else ' ' for ch in text)
    # Keep the UTF-16 WPF frame quota independent of non-BMP text in a document.
    units = visible.encode('utf-16-le')[:512]
    return units.decode('utf-16-le', errors='ignore')


def _table_label(file_type, cell):
    locator = cell['locator']
    if file_type == 'pdf':
        return (f"PDF · страница {locator['page_index'] + 1} · строка {locator['row']} · "
                f"столбец {locator['column']}: ")
    if file_type == 'xlsx':
        return f"Лист {locator['sheet']} · {locator['address']}: "
    if file_type == 'docx':
        return (f"DOCX · таблица {locator['table']} · строка {locator['row']} · "
                f"столбец {locator['column']}: ")
    return f"CSV · строка {locator['row']} · столбец {locator['column']}: "


def preview_rows(data, file_type):
    result = []
    for table in data['tables']:
        for row in table['rows']:
            for cell in row['cells']:
                rendered = cell['text']
                if cell['kind'] == 'formula':
                    status = cell['cache_status']
                    if status == 'missing':
                        rendered = 'сохранённого значения нет'
                    elif status == 'stale':
                        rendered = f'{rendered} (кэш требует пересчёта)'
                    else:
                        rendered = f'{rendered} (свежесть кэша не подтверждена)'
                result.append(_one_line(_table_label(file_type, cell), rendered))
                if len(result) == _PREVIEW_LIMIT:
                    return result
    for paragraph in data['paragraphs'][:_PREVIEW_LIMIT - len(result)]:
        locator = paragraph['locator']
        if file_type == 'pdf':
            title = f"PDF · страница {locator['page_index'] + 1} · строка {locator['line']}: "
        elif file_type == 'docx':
            title = f"DOCX · абзац {locator['paragraph']}: "
        else:
            title = f"TXT · строка {locator['line']}: "
        result.append(_one_line(title, paragraph['text']))
    return result
