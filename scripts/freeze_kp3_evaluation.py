"""Verify actual local resources/model pins and seal a NEW evaluation manifest before answers."""
from pathlib import Path
import argparse,json,platform,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1];WORKSPACE=ROOT.parents[1]if ROOT.parent.name=='tmp'else ROOT;sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_protocol_v1.common import read,write_new,file_sha,require
from kp3_protocol_v1.freeze import create_freeze,verify_freeze
from kp3_protocol_v1.suite import validate_suite

def inventory(resources,exports,index_dir,model_dir,model_exe):
    cat=read(ROOT/'data/catalogs/kp3_corpus_v1/runtime_catalog.json');local=read(resources);xp=read(exports);mapping={};descriptors={};environments=[]
    def bind(key,path,kind,expected=None,size=None):
        p=Path(path).resolve();require(p.is_file(),'resource_missing:'+key);h=file_sha(p);require(expected is None or expected==h,'resource_sha_mismatch:'+key);require(size is None or size==p.stat().st_size,'resource_size_mismatch:'+key);mapping[key]=str(p);descriptors[key]=dict(kind=kind,sha256=h,byte_length=p.stat().st_size)
    for doc in cat['documents']:
        bind('pdf:'+doc['document_id'],local[doc['availability']['local_resource_id']],'exact_primary_pdf',doc['sha256'],doc['byte_length']);export=Path(xp[doc['document_id']]);data=read(export,20000000);require(data['document_sha256']==doc['sha256'],'export_source_mismatch');environments.append(data['environment']);bind('export:'+doc['document_id'],export,'extraction_export')
    cfg=read(ROOT/'data/extraction/kp3_pdf_v1/config.json');expected_env=dict(python=cfg['worker_python'],pdfplumber=cfg['pdfplumber'],pdfminer_six=cfg['pdfminer_six']);require(all(e==expected_env for e in environments),'worker_environment_mismatch')
    for kind in ['prepared','automatic']:
        p=Path(index_dir)/(kind+'.sqlite');sidecar=read(Path(str(p)+'.manifest.json'));bind('index:'+kind,p,'retrieval_'+kind,sidecar['index_sha256']);bind('index_manifest:'+kind,Path(str(p)+'.manifest.json'),'retrieval_manifest')
    model=read(ROOT/'data/config/local_model.json');require(model['cloud_enabled']is False and model['endpoint']=='http://127.0.0.1:11435','model_endpoint_changed');bind('model:server',model_exe,'existing_ollama_executable',model['executable_sha256']);manifest=Path(model_dir)/'manifests/registry.ollama.ai/library/qwen3/4b';m=read(manifest);bind('model:tag_manifest',manifest,'ollama_tag_manifest')
    for row in [m['config'],*m['layers']]:
        h=row['digest'].removeprefix('sha256:');require(len(h)==64 and all(c in '0123456789abcdef'for c in h),'invalid_model_blob_digest');bind('model:blob:'+h,Path(model_dir)/'blobs'/('sha256-'+h),row['mediaType'],h,row['size'])
    require('model:blob:'+model['model_digest']in mapping or descriptors['model:tag_manifest']['sha256']==model['model_digest'],'pinned_model_digest_unresolved')
    return dict(schema_version='kp3-local-freeze-resources-0.1',descriptors=descriptors,resources=mapping,environment=dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version,worker=expected_env),new_downloads=0,model_calls=0)

def freeze_files():
    files=set()
    for parent in ['src','scripts','app_kp3','evaluation/kp3_protocol_v1']:
        files.update(p.relative_to(ROOT).as_posix()for p in(ROOT/parent).rglob('*.py'))
    for parent in ['data/catalogs/kp3_corpus_v1','data/catalogs/kp3_calculator_dev_v1','data/dictionaries/kp3_finance_v1','data/calculation/kp3_calculator_v1','data/scenarios/kp3_scenario_v1','data/extraction/kp3_pdf_v1','data/evaluation/kp3_eval_v1','evaluation/fixtures/kp3_eval_v1']:
        files.update(p.relative_to(ROOT).as_posix()for p in(ROOT/parent).rglob('*')if p.is_file())
    files.update(['data/config/local_model.json','evaluation/reference/kp3_calculator_v1/oracle.py','evaluation/reference/kp3_scenario_v1/oracle.py','evaluation/kp3_05_2026-11-09/source-checks.json','evaluation/kp3_13_2026-11-10/ui-runs.json','evaluation/kp3_14_2026-11-10/control-export13.md','docs/kp3/evaluation_protocol_v1.md','tests/test_kp3_evaluation.py'])
    files.update(p.relative_to(ROOT).as_posix()for p in(ROOT/'evaluation/protocols/kp3_eval_v1').glob('*.json')if p.name!='freeze-manifest.json')
    return sorted(files)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resources',type=Path,required=True);p.add_argument('--exports',type=Path,required=True);p.add_argument('--index-dir',type=Path,required=True);p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--model-exe',type=Path,required=True);p.add_argument('--inventory-output',type=Path,required=True);p.add_argument('--seal',action='store_true');a=p.parse_args()
    info=inventory(a.resources,a.exports,a.index_dir,a.model_dir,a.model_exe);write_new(a.inventory_output,info)
    if a.seal:
        protocol='evaluation/protocols/kp3_eval_v1/protocol.json';inputs='data/evaluation/kp3_eval_v1/inputs.json';gold='evaluation/fixtures/kp3_eval_v1/gold.json';validate_suite(read(ROOT/inputs),read(ROOT/gold),read(ROOT/protocol));target=ROOT/'evaluation/protocols/kp3_eval_v1/freeze-manifest.json';m=create_freeze(ROOT,target,freeze_files(),info['descriptors'],protocol,inputs,gold);verify_freeze(ROOT,target);print(json.dumps(dict(freeze_sha256=file_sha(target),files=len(m['file_sha256']),resources=len(info['resources']),model_calls=0,final_method_attempts=0)))
    else:print(json.dumps(dict(resources=len(info['resources']),environment=info['environment'],new_downloads=0,model_calls=0)))
