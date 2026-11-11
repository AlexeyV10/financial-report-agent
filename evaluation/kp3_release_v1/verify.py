"""Read-only release identity/readiness. No financial answer or model generation."""
from pathlib import Path,PurePosixPath
from importlib.metadata import version,PackageNotFoundError
import hashlib,json,platform,re,sqlite3

SCHEMA='kp3-release-candidate-0.1'
REPORT='kp3-release-check-0.1'
PROFILES={'code','B','A','C','UI'}


class ReleaseError(ValueError):
    def __init__(self,code):self.code=code;super().__init__(code)


def need(condition,code):
    if not condition:raise ReleaseError(code)


def unique(pairs):
    out={}
    for k,v in pairs:need(k not in out,'duplicate_json_key');out[k]=v
    return out


def read(path):
    p=Path(path);need(p.is_file(),'file_missing');need(p.stat().st_size<=8000000,'json_size_limit')
    return json.loads(p.read_text(encoding='utf8'),object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ReleaseError('nonfinite_json')))


def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def local(root,name):
    need(type(name)is str and bool(name)and '\\'not in name and ':'not in name,'unsafe_release_path')
    raw=PurePosixPath(name);need(bool(raw.parts)and not raw.is_absolute()and '..'not in raw.parts and name==raw.as_posix()and raw.parts[0]not in {'.git','tmp'},'unsafe_release_path')
    p=(Path(root)/name).resolve();need(p.is_relative_to(Path(root).resolve()),'unsafe_release_path');return p


def shape(obj,keys):need(type(obj)is dict and set(obj)==set(keys.split()),'invalid_release_schema')


def hash_text(value):return type(value)is str and re.fullmatch('[0-9a-f]{64}',value)is not None


def validate(root,m):
    shape(m,'schema_version release_id created_at base_commit scope file_sha256 evaluation resources profiles environment service_inputs limits')
    need(m['schema_version']==SCHEMA and type(m['release_id'])is str and re.fullmatch(r'kp3-rc[0-9]+-[0-9]{4}-[0-9]{2}-[0-9]{2}',m['release_id'])is not None,'invalid_release_version')
    need(type(m['scope'])is dict and m['scope'].get('complete_original_P0')is False and m['scope'].get('unseen_real')==0,'release_scope_overclaim')
    files=m['file_sha256'];need(type(files)is dict and 1<=len(files)<=2000,'invalid_release_files')
    for name,h in files.items():local(root,name);need(hash_text(h),'invalid_release_hash')
    e=m['evaluation'];shape(e,'freeze_path freeze_sha256 raw_manifest_path raw_manifest_sha256 metrics_path metrics_sha256 relation')
    for field in ['freeze','raw_manifest','metrics']:
        name=e[field+'_path'];local(root,name);need(name in files and files[name]==e[field+'_sha256'],'unbound_evaluation_identity')
    resources=m['resources'];need(type(resources)is dict and 1<=len(resources)<=64,'invalid_release_resources')
    for key,row in resources.items():
        shape(row,'sha256 byte_length kind');need(type(key)is str and key.startswith(('pdf:','export:','index:','index_manifest:','model:'))and hash_text(row['sha256'])and type(row['byte_length'])is int and row['byte_length']>0,'invalid_release_resource')
    profiles=m['profiles'];need(type(profiles)is dict and set(profiles)==PROFILES,'invalid_release_profiles')
    for profile,keys in profiles.items():
        need(type(keys)is list and all(type(k)is str for k in keys)and len(keys)==len(set(keys))and set(keys)<=set(resources),'invalid_profile_resources')
        if profile in {'code','B','UI'}:need(not any(k.startswith('model:')for k in keys),'model_required_for_model_free_profile')
    need(profiles['code']==[]and profiles['B']==profiles['UI']and profiles['A']==profiles['C']and set(profiles['B'])<=set(profiles['A']),'inconsistent_release_profiles')
    shape(m['service_inputs'],'catalog dictionary admission bindings checks config lexicon')
    for k in m['service_inputs'].values():need(type(k)is str and k in files,'unbound_service_input');local(root,k)
    shape(m['environment'],'core_python core_sqlite UI');shape(m['environment']['UI'],'python streamlit pandas')
    return m


def verify_files(root,m):
    errors=[]
    for name,h in m['file_sha256'].items():
        p=local(root,name)
        if not p.is_file():errors.append(dict(file=name,reason='release_file_missing'))
        elif sha(p)!=h:errors.append(dict(file=name,reason='release_file_changed'))
    return errors


def verify_resources(m,resources,profile):
    need(profile in PROFILES,'unknown_release_profile');need(type(resources)is dict and set(resources)<=set(m['resources']),'unknown_resource_binding')
    out=[]
    for key in m['profiles'][profile]:
        pin=m['resources'][key];raw=resources.get(key);p=Path(raw)if type(raw)is str and raw else None
        if p is None or not p.is_file():status='resource_missing'
        elif p.stat().st_size!=pin['byte_length']or sha(p)!=pin['sha256']:status='resource_changed'
        else:status='ready'
        out.append(dict(resource_id=key,status=status))
    return out


def bind_context(root,m,context_path,resources):
    from financial_assistant.service_b import load_service_context
    from financial_assistant.product_service import preflight
    cfg=read(context_path)
    for key,name in m['service_inputs'].items():
        value=cfg['retrieval'][key]if key in {'config','lexicon'}else cfg[key]
        need((Path(root)/value).resolve()==local(root,name),'release_context_input_mismatch')
    ctx=load_service_context(context_path)
    need(Path(ctx.retrieval['db_path']).resolve()==Path(resources['index:prepared']).resolve(),'release_index_binding_mismatch')
    for d in ctx.calculation.catalog['documents']:
        actual=ctx.calculation.resources[d['availability']['local_resource_id']]
        need(Path(actual).resolve()==Path(resources['pdf:'+d['document_id']]).resolve(),'release_pdf_binding_mismatch')
    ready=preflight(ctx);need(ready['ready']and ready['index_kind']=='prepared','release_prepared_context_required')
    return ready


def check(root,manifest_path,profile='code',resource_path=None,context_path=None):
    out=dict(schema_version=REPORT,release_id=None,profile=profile,execution_status='error',reason_code='not_checked',code_verified=False,runtime_ready=False,financial_result=None,model_chat_requests=0,resources=[],readiness=None,model_probe=None,environment=dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version),limitations=['Readiness is not a financial answer, new source annotation or model-quality measurement'])
    stage='manifest'
    try:
        need(profile in PROFILES,'unknown_release_profile');m=validate(root,read(manifest_path));out['release_id']=m['release_id'];out['manifest_sha256']=sha(manifest_path)
        errors=verify_files(root,m);out['file_errors']=errors;need(not errors,'release_files_not_intact')
        stage='evaluated_version'
        from kp3_protocol_v1.freeze import verify_freeze,read_raw
        e=m['evaluation'];freeze=local(root,e['freeze_path']);f=verify_freeze(root,freeze)
        need(m['resources']==f['logical_resources'],'release_resource_pins_drift')
        need(all(m['file_sha256'].get(k)==h for k,h in f['file_sha256'].items()),'evaluated_code_relation_changed')
        raw=local(root,e['raw_manifest_path']);rows=read_raw(raw.parent/'raw',freeze,raw)
        need(len(rows)==138,'evaluated_raw_count_changed');out['evaluated_raw_verified']=len(rows);out['code_verified']=True
        if profile=='code':out.update(execution_status='completed',reason_code='code_verified_runtime_not_checked');return out
        stage='resources';need(resource_path is not None,'resource_map_required');resources=read(resource_path);rows=verify_resources(m,resources,profile);out['resources']=rows;need(all(r['status']=='ready'for r in rows),'release_resources_unavailable')
        stage='service_context';need(context_path is not None,'service_context_required');out['readiness']=bind_context(root,m,context_path,resources)
        if profile=='UI':
            stage='ui_environment'
            for package,pin in m['environment']['UI'].items():
                actual=platform.python_version()if package=='python'else version(package);out['environment'][package]=actual;need(actual==pin,'ui_dependency_version_mismatch')
        if profile in {'A','C'}:
            stage='model_probe'
            from financial_assistant.agent_model_v2 import load_agent_model
            out['model_probe']=load_agent_model(Path(root)/'data/config/local_model.json').probe(timeout=3)
        out.update(execution_status='completed',reason_code='ready',runtime_ready=True)
    except Exception as e:
        out.update(execution_status='error',reason_code=getattr(e,'code','dependency_missing'if isinstance(e,PackageNotFoundError)else'release_check_failed'),failed_stage=stage,error_type=type(e).__name__)
    return out
