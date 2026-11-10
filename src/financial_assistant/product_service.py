"""P0 product routing. Existing B/C/A and scenario implementations own all calculations."""
from pathlib import Path
from contextlib import closing
from .contracts_v2 import digest,need,read_json
from .service_b import execute
from .agent_c import execute_c
from .agent_model_v2 import load_agent_model
from .one_shot_a import execute_a
from .one_shot_model import load_one_shot_model
from .scenario_service import own_financial,execute_scenario
from .scenario_contracts_v1 import REQUEST
from .retrieval_v2 import file_sha,_signature
from .document_extraction import canonical
import hashlib,json,os,sqlite3
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
METHODS={'B':'B · фиксированный путь, без модели','C':'C · агент с инструментами','A':'A · один выбор модели'}

def preflight(ctx):
    """Read-only readiness, NOT search or fresh financial answer. No fallback on failures."""
    ctx.validate();rows=[]
    for d in ctx.calculation.catalog['documents']:
        try:ctx.calculation.check_local_source(d);status='ready';reason='ok'
        except Exception as e:status='error';reason=getattr(e,'code',type(e).__name__)
        facts=[f for f in ctx.calculation.catalog['facts']if f['document_id']==d['document_id']]
        rows.append(dict(document_id=d['document_id'],file=status,reason=reason,preparation=','.join(sorted({f['provenance']['status']for f in facts})),publication=d['publication']['precision'],human_reviewed=any(f['provenance']['status']=='human_reviewed'for f in facts)))
    r=ctx.retrieval;p=Path(r['db_path']);m=read_json(Path(str(p)+'.manifest.json'))
    need(p.is_file()and file_sha(p)==m['index_sha256'],'index_hash_mismatch')
    with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True))as con:
        con.execute('PRAGMA query_only=ON');meta=json.loads(con.execute('SELECT payload FROM metadata').fetchone()[0])
    need(canonical(meta)==m['metadata_digest'],'index_metadata_mismatch');need(meta['catalog_digest']==digest(ctx.calculation.catalog),'index_catalog_mismatch')
    need(meta['configuration_signature']==_signature(r['config'],r['lexicon']),'index_configuration_mismatch')
    if meta['kind']=='automatic':
        need(type(r['export_paths'])is dict,'export_resources_required')
        for did,h in meta['export_hashes'].items():need(file_sha(r['export_paths'][did])==h,'extraction_hash_mismatch')
    return dict(documents=rows,index_kind=meta['kind'],index_sha256=m['index_sha256'],ready=all(x['file']=='ready'for x in rows),retrieval_performed=False,model_calls=0)

def restore_registered(ctx,document_id,data):
    """Restore only a missing exact resource in the trusted map; never overwrite."""
    ctx.validate();docs=[d for d in ctx.calculation.catalog['documents']if d['document_id']==document_id]
    need(len(docs)==1,'unknown_document_id');d=docs[0]
    need(type(data)is bytes and len(data)==d['byte_length']and len(data)<=50000000 and data.startswith(b'%PDF-')and hashlib.sha256(data).hexdigest()==d['sha256'],'source_version_mismatch')
    target=Path(ctx.calculation.resources[d['availability']['local_resource_id']]).resolve()
    workspace=ROOT.parents[1]if ROOT.parent.name=='tmp'else ROOT
    need(target.is_relative_to((workspace/'tmp').resolve()),'private_source_path_required')
    if target.exists():
        need(file_sha(target)==d['sha256'],'existing_source_conflict');return 'already_present'
    target.parent.mkdir(parents=True,exist_ok=True);temp=target.parent/('restore13-'+uuid4().hex+'.tmp')
    try:
        with temp.open('xb')as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.link(temp,target)
    finally:
        if temp.exists():temp.unlink()
    return 'restored_exact_version'

def live_fingerprint(ctx):
    # Hash current resources too: missing/changed bytes never revive an earlier answer.
    hashes={}
    paths=list(ctx.calculation.resources.values())+[ctx.retrieval['db_path'],str(ctx.retrieval['db_path'])+'.manifest.json',ROOT/'data/config/local_model.json']+list((ctx.retrieval['export_paths']or {}).values())
    paths+=list(ctx.calculation.file_guards)
    if ctx.config_guard:paths.append(ctx.config_guard[0])
    for p in paths:
        try:hashes[str(p)]=file_sha(p)
        except OSError:hashes[str(p)]='missing'
    return digest(dict(context=ctx.current_identity(),live=hashes))

def financial(source,answers,method,ctx,store,nonce=0):
    need(method in METHODS,'product_method_unsupported');fingerprint=live_fingerprint(ctx)
    intent=dict(kind='financial',source=source,answers=answers,method=method)
    def produce(rid):
        if method=='B':r=execute(source,'B',ctx,answers,run_id=rid)
        elif method=='A':r=execute_a(source,ctx,load_one_shot_model(ROOT/'data/config/local_model.json'),answers,run_id=rid)
        else:r=execute_c(source,ctx,load_agent_model(ROOT/'data/config/local_model.json'),answers,run_id=rid)
        return dict(kind='financial',source=source,answers=answers,result=r)
    return store.run(intent,fingerprint,produce,nonce)

def scenario(source,ctx,store,nonce=0):
    ctx.validate();request=source['request'];financial_source=source.get('financial')
    identity=ctx.identity if ctx.service is None else digest(dict(scenario=ctx.identity,live=live_fingerprint(ctx.service)))
    def produce(rid):
        fin=financial_source if financial_source is not None else own_financial(ctx,rid+'-financial')
        req=dict(request,financial_run_id=fin['run_id']);out=execute_scenario(fin,req,ctx,run_id=rid)
        return dict(kind='scenario',source=dict(request=req),answers=[],result=out)
    return store.run(dict(kind='scenario',source=source),identity,produce,nonce)
