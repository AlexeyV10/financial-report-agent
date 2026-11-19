"""Exercise four own captured files through the real Windows extraction entry points."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from io import BytesIO, StringIO
import json
from pathlib import Path
import runpy
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant.application_paths import ApplicationPaths, WorkspaceContext
from financial_assistant.vault_storage import VaultStore


CSV = ('Статья;2025;2024\nВыручка;1\u202f234,50;1000\nРасходы;(300,00);\n'
       'Пустая колонка;77\nУчебный маркер;=2+2;0\n').encode('utf-8-sig')
TXT = 'Первый абзац\r\n<b>Буквальная строка</b>\r\nТретий абзац'.encode('utf-16')
PACKAGE_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
OFFICE_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
XL_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
WORD_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def own_office(name, main, parts):
    word = name == 'docx'
    part = 'word/document.xml' if word else 'xl/workbook.xml'
    family = 'wordprocessingml.document' if word else 'spreadsheetml.sheet'
    mimetype = f'application/vnd.openxmlformats-officedocument.{family}.main+xml'
    entries = {'[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
               f'<Override PartName="/{part}" ContentType="{mimetype}"/></Types>',
               '_rels/.rels': f'<Relationships xmlns="{PACKAGE_NS}">'
               f'<Relationship Id="root" Type="{OFFICE_NS}/officeDocument" Target="{part}"/></Relationships>',
               part: main, **parts}
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for filename, data in entries.items():
            archive.writestr(filename, data)
    return output.getvalue()


def own_xlsx(formula='A3/1000'):
    workbook = f'<workbook xmlns="{XL_NS}" xmlns:r="{OFFICE_NS}">' \
               '<sheets><sheet name="Группа" sheetId="1" r:id="sheet"/></sheets>' \
               '<calcPr calcMode="manual" fullCalcOnLoad="1"/></workbook>'
    relationships = f'<Relationships xmlns="{PACKAGE_NS}">' \
                    f'<Relationship Id="sheet" Type="{OFFICE_NS}/worksheet" Target="worksheets/sheet1.xml"/>' \
                    f'<Relationship Id="style" Type="{OFFICE_NS}/styles" Target="styles.xml"/></Relationships>'
    sheet = f'<worksheet xmlns="{XL_NS}"><sheetData>' \
            '<row r="1"><c r="A1" t="inlineStr"><is><t>млн RUB</t></is></c></row>' \
            '<row r="2"><c r="A2" t="inlineStr"><is><t>Выручка</t></is></c>' \
            '<c r="B2" t="inlineStr"><is><t>2025</t></is></c></row>' \
            f'<row r="3"><c r="A3" s="1"><v>1234.50</v></c><c r="B3"><f>{formula}</f><v>1.23450</v></c>' \
            '<c r="C3"><f>A3+1</f></c></row></sheetData><autoFilter ref="A2:C3"/>' \
            '<mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells></worksheet>'
    styles = f'<styleSheet xmlns="{XL_NS}"><numFmts count="1">' \
             '<numFmt numFmtId="164" formatCode="0.0000"/></numFmts>' \
             '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>'
    return own_office('xlsx', workbook, {'xl/_rels/workbook.xml.rels': relationships,
                                         'xl/worksheets/sheet1.xml': sheet, 'xl/styles.xml': styles})


def own_docx():
    def paragraph(value):
        return f'<w:p><w:r><w:t>{value}</w:t></w:r></w:p>'

    main = f'<w:document xmlns:w="{WORD_NS}"><w:body>' + paragraph('Учебный документ') + \
           '<w:tbl><w:tblGrid><w:gridCol/><w:gridCol/><w:gridCol/></w:tblGrid>' \
           '<w:tr><w:trPr><w:tblHeader/></w:trPr>' \
           '<w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>' + paragraph('Сумма · млн RUB') + \
           '</w:tc><w:tc>' + paragraph('2025') + '</w:tc></w:tr><w:tr>' + \
           '<w:tc>' + paragraph('Выручка') + '</w:tc><w:tc>' + paragraph('1234,50') + \
           '</w:tc><w:tc>' + paragraph('Подтверждение') + '</w:tc></w:tr></w:tbl>' + \
           paragraph('Второй абзац') + '</w:body></w:document>'
    return own_office('docx', main, {})


def run_worker(install, app_data, cwd, vault, asset, *extra):
    process = subprocess.run([str(install / 'runtime/python.exe'), '-I', '-B', '-X', 'utf8',
                              str(install / 'app/spikes/windows_12/extract_cli.py'),
                              '--install-root', str(install), '--app-data', str(app_data), '--vault', str(vault),
                              '--asset-sha', asset, *extra], cwd=cwd, timeout=25, capture_output=True)
    assert not process.stderr and process.returncode in {0, 3}, process.returncode
    return process.returncode, process.stdout if extra and process.returncode == 0 else json.loads(process.stdout)


def inspect_extracted(data, kind):
    if kind == 'txt':
        assert data['encoding'] == 'utf-16' and data['delimiter'] is None
        assert data['paragraphs'][1] == {'locator': {'line': 2}, 'text': '<b>Буквальная строка</b>'}
        return
    table, = data['tables']
    rows = table['rows']
    if kind == 'csv':
        assert data['encoding'] == 'utf-8-sig' and data['delimiter'] == ';'
        assert rows[1]['cells'][1]['numeric_lexeme'] == '1234.50' and rows[1]['cells'][1]['text'] == '1\u202f234,50'
        assert rows[2]['cells'][1]['numeric_lexeme'] == '-300.00'
        assert rows[2]['cells'][2]['kind'] == 'blank' and rows[3]['cells'][2]['kind'] == 'missing'
        assert rows[4]['cells'][1]['text'] == '=2+2' and rows[4]['cells'][1]['kind'] == 'text'
    elif kind == 'xlsx':
        assert 'A1:B1' in table['merges'] and 2 in table['header_rows']
        first, formula, missing = rows[2]['cells']
        assert first['locator']['address'] == 'A3' and first['locator']['sheet'] == 'Группа'
        assert first['text'] == '1234.50' and first['format_code'] == '0.0000'
        assert formula['locator']['address'] == 'B3' and formula['formula'] == 'A3/1000'
        assert formula['cached_value'] == '1.23450' and formula['cache_status'] == 'stale'
        assert missing['cache_status'] == 'missing' and missing['cached_value'] is None
    else:
        assert 1 in table['header_rows'] and table['merges']
        assert {'part': 'word/document.xml', 'paragraph': 1} == data['paragraphs'][0]['locator']
        cell = rows[1]['cells'][1]
        assert cell['text'] == '1234,50'
        assert [cell['locator'][key] for key in ('table', 'row', 'column')] == [1, 2, 2]


def check(args):
    harness = runpy.run_path(str(ROOT / 'spikes/windows_11/check_import.py'))
    native_stage = runpy.run_path(str(ROOT / 'spikes/windows_08/check_shell.py'))
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / 'tmp') or out == ROOT / 'tmp':
        raise ValueError('Use a fresh path under ignored tmp/')
    out.mkdir(parents=True)
    install, app_data, cwd, vault_a, vault_b = [out / name for name in (
        'Установка', 'Данные', 'Пустой каталог', 'Хранилище А', 'Хранилище Б',
    )]
    app_data.mkdir()
    cwd.mkdir()
    harness['write_marker'](vault_a, 'win12-a')
    harness['write_marker'](vault_b, 'win12-b')
    prior, executable = native_stage['stage_install'](args.runtime_build, args.legacy_demo, install)
    before = prior['files'](install)
    candidates = {'csv': CSV, 'xlsx': own_xlsx(), 'docx': own_docx(), 'txt': TXT}
    test_input = out / 'Учебный CSV с расширением txt.txt'
    test_input.write_bytes(CSV)
    command = [str(executable), '--app-data', str(app_data), '--vault-a', str(vault_a),
               '--vault-b', str(vault_b), '--probe-extract', str(test_input)]
    process = subprocess.run(command, cwd=cwd, capture_output=True, timeout=90)
    path = app_data / 'win12-extract-probe.json'
    assert path.is_file(), process.returncode
    native = json.loads(path.read_bytes())
    assert process.returncode == 0 and native['ok'], native.get('incomplete_step')
    assert native['locator_verified'] and native['scope_cleared'] and native['same_preview']
    assert native['semantic_state'] == 'not_reviewed' and native['reused_status'] == 'reused'
    measured = {}
    for kind, contents in candidates.items():
        source = out / f'Собственный {kind}.test'
        source.write_bytes(contents)
        imported = harness['invoke'](install, app_data, cwd, vault_a, source)
        assert imported['file_type'] == kind and imported['status'] in {'captured', 'duplicate'}
        asset = imported['asset_sha256']
        if kind == 'txt':
            with ThreadPoolExecutor(max_workers=2) as pool:
                concurrent = [pool.submit(run_worker, install, app_data, cwd, vault_a, asset) for _ in range(2)]
                outcomes = [work.result() for work in concurrent]
            assert sorted(frame['status'] for _, frame in outcomes) == ['extracted', 'reused']
            code, extracted = next(item for item in outcomes if item[1]['status'] == 'extracted')
        else:
            code, extracted = run_worker(install, app_data, cwd, vault_a, asset)
        assert code == 0 and extracted['semantic_state'] == 'not_reviewed' and extracted['preview']
        assert extracted['file_type'] == kind and extracted['workspace_id'] == 'win12-a'
        receipt = vault_a / 'runs' / f'win12-extract-v1-{asset}.json'
        saved = receipt.read_bytes()
        artifact = json.loads(saved)
        assert artifact['asset_sha256'] == asset and artifact['file_type'] == kind
        inspect_extracted(artifact['data'], kind)
        repeated_code, repeated = run_worker(install, app_data, cwd, vault_a, asset)
        assert repeated_code == 0 and repeated['status'] == 'reused' and repeated['preview'] == extracted['preview']
        assert receipt.read_bytes() == saved
        if kind == 'csv':
            export_code, exported = run_worker(install, app_data, cwd, vault_a, asset, '--export-csv')
            assert export_code == 0
            rows = list(csv.reader(StringIO(exported.decode('utf-8-sig'), newline=''), delimiter=';'))
            assert rows[4][1] == "'=2+2" and rows[1][1] == '1\u202f234,50'
        elif kind == 'xlsx':
            assert any('B3: 1.23450 (кэш требует пересчёта)' in label for label in extracted['preview'])
            export_code, exported = run_worker(install, app_data, cwd, vault_a, asset, '--export-csv')
            assert export_code == 0
            rows = list(csv.reader(StringIO(exported.decode('utf-8-sig'), newline=''), delimiter=';'))
            assert rows[2][1] == "'=A3/1000"
        measured[kind] = {'tables': extracted['table_count'], 'paragraphs': extracted['paragraph_count'],
                          'preview_rows': len(extracted['preview']), 'reused_equal': True}

    blocked_path = out / 'Вымышленная внешняя ссылка.xlsx'
    blocked_path.write_bytes(own_xlsx('[example.xlsx]Sheet!A1'))
    blocked_capture = harness['invoke'](install, app_data, cwd, vault_a, blocked_path)
    assert blocked_capture['status'] == 'captured'
    bad_sha = blocked_capture['asset_sha256']
    code, blocked = run_worker(install, app_data, cwd, vault_a, bad_sha)
    assert code == 3 and blocked['error'] == 'xlsx_active_content' and blocked['preview'] == []
    assert not (vault_a / 'runs' / f'win12-extract-v1-{bad_sha}.json').exists()

    code, alien = run_worker(install, app_data, cwd, vault_b, native['asset_sha256'])
    assert code == 3 and alien['preview'] == [] and alien['asset_sha256'] is None
    paths = ApplicationPaths(install, app_data)
    with VaultStore(WorkspaceContext.open(paths, vault_a)) as store:
        assert store.search('Выручка') == [] and store.summary()['fts_rows'] == 0
    assert prior['files'](install) == before and prior['files'](cwd) == {}
    report = {'schema': 'win12-native-extraction-proof-1', 'native': native, 'formats': measured,
              'csv_formula_escape_verified': True, 'cross_vault_refused': True, 'indexed_rows': 0,
              'concurrent_txt_single_receipt': True, 'external_formula_refused': True,
              'program_hashes_unchanged': len(before)}
    (out / 'extract-proof.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build', required=True, type=Path)
    parser.add_argument('--legacy-demo', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    check(parser.parse_args())


if __name__ == '__main__':
    main()
