"""Multi-document evidence retrieval. Prepared evidence and automatic candidates stay separate."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from .catalog import available_from,validate_catalog
from .contracts_v2 import CHECKED,ClarificationRequired,ContractError,digest,identifier,instant,period,shape,text,unit
from .document_extraction import SCHEMA,ExtractionError,canonical,fingerprint,normalized,read_private_json,source_identity

ROOT=Path(__file__).resolve().parents[2]
INDEX_SCHEMA='kp3-index-0.1'
SEARCH_SCHEMA='kp3-search-0.1'


class RetrievalError(ValueError):
    def __init__(self,code):self.code=code;super().__init__(code)


def need(ok,code):
    if not ok:raise RetrievalError(code)


def private_path(path):
    p=Path(path).resolve()
    need(p.is_relative_to((ROOT/'tmp').resolve()),'private_path_required')
    return p


def file_sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def _lexicon(lexicon):
    need(type(lexicon) is dict and set(lexicon)=={'lexicon_version','description','metrics','stopwords'} and lexicon['lexicon_version']=='1.0','invalid_lexicon')
    for row in lexicon['metrics'].values():
        need(set(row)=={'tag','search_aliases','candidate_rows'} and re.fullmatch('[a-z]+',row['tag']) is not None,'invalid_lexicon')
        need(all(isinstance(x,str) and x.strip() for x in row['search_aliases']+row['candidate_rows']),'invalid_lexicon')
    return lexicon


def normalize_query(query,lexicon):
    n=normalized(query)
    aliases=sorted(((normalized(alias),row['tag']) for row in lexicon['metrics'].values() for alias in row['search_aliases']),key=lambda x:len(x[0]),reverse=True)
    for alias,tag in aliases:n=re.sub(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',tag,n)
    return [w for w in re.findall(r'[^\W_]+',n) if w not in lexicon['stopwords']]


def _fts_query(tokens,lexicon):
    known_tags={m['tag'] for m in lexicon['metrics'].values()}
    tags=[t for t in dict.fromkeys(tokens) if t in known_tags]
    other=[t for t in dict.fromkeys(tokens) if t not in known_tags]
    quoted=lambda t:'"'+t.replace('"','""')+'"'
    groups=['('+ ' OR '.join(map(quoted,tags))+')'] if tags else []
    groups+=list(map(quoted,other))
    return ' AND '.join(groups)


def _signature(cfg,lexicon):
    # Admission/number semantics are dependencies too, not only the FTS implementation.
    dependencies=['src/financial_assistant/catalog.py','src/financial_assistant/contracts_v2.py','src/financial_assistant/contracts.py']
    return canonical(dict(schema=INDEX_SCHEMA,code_sha256=file_sha(Path(__file__)),validation_code={p:file_sha(ROOT/p) for p in dependencies},extractor=fingerprint(ROOT,cfg),lexicon=lexicon))


def _record_terms(row,lexicon):
    tag=lexicon['metrics'][row['metric_id']]['tag']
    return normalized(' '.join([tag,row['row_label'],row['raw_value'],row['value'],row['period']['start'],row['period']['end'],row['currency']]))


def prepared_records(catalog):
    docs={d['document_id']:d for d in catalog['documents']};orgs={o['organization_id']:o for o in catalog['organizations']};evs={e['evidence_id']:e for e in catalog['evidence']}
    records=[];contexts=set()
    for f in catalog['facts']:
        d=docs[f['document_id']];e=evs.get(f['evidence_id'])
        need(d['preparation_status'] in {'ready','checked'} and d['provenance']['status'] in CHECKED,'document_unprepared')
        need(f['provenance']['status'] in CHECKED and e is not None and e['provenance']['status'] in CHECKED and f['value'] is not None,'unverified_prepared_input')
        context=canonical([f[k] for k in ['document_id','metric_id','definition_id','period','currency','scale']])
        need(context not in contexts,'prepared_fact_conflict');contexts.add(context)
        records.append(dict(record_id=e['evidence_id'],document_id=d['document_id'],version_id=d['version_id'],document_sha256=d['sha256'],organization_id=d['organization_id'],consolidation=orgs[d['organization_id']]['consolidation'],accounting_standard=d['accounting_standard'],metric_id=f['metric_id'],definition_id=f['definition_id'],period=f['period'],currency=f['currency'],scale=f['scale'],raw_value=e['raw_value'],value=f['value'],row_label=f['original_label'],origin_role=f['origin_role'],locator=e['locator'],evidence_id=e['evidence_id'],evidence_digest=f['evidence_digest'],verification_status=f['provenance']['status'],source_kind='prepared_evidence',reverification_performed=False))
    return records


def validate_export(export,doc,cfg):
    """Hash/schema linkage is technical integrity, never source semantics approval."""
    need(type(export) is dict and set(export)=={'schema_version','document_sha256','byte_length','pdf_pages','extractor_fingerprint','config','environment','origin','pages'},'invalid_export_schema')
    need(export['schema_version']==SCHEMA and export['origin']=='automatic_pdf_geometry_candidates','unsupported_export_mode')
    need(export['document_sha256']==doc['sha256'] and export['pdf_pages']==doc['pdf_pages'] and export['byte_length']==doc['byte_length'],'extraction_version_mismatch')
    need(export['config']==cfg and export['extractor_fingerprint']==fingerprint(ROOT,cfg),'extraction_configuration_mismatch')
    need(export['environment']==dict(python=cfg['worker_python'],pdfplumber=cfg['pdfplumber'],pdfminer_six=cfg['pdfminer_six']),'worker_environment_mismatch')
    need(type(export['pages']) is list and len(export['pages'])==doc['pdf_pages'],'invalid_export_pages')
    def bbox(value,within=None):
        need(type(value) is list and len(value)==4 and all(type(x) in {int,float} and math.isfinite(x) for x in value)
             and value[0]<value[2] and value[1]<value[3],'invalid_bbox')
        if within is not None:
            need(value[0]>=within[0]-1 and value[1]>=within[1]-1 and value[2]<=within[2]+1 and value[3]<=within[3]+1,'bbox_outside_context')
    for expected,p in enumerate(export['pages'],1):
        need(set(p)=={'pdf_page','width','height','bbox','regions'} and p['pdf_page']==expected,'invalid_export_page')
        need(type(p['width']) in {int,float} and type(p['height']) in {int,float} and p['width']>0 and p['height']>0,'invalid_page_size')
        bbox(p['bbox'])
        seen=set()
        for r in p['regions']:
            need(set(r)=={'region_id','bbox','text','status','reason_code','tables'},'invalid_export_region')
            need(r['region_id'] in {'full_page','left_half_of_spread','right_half_of_spread'} and r['region_id'] not in seen,'duplicate_or_invalid_region');seen.add(r['region_id'])
            need(r['status'] in {'structured','not_recognized','unsupported_layout'} and type(r['text']) is str and '\x00' not in r['text'],'invalid_region_status')
            need((r['status']=='structured')==bool(r['tables']),'empty_successful_table')
            bbox(r['bbox'],p['bbox'])
            for t in r['tables']:
                need(type(t) is dict and set(t)=={'table_id','statement_type','title','unit_header','currency','scale','columns','rows','bbox'},'invalid_table_schema')
                need(t['statement_type'] in cfg['statement_types'] and t['rows'] and t['columns'] and t['title'] and t['unit_header'],'incomplete_table_context')
                need(t['table_id']==f"p{p['pdf_page']}:{r['region_id']}:0",'table_locator_mismatch')
                from .document_extraction import column_period,unit_from_header
                need(unit_from_header(t['unit_header'])==(t['currency'],t['scale']),'table_unit_mismatch')
                bbox(t['bbox'],r['bbox'])
                need(len({col['column_index'] for col in t['columns']})==len(t['columns']),'duplicate_column')
                need(len({row['row_index'] for row in t['rows']})==len(t['rows']),'duplicate_row')
                for col in t['columns']:period(col['period']);need(bool(col['header']),'column_header_missing')
                for col in t['columns']:
                    need(set(col)=={'column_index','year','header','period','x_min','x_max'},'invalid_column_schema')
                    need(col['period']==column_period(col['year'],col['header'].rsplit(' / ',1)[0],t['title']),'column_period_mismatch')
                for row in t['rows']:
                    need(set(row)=={'row_index','row_label','bbox','cells'},'invalid_row_schema')
                    need(bool(row['row_label']) and bool(row['cells']),'empty_row')
                    bbox(row['bbox'],t['bbox'])
                    need(len({x['column_index'] for x in row['cells']})==len(row['cells']),'duplicate_cell_column')
                    for cell in row['cells']:
                        need(set(cell)=={'column_index','column_header','period','raw_value','value','numeric_encoding','bbox','provenance'},'invalid_cell_schema')
                        need(cell['provenance']=='candidate','invented_extractor_review')
                        period(cell['period'])
                        from .document_extraction import source_number
                        value,encoding=source_number(cell['raw_value'])
                        need(value==cell['value'] and encoding==cell['numeric_encoding'],'candidate_numeric_mismatch')
                        cols=[c for c in t['columns'] if c['column_index']==cell['column_index']]
                        need(len(cols)==1 and cols[0]['period']==cell['period'] and cols[0]['header']==cell['column_header'],'candidate_column_mismatch')
                        bbox(cell['bbox'],r['bbox'])
                        need(cell['bbox'][1]>=row['bbox'][1]-1 and cell['bbox'][3]<=row['bbox'][3]+1,'candidate_row_bbox_mismatch')
                        need(cols[0]['x_min']<=(cell['bbox'][0]+cell['bbox'][2])/2<cols[0]['x_max'],'candidate_column_bbox_mismatch')


def automatic_records(doc,org,metrics,export,lexicon):
    """Receives metadata and PDF-derived tables, no Fact/Evidence/expected/gold inputs."""
    records=[];diagnostics=dict(table_counts={'income':0,'cash_flow':0},unrecognized_regions=0,unsupported_regions=[])
    for page in export['pages']:
        for region in page['regions']:
            if region['status']!='structured':
                diagnostics['unrecognized_regions']+=1
                if region['status']=='unsupported_layout':diagnostics['unsupported_regions'].append(dict(pdf_page=page['pdf_page'],region=region['region_id'],reason_code=region['reason_code']))
            for table in region['tables']:
                diagnostics['table_counts'][table['statement_type']]+=1
                for row in table['rows']:
                    labels=[mid for mid,v in lexicon['metrics'].items() if normalized(row['row_label']) in {normalized(x) for x in v['candidate_rows']}]
                    for mid in labels:
                        if (mid=='operating_cash_flow') != (table['statement_type']=='cash_flow'):continue
                        metric=metrics.get(mid)
                        if metric is None:continue
                        for cell in row['cells']:
                            locator=dict(kind='pdf',pdf_page=page['pdf_page'],page_region=region['region_id'],table_id=table['table_id'],table_title=table['title'],row_label=row['row_label'],column_label=cell['column_header'],column_index=cell['column_index'],unit_header=table['unit_header'],table_bbox=table['bbox'],row_bbox=row['bbox'],cell_bbox=cell['bbox'],printed_page=None,statement_page=None)
                            key=[doc['sha256'],page['pdf_page'],region['region_id'],table['table_id'],row['row_index'],cell['column_index']]
                            role='reported_period' if cell['period']==doc['report_period'] else 'comparative_period' if cell['period']['end']<doc['report_period']['end'] else 'subperiod_not_admitted'
                            records.append(dict(record_id='cell:'+canonical(key),document_id=doc['document_id'],version_id=doc['version_id'],document_sha256=doc['sha256'],organization_id=doc['organization_id'],consolidation=org['consolidation'],accounting_standard=doc['accounting_standard'],metric_id=mid,definition_id=metric['definition_id'],period=cell['period'],currency=table['currency'],scale=table['scale'],raw_value=cell['raw_value'],value=cell['value'],row_label=row['row_label'],origin_role=role,locator=locator,evidence_id=None,evidence_digest=None,verification_status='candidate',source_kind='automatic_candidate',reverification_performed=False))
    return records,diagnostics


def _unique_records(records):
    ids={};cells={}
    for r in records:
        ident=r['record_id']
        if ident in ids:
            need(ids[ident]==r,'duplicate_cell_conflict');continue
        loc=r['locator']
        key=canonical([r['document_sha256'],loc.get('pdf_page'),loc.get('page_region'),loc['cell_bbox']]) if 'cell_bbox' in loc else canonical([r['document_id'],r['period'],r['metric_id'],loc])
        if key in cells:
            old=ids[cells[key]]
            comparison=['document_id','version_id','organization_id','consolidation','accounting_standard','metric_id','definition_id','period','currency','scale','raw_value','value','row_label','verification_status','source_kind']
            need(all(old[k]==r[k] for k in comparison),'duplicate_cell_conflict')
            continue
        cells[key]=ident;ids[ident]=r
    return list(ids.values())


def build_index(db_path,catalog,resources,cfg,lexicon,kind,export_paths=None):
    validate_catalog(catalog);lexicon=_lexicon(lexicon)
    need(kind in {'prepared','automatic'},'explicit_index_kind_required')
    db=private_path(db_path);sidecar=Path(str(db)+'.manifest.json')
    need(not db.exists() and not sidecar.exists(),'index_exists')
    docs={d['document_id']:d for d in catalog['documents']};orgs={o['organization_id']:o for o in catalog['organizations']};metrics={m['metric_id']:m for m in catalog['metrics']}
    for d in docs.values():
        need(d['availability']['local_resource_id'] in resources,'source_missing')
        source_identity(resources[d['availability']['local_resource_id']],d)
    diagnostics={};export_hashes={}
    if kind=='prepared':
        need(not export_paths,'unexpected_export_resources');records=prepared_records(catalog)
    else:
        need(type(export_paths) is dict and set(export_paths)==set(docs),'export_resources_required')
        records=[]
        for did,path in export_paths.items():
            export=read_private_json(private_path(path));validate_export(export,docs[did],cfg)
            rows,diagnostics[did]=automatic_records(docs[did],orgs[docs[did]['organization_id']],metrics,export,lexicon)
            records+=rows;export_hashes[did]=file_sha(path)
    records=_unique_records(records)
    need(records,'index_has_no_records')
    meta=dict(index_schema=INDEX_SCHEMA,kind=kind,catalog_digest=digest(catalog),configuration_signature=_signature(cfg,lexicon),sources={k:d['sha256'] for k,d in docs.items()},export_hashes=export_hashes,record_count=len(records),diagnostics=diagnostics)
    db.parent.mkdir(parents=True,exist_ok=True)
    with db.open('xb'):pass
    try:
        with closing(sqlite3.connect(db)) as con:
            with con:
                con.execute('CREATE TABLE metadata(payload TEXT NOT NULL)')
                con.execute('CREATE TABLE records(id INTEGER PRIMARY KEY,document_id TEXT,metric_id TEXT,definition_id TEXT,period_key TEXT,role TEXT,currency TEXT,scale INTEGER,payload TEXT)')
                con.execute("CREATE VIRTUAL TABLE search USING fts5(terms, tokenize='unicode61')")
                con.execute('INSERT INTO metadata VALUES (?)',(json.dumps(meta,ensure_ascii=False),))
                for i,r in enumerate(records,1):
                    con.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)',(i,r['document_id'],r['metric_id'],r['definition_id'],canonical(r['period']),r['origin_role'],r['currency'],r['scale'],json.dumps(r,ensure_ascii=False)))
                    con.execute('INSERT INTO search(rowid,terms) VALUES (?,?)',(i,_record_terms(r,lexicon)))
    except sqlite3.Error as exc:raise RetrievalError('index_build_failed') from exc
    manifest=dict(index_schema=INDEX_SCHEMA,index_sha256=file_sha(db),metadata_digest=canonical(meta))
    with sidecar.open('x',encoding='utf-8') as stream:json.dump(manifest,stream,ensure_ascii=False,indent=2)
    return dict(status='indexed',kind=kind,records=len(records),documents=len(docs),index_sha256=manifest['index_sha256'],configuration_signature=meta['configuration_signature'],financial_status=None,facts_admitted=0)


def validate_search(spec,catalog):
    need(type(spec) is dict,'invalid_search_spec')
    fields={'schema_version','query','organization_id','consolidation','accounting_standard','metrics','periods','documents','source_units','version_policy','mode','as_of','top_k'}
    need(not (set(spec)-fields),'unknown_search_field')
    missing=[k for k in fields-{'as_of'} if k not in spec or spec[k] is None or spec[k]=='' or spec[k]==[]]
    if missing:raise ClarificationRequired('missing_fields',sorted(missing))
    need(set(spec)==fields and spec['schema_version']==SEARCH_SCHEMA,'invalid_search_schema')
    need(isinstance(spec['query'],str) and 0<len(spec['query'])<=500,'invalid_query')
    need(type(spec['top_k']) is int and 1<=spec['top_k']<=32,'invalid_top_k')
    orgs={o['organization_id']:o for o in catalog['organizations']};metrics={m['metric_id']:m for m in catalog['metrics']};docs={d['document_id']:d for d in catalog['documents']}
    need(spec['organization_id'] in orgs,'unknown_organization_id');org=orgs[spec['organization_id']]
    need(spec['consolidation']==org['consolidation'] and spec['accounting_standard'] in org['accounting_standards'],'entity_or_standard_mismatch')
    need(type(spec['documents']) is list and 0<len(spec['documents'])<=16,'invalid_document_selection')
    selected=set()
    for ref in spec['documents']:
        shape(ref,'document_id version_id');did=ref['document_id']
        need(did in docs,'unknown_document_id');need(did not in selected,'duplicate_document_selection');selected.add(did);doc=docs[did]
        need(ref['version_id']==doc['version_id'],'document_version_mismatch')
        need(doc['organization_id']==spec['organization_id'] and doc['accounting_standard']==spec['accounting_standard'],'entity_or_standard_mismatch')
    need(type(spec['metrics']) is list and 0<len(spec['metrics'])<=8,'invalid_metric_selection')
    seen=set()
    for ref in spec['metrics']:
        shape(ref,'metric_id definition_id');mid=ref['metric_id'];need(mid in metrics,'unknown_metric_id')
        need(mid not in seen,'duplicate_metric_selection');seen.add(mid);need(ref['definition_id']==metrics[mid]['definition_id'],'unknown_metric_definition')
    need(type(spec['periods']) is list and 0<len(spec['periods'])<=8,'invalid_period_selection')
    for p in spec['periods']:period(p)
    for p in spec['periods']:
        need(all(p['kind'] in metrics[ref['metric_id']]['period_kinds'] for ref in spec['metrics']),'metric_period_mismatch')
    need(len({canonical(p) for p in spec['periods']})==len(spec['periods']),'duplicate_period_selection')
    need(type(spec['source_units']) is list and 0<len(spec['source_units'])<=8,'invalid_source_units')
    for u in spec['source_units']:unit(u)
    need(len({canonical(u) for u in spec['source_units']})==len(spec['source_units']),'duplicate_source_unit')
    need(spec['version_policy'] in {'explicit_versions','original_period_documents'},'invalid_version_policy')
    need(spec['mode'] in {'snapshot','historical'},'invalid_mode')
    if spec['mode']=='historical':need(spec['as_of'] is not None,'as_of_required');instant(spec['as_of'])
    else:need(spec['as_of'] is None,'as_of_requires_historical')
    return [docs[did] for did in sorted(selected)]


def search_index(db_path,catalog,resources,cfg,lexicon,spec,export_paths=None):
    validate_catalog(catalog);lexicon=_lexicon(lexicon);docs=validate_search(spec,catalog)
    tokens=normalize_query(spec['query'],lexicon);need(tokens,'invalid_query')
    db=private_path(db_path);sidecar=Path(str(db)+'.manifest.json')
    need(db.is_file(),'index_missing');need(sidecar.is_file(),'index_manifest_missing')
    manifest=read_private_json(sidecar,1000000)
    need(set(manifest)=={'index_schema','index_sha256','metadata_digest'} and manifest['index_schema']==INDEX_SCHEMA,'index_manifest_invalid')
    need(file_sha(db)==manifest['index_sha256'],'index_hash_mismatch')
    for d in docs:
        need(d['availability']['local_resource_id'] in resources,'source_missing');source_identity(resources[d['availability']['local_resource_id']],d)
    try:
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as con:
            con.execute('PRAGMA query_only=ON');con.execute('PRAGMA trusted_schema=OFF')
            meta=json.loads(con.execute('SELECT payload FROM metadata').fetchone()[0])
            need(canonical(meta)==manifest['metadata_digest'],'index_metadata_mismatch')
            need(meta['catalog_digest']==digest(catalog),'index_catalog_mismatch')
            need(meta['configuration_signature']==_signature(cfg,lexicon),'index_configuration_mismatch')
            need(meta['sources']=={d['document_id']:d['sha256'] for d in catalog['documents']},'index_source_mismatch')
            if meta['kind']=='automatic':
                need(type(export_paths) is dict and set(export_paths)==set(meta['export_hashes']),'export_resources_required')
                for did in [d['document_id'] for d in docs]:
                    path=private_path(export_paths[did]);need(path.is_file(),'extraction_missing');need(file_sha(path)==meta['export_hashes'][did],'extraction_hash_mismatch')
            result=dict(schema_version=SEARCH_SCHEMA,status='found',reason_code='ok',financial_status=None,source_kind=meta['kind'],results=[],reverification_performed=False,warnings=['source_text_untrusted','retrieval_is_not_financial_answer'],index_sha256=manifest['index_sha256'])
            if spec['mode']=='historical':
                stamps=[available_from(d) for d in docs]
                if any(s is None for s in stamps):result.update(status='blocked',reason_code='publication_unknown');return result
                if any(instant(spec['as_of'])<s for s in stamps):result.update(status='blocked',reason_code='not_yet_available');return result
            mids=[m['metric_id'] for m in spec['metrics']];periods=[canonical(p) for p in spec['periods']];dids=[d['document_id'] for d in docs]
            placeholders=lambda xs:','.join('?' for _ in xs)
            sql='SELECT r.payload FROM search JOIN records r ON r.id=search.rowid WHERE search MATCH ? AND r.document_id IN ('+placeholders(dids)+') AND r.metric_id IN ('+placeholders(mids)+') AND r.period_key IN ('+placeholders(periods)+')'
            params=[_fts_query(tokens,lexicon),*dids,*mids,*periods]
            sql+=' AND ('+' OR '.join('(r.currency=? AND r.scale=?)' for u in spec['source_units'])+')'
            for u in spec['source_units']:params += [u['currency'],u['scale']]
            if spec['version_policy']=='original_period_documents':sql+=" AND r.role='reported_period'"
            sql+=' ORDER BY bm25(search),r.document_id,r.metric_id,r.period_key,r.id LIMIT ?';params.append(spec['top_k'])
            result['results']=[json.loads(row[0]) for row in con.execute(sql,params).fetchall()]
            returned={(row['metric_id'],canonical(row['period'])) for row in result['results']}
            missing=[dict(metric_id=m['metric_id'],definition_id=m['definition_id'],period=p) for m in spec['metrics'] for p in spec['periods'] if (m['metric_id'],canonical(p)) not in returned]
            result['requested_context_coverage']=dict(requested_metric_period_slots=len(spec['metrics'])*len(spec['periods']),matched_slots=len(returned),missing_contexts=missing,scope='Metric/period coverage only; not financial approval or evidence gold.')
            if result['results'] and missing:result.update(status='partial',reason_code='incomplete_evidence_context')
            if not result['results']:
                unsupported=meta['kind']=='automatic' and any(meta['diagnostics'][d['document_id']]['table_counts']['cash_flow' if mid=='operating_cash_flow' else 'income']==0 for d in docs for mid in mids)
                result.update(status='unsupported_layout' if unsupported else 'not_found',reason_code='statement_table_unavailable' if unsupported else 'original_version_missing' if spec['version_policy']=='original_period_documents' else 'no_matching_evidence_context')
            if meta['kind']=='automatic':result['warnings'].append('automatic_candidates_are_not_assistant_checked')
            return result
    except (sqlite3.Error,json.JSONDecodeError,KeyError,TypeError) as exc:raise RetrievalError('index_invalid') from exc
