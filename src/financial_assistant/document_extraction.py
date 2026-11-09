"""Geometry-based table candidates. No catalog, expected amounts, Fact admission or financial formulas."""
from calendar import monthrange
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import unicodedata

SCHEMA = 'kp3-extraction-0.1'


class ExtractionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def need(ok, code):
    if not ok:
        raise ExtractionError(code)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().replace('ё', 'е').split())


def load_config(path):
    cfg = read_private_json(path)
    required = {'profile_version','max_pdf_bytes','max_pages','spread_aspect_min','x_tolerance','y_tolerance','line_tolerance','horizontal_text_only','title_top_fraction','statement_types','ocr','worker_python','pdfplumber','pdfminer_six'}
    need(type(cfg) is dict and set(cfg) == required and cfg['profile_version'] == '1.0', 'invalid_extractor_config')
    for k in ['max_pdf_bytes','max_pages']:
        need(type(cfg[k]) is int and 0 < cfg[k] <= (50000000 if k == 'max_pdf_bytes' else 200), 'invalid_extractor_config')
    for k in ['spread_aspect_min','x_tolerance','y_tolerance','line_tolerance','title_top_fraction']:
        need(type(cfg[k]) in {int,float} and 0 < cfg[k] <= 10, 'invalid_extractor_config')
    need(cfg['ocr'] is False and cfg['horizontal_text_only'] is True and cfg['statement_types'] == ['income','cash_flow'], 'unsupported_extractor_config')
    return cfg


def read_private_json(path, limit=32000000):
    p = Path(path); need(p.stat().st_size <= limit, 'export_too_large')
    def unique(rows):
        out = {}
        for k,v in rows:
            need(k not in out, 'duplicate_json_key'); out[k] = v
        return out
    def invalid(_): raise ExtractionError('invalid_json_number')
    try:
        return json.loads(p.read_text(encoding='utf-8-sig'), object_pairs_hook=unique, parse_constant=invalid)
    except (UnicodeError,json.JSONDecodeError):
        raise ExtractionError('invalid_json') from None


def fingerprint(root, cfg):
    root = Path(root)
    files = ['scripts/extract_pdf_v2.py','src/financial_assistant/document_extraction.py']
    return canonical(dict(schema=SCHEMA, config=cfg, code={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}))


def source_identity(pdf, doc):
    p = Path(pdf)
    need(p.is_file(), 'source_missing')
    need(p.stat().st_size == doc['byte_length'], 'source_version_mismatch')
    need(p.stat().st_size <= 50000000, 'source_too_large')
    with p.open('rb') as f:
        need(f.read(5) == b'%PDF-', 'source_not_pdf'); f.seek(0)
        data=f.read(doc['byte_length']+1)
        need(len(data)==doc['byte_length'] and hashlib.sha256(data).hexdigest() == doc['sha256'], 'source_version_mismatch')
    return doc['sha256']


def source_number(raw):
    """Explicit notation, preserve raw token separately; dash/decimal comma are unsupported."""
    need(isinstance(raw,str) and 0 < len(raw) <= 60, 'unsupported_numeric_notation')
    neg = raw.startswith('(') and raw.endswith(')')
    body = raw[1:-1] if neg else raw
    if re.fullmatch(r'[0-9]{1,3}(?:,[0-9]{3})+',body):
        encoding = 'comma_thousands_integer'; token = body.replace(',','')
    elif re.fullmatch(r'[0-9]{1,3}(?: [0-9]{3})+',body):
        encoding = 'space_thousands_integer'; token = body.replace(' ','')
    elif re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',body):
        need(not (neg and body.startswith('-')), 'unsupported_numeric_notation')
        encoding = 'decimal_string'; token = body
    else:
        raise ExtractionError('unsupported_numeric_notation')
    if neg: token = '-' + token
    need(re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',token) is not None, 'unsupported_numeric_notation')
    Decimal(token)
    return token,encoding


def lines_from_words(words, tolerance):
    lines = []
    for w in sorted(words,key=lambda w:(w['top'],w['x0'])):
        if lines and abs(lines[-1]['top']-w['top']) <= tolerance:
            lines[-1]['words'].append(w)
            lines[-1]['bottom'] = max(lines[-1]['bottom'],w['bottom'])
        else:
            lines.append(dict(top=w['top'],bottom=w['bottom'],words=[w]))
    for line in lines:
        line['words'].sort(key=lambda w:w['x0'])
        line['text'] = ' '.join(w['text'] for w in line['words'])
    return lines


def unit_from_header(text):
    n = normalized(text)
    if re.search(r'млн\.?\s+руб|миллионах российских рублей',n):return 'RUB',1000000
    if 'тысячах российских рублей' in n:return 'RUB',1000
    if re.search(r'\busd\s+million\b',n):return 'USD',1000000
    raise ExtractionError('unit_header_unavailable')


MONTHS = {'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}
COUNTS = {'три':3,'шесть':6,'девять':9,'двенадцать':12}


def column_period(year, header, title):
    h=normalized(header);t=normalized(title)
    if re.search(r'за\s+\d{4}\s+год',t):
        return dict(kind='duration',duration_type='full_year',start=f'{year}-01-01',end=f'{year}-12-31')
    dates=list(re.finditer(r'(\d{1,2})\s+('+'|'.join(MONTHS)+r')\b',h))
    counts=[n for word,n in COUNTS.items() if re.search(r'\b'+word+r'\s+месяц',h)]
    need(len(dates)==1 and len(counts)==1,'period_header_unavailable')
    day=int(dates[0][1]);month=MONTHS[dates[0][2]];count=counts[0]
    need(day==monthrange(year,month)[1] and count <= month, 'unsupported_duration_header')
    start_month=month-count+1
    kind='quarter' if count==3 and start_month in {1,4,7,10} else 'year_to_date' if start_month==1 and count<12 else 'custom'
    return dict(kind='duration',duration_type=kind,start=f'{year}-{start_month:02d}-01',end=f'{year}-{month:02d}-{day:02d}')


def parse_region(words, box, page_number, region_id, cfg):
    """Parse a statement by its visible title, unit, year centres and duration headers."""
    lines=lines_from_words(words,cfg['line_tolerance'])
    result=dict(region_id=region_id,bbox=list(box),text='\n'.join(l['text'] for l in lines),status='not_recognized',reason_code='no_supported_statement_title',tables=[])
    top=[l for l in lines if l['top'] < box[1]+(box[3]-box[1])*cfg['title_top_fraction']]
    title_lines=[];started=False
    for l in top:
        n=normalized(l['text'])
        if 'консолидирован' in n and re.search(r'\bотчет\b',n):started=True
        if started:
            if re.search(r'млн|тысячах|миллионах|прим\.|\busd\b',n):break
            title_lines.append(l)
            if re.search(r'\b20\d{2}\s+год(?:а)?\b',n):break
    if not title_lines:
        if not words or len(result['text'].strip())<40:
            result.update(status='unsupported_layout',reason_code='text_layer_empty_or_sparse')
        return result
    title=' '.join(l['text'] for l in title_lines);n=normalized(title)
    statement='cash_flow' if 'движении денежных средств' in n else 'income' if re.search(r'прибыл|убыт',n) and 'доход' in n else None
    if statement is None:return result
    result.update(status='unsupported_layout',reason_code='column_header_unavailable')
    try:
        headers=[]
        for line in top:
            years=[w for w in line['words'] if re.fullmatch(r'20\d{2}',w['text'])]
            if len(years) in {2,4} and len({w['text'] for w in years})==2 and line['top']>title_lines[0]['top']:
                headers.append((line,years))
        need(len(headers)==1,'column_header_unavailable')
        line,years=headers[0];centres=[(w['x0']+w['x1'])/2 for w in years]
        need(centres==sorted(centres) and len(set(centres))==len(centres),'invalid_column_geometry')
        unit_lines=[l for l in top if l['top']<=line['bottom']+3 and re.search(r'млн|тысячах|миллионах|\busd\b',normalized(l['text']))]
        need(len(unit_lines)==1,'unit_header_unavailable');unit_header=unit_lines[0]['text']
        currency,scale=unit_from_header(unit_header)
        bounds=[centres[0]-(centres[1]-centres[0])/2]+[(a+b)/2 for a,b in zip(centres,centres[1:])]+[min(box[2],centres[-1]+(centres[-1]-centres[-2])/2)]
        columns=[]
        for i,w in enumerate(years):
            group_left=box[0] if len(years)==2 else box[0] if i<2 else bounds[2]
            group_right=box[2] if len(years)==2 else bounds[2] if i<2 else box[2]
            # Only the local multi-level header, excluding the title and year line.
            group_words=[x for l in top if l['top']>title_lines[-1]['bottom'] and l['bottom']<line['top']+2 for x in l['words'] if group_left<=(x['x0']+x['x1'])/2<group_right]
            group=' '.join(x['text'] for x in group_words)
            columns.append(dict(column_index=i,year=int(w['text']),header=(group+' / ' if group else '')+w['text'],period=column_period(int(w['text']),group,title),x_min=bounds[i],x_max=bounds[i+1]))
        rows=[];pending=[];last_bottom=line['bottom']
        numeric_token=re.compile(r'[-–—()]|[()]?-?[0-9][0-9,.]*[()]?')
        for l in lines:
            if l['top']<=line['bottom']+2:continue
            if l['top']>box[3]-35:break
            slots=[]
            for col in columns:
                ws=[w for w in l['words'] if col['x_min']<=(w['x0']+w['x1'])/2<col['x_max'] and numeric_token.fullmatch(w['text'])]
                slots.append(ws)
            has_values=any(slots)
            if l['top']-last_bottom>9:pending=[]
            if not has_values:
                text=l['text']
                if text.endswith(':') or not re.search(r'[а-яА-ЯA-Za-z]',text):pending=[]
                else:pending.append(l)
                last_bottom=l['bottom'];continue
            leftmost=min(w['x0'] for ws in slots for w in ws)
            label_words=[w for w in l['words'] if w['x0']<leftmost and re.search(r'[а-яА-ЯA-Za-z]',w['text'])]
            label=' '.join([p['text'] for p in pending]+[w['text'] for w in label_words]).strip()
            row_top=min([l['top']]+[p['top'] for p in pending])
            pending=[];last_bottom=l['bottom']
            if not label:continue
            values=[]
            for col,ws in zip(columns,slots):
                if not ws:continue
                raw=' '.join(w['text'] for w in ws)
                try:value,encoding=source_number(raw)
                except ExtractionError:continue
                cell_box=[min(w['x0'] for w in ws),min(w['top'] for w in ws),max(w['x1'] for w in ws),max(w['bottom'] for w in ws)]
                values.append(dict(column_index=col['column_index'],column_header=col['header'],period=col['period'],raw_value=raw,value=value,numeric_encoding=encoding,bbox=cell_box,provenance='candidate'))
            if values:rows.append(dict(row_index=len(rows),row_label=label,bbox=[box[0],row_top,box[2],l['bottom']],cells=values))
        need(rows,'table_empty')
        table=dict(table_id=f'p{page_number}:{region_id}:0',statement_type=statement,title=title,unit_header=unit_header,currency=currency,scale=scale,columns=columns,rows=rows,bbox=list(box))
        result.update(status='structured',reason_code='candidate_table_extracted',tables=[table])
    except ExtractionError as exc:
        result['reason_code']=exc.code
    return result
