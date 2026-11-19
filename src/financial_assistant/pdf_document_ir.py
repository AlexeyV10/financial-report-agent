"""Adapt digital PDF geometry to the local, unreviewed extraction artifact."""

from .pdf_table_ir import extract_pdf_tables
from .pdf_text_ir import extract_pdf_pages


def extract_pdf_document(data):
    document = extract_pdf_pages(data)
    pages = document['pages']
    if all(page['text_status'] == 'ocr_pending' for page in pages):
        return None

    paragraphs = []
    for page in pages:
        for line_number, line in enumerate(page['lines'], start=1):
            spans = line['spans']
            locator = {'page_index': page['page_index'], 'line': line_number,
                       'printed_page': page['printed_page'], 'pdf_page_label': page['pdf_page_label'],
                       'bbox': line['bbox'], 'ranges': [
                           {'char_start': span['char_start'], 'char_end': span['char_end'],
                            'pdf_box': span['pdf_box']} for span in spans]}
            paragraphs.append({'locator': locator, 'text': line['text']})

    return {'encoding': None, 'delimiter': None, 'pages': pages, 'paragraphs': paragraphs,
            'tables': extract_pdf_tables(pages), 'notes': document['notes'],
            'provenance': {**document['provenance'], 'table_rules': 'win13-pdf-tables-1'}}
