"""Frozen methods receive only source/answers. No evaluator, gold, target or overrides imported."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter
import hashlib,json,os,platform,sqlite3,sys
from kp3_protocol_v1.common import read,require,digest,file_sha,write_new
from kp3_protocol_v1.freeze import verify_freeze
from .ledger import atomic_new,run_lock,run_id,validate_observation,budget_total,next_slot

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.service_b import load_service_context,ServiceContext,execute
from financial_assistant.agent_c import execute_c
from financial_assistant.one_shot_a import execute_a
from financial_assistant.agent_model_v2 import load_agent_model
from financial_assistant.one_shot_model import load_one_shot_model
from financial_assistant.agent_contracts_v2 import AgentLimits,validate_agent_answer
from financial_assistant.one_shot_contracts import SelectionLimits,validate_one_shot_answer
from financial_assistant.service_contracts import validate_answer
from financial_assistant.local_model import local_json
from financial_assistant.agent import bounded

FREEZE='evaluation/protocols/kp3_eval_v1/freeze-manifest.json'
FROZEN_SHA='072a1caf92423d2e41ae12625cc485d81f0bc3c321c3cce5cbb1db663bcf1fbe'
EXTRA=['evaluation/kp3_run_v1/__init__.py','evaluation/kp3_run_v1/ledger.py','evaluation/kp3_run_v1/runtime.py','evaluation/kp3_run_v1/supplement.py','scripts/run_kp3_comparison.py','scripts/collect_kp3_supplement.py','tests/test_comparison_runner16.py']


def private(path):
    p=Path(path).resolve();require(p.is_relative_to((ROOT/'tmp').resolve())and p!=(ROOT/'tmp').resolve(),'private_run_path_required');return p
def now():return datetime.now(timezone.utc).isoformat()
def model_state():
    try:
        result=local_json('/api/ps',timeout=2);models=result.get('models',[]);loaded=any(m.get('name')=='qwen3:4b'for m in models)
        return dict(cold_warm='warm'if loaded else'cold',source='actual_loopback_api_ps',loaded_model_names=[m.get('name')for m in models])
    except Exception as e:return dict(cold_warm='unknown',source='api_ps_failed',reason_code=getattr(e,'code',type(e).__name__))


def prepare(context_path,resources_path,private_dir,manifest_path):
    t=private(private_dir);require(not t.exists(),'new_private_run_required');require(file_sha(ROOT/FREEZE)==FROZEN_SHA,'wrong_freeze');f=verify_freeze(ROOT,ROOT/FREEZE,read(resources_path));protocol=read(ROOT/f['protocol_path']);inputs=read(ROOT/f['inputs_path']);require(len(protocol['order'])==138,'wrong_denominator');require(protocol['limits']['C']==AgentLimits().validate()and protocol['limits']['A']==SelectionLimits().validate(),'runtime_limits_drift')
    ctx=load_service_context(context_path);ctx.validate();t.mkdir(parents=True);cfg=read(context_path);guard_paths=[context_path,resources_path,ROOT/cfg['resources']]
    manifest=dict(schema_version='kp3-run-manifest-0.1',run_name='kp3-16-known-corpus-first-v1',created_at=now(),source_base_commit='f22395940e958e89f0465fb087554dbe47aba167',freeze_path=FREEZE,freeze_sha256=FROZEN_SHA,runner_file_sha256={p:file_sha(ROOT/p)for p in EXTRA},setup_file_sha256={str(Path(p).relative_to(ROOT)):file_sha(p)for p in guard_paths},logical_resources=f['logical_resources'],order=protocol['order'],order_digest=digest(protocol['order']),suite_digest=digest(inputs),budget=protocol['budget'],limits=protocol['limits'],private_run_dir=t.relative_to(ROOT).as_posix(),context_path=Path(context_path).relative_to(ROOT).as_posix(),resources_path=Path(resources_path).relative_to(ROOT).as_posix(),environment=dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version,platform=platform.platform(),processor=platform.processor()),method_input_policy='Only source/answers; registered native methods. No gold/target/profile/fault overrides.',resume_policy='Exclusive claim before invocation; existing result recovered, otherwise interrupted unknown; never rerun a claimed slot',latency_policy='perf_counter around full registered method invocation, excluding api_ps/claim/raw serialization; actual stage elapsed retained; setup resource hashing separately',cold_warm_policy='Actual api_ps before each attempt, or unknown; phase label never used as evidence of model load',new_models=0,new_packages=0,reserved_unseen_real=0)
    write_new(manifest_path,manifest);return manifest


def validate_manifest(path):
    m=read(path);require(m['schema_version']=='kp3-run-manifest-0.1'and m['freeze_sha256']==file_sha(ROOT/FREEZE)==FROZEN_SHA,'manifest_freeze_changed')
    for name,h in {**m['runner_file_sha256'],**m['setup_file_sha256']}.items():require(file_sha(ROOT/name)==h,'run_dependency_changed:'+name)
    freeze=verify_freeze(ROOT,ROOT/FREEZE,read(ROOT/m['resources_path']));inputs=read(ROOT/freeze['inputs_path']);protocol=read(ROOT/freeze['protocol_path']);require(m['order']==protocol['order']and m['suite_digest']==digest(inputs),'run_order_or_inputs_changed');return m,inputs


def rows_from(directory,order,h):
    p=Path(directory);slots={s['attempt_id']:s for s in order};rows=[]
    if not p.exists():return rows
    for f in sorted(p.glob('*.json')):
        require(f.stem in slots,'unknown_raw_file');r=read(f);validate_observation(r,slots[f.stem],h);rows.append(r)
    next_slot(order,rows);return rows


def execute_attempt(slot,case,ctx,rid):
    source=deepcopy(case['source']);answers=deepcopy(case['answers']);method=slot['method']
    if method=='B':return bounded(execute,(source,'B',ctx,answers,rid),180)
    if method=='A':return execute_a(source,ctx,load_one_shot_model(ROOT/'data/config/local_model.json'),answers=answers,run_id=rid)
    if method=='C':return execute_c(source,ctx,load_agent_model(ROOT/'data/config/local_model.json'),answers=answers,run_id=rid)
    raise ValueError('unregistered_method')


def recover_saved(path,slot,case,rid):
    if not path.is_file():return None
    try:
        a=read(path);require(a['run_id']==rid and a['method']==slot['method'],'saved_identity_mismatch');require(a['source_input_digest']==digest(dict(source=case['source'],answers=case['answers'])),'saved_source_mismatch');{'B':validate_answer,'A':validate_one_shot_answer,'C':validate_agent_answer}[slot['method']](a);return a
    except (ValueError,KeyError,TypeError):return None


def run(manifest_path,raw_dir,progress_path):
    m,inputs=validate_manifest(manifest_path);h=file_sha(manifest_path);t=private(ROOT/m['private_run_dir']);raw=Path(raw_dir);raw.mkdir(parents=True,exist_ok=True);cases={c['case_id']:c for c in inputs['cases']};base=load_service_context(ROOT/m['context_path']);completed=[]
    with run_lock(t/'runner.lock'):
        completed=rows_from(raw,m['order'],h)
        for slot in m['order']:
            if any(r['attempt_id']==slot['attempt_id']for r in completed):continue
            budget=budget_total(completed);require(budget['reserved_chat_requests']<=m['budget']['max_chat_requests']and budget['reserved_output_tokens']<=m['budget']['max_output_tokens']and budget['serial_wall_s']<=m['budget']['max_serial_wall_s'],'declared_budget_exhausted')
            rid=run_id(h,slot);case=cases[slot['case_id']];run_dir=t/'service-runs'/slot['attempt_id'];ctx=ServiceContext(base.calculation,base.retrieval,run_dir,base.config_guard);saved=run_dir/(hashlib.sha256(rid.encode()).hexdigest()+'.json');claim=t/'claims'/(slot['attempt_id']+'.json');answer=None;error=None;elapsed=None;recovered=claim.exists();state=dict(cold_warm='unknown',source='interrupted_attempt_not_reprobed');started=None
            if recovered:
                c=read(claim);require(c['run_manifest_sha256']==h and c['slot']==slot and c['run_id']==rid,'claim_identity_changed');started=c['started_at'];answer=recover_saved(saved,slot,case,rid);error=None if answer is not None else'interrupted_unknown_no_retry'
            else:
                state=model_state();started=now();atomic_new(claim,dict(schema_version='kp3-attempt-claim-0.1',run_manifest_sha256=h,slot=slot,run_id=rid,source_digest=digest(dict(source=case['source'],answers=case['answers'])),started_at=started,model_state=state));clock=perf_counter()
                try:answer=execute_attempt(slot,case,ctx,rid)
                except Exception as e:error=getattr(e,'code',type(e).__name__);answer=recover_saved(saved,slot,case,rid)
                elapsed=round((perf_counter()-clock)*1000,4)
            row=dict(schema_version='kp3-observation-0.1',**slot,source='actual',answer=answer,measurement=dict(run_manifest_sha256=h,started_at=started,finished_at=now(),elapsed_ms=elapsed,cold_warm=state['cold_warm'],model_state_observation=state,runner_status='recovered_first_attempt'if recovered and answer is not None else'interrupted_unknown'if recovered else'completed'if error is None else'runner_error',runner_error=error,reexecuted=False))
            validate_observation(row,slot,h);atomic_new(raw/(slot['attempt_id']+'.json'),row);completed.append(row);budget=budget_total(completed);progress=dict(completed=len(completed),planned=len(m['order']),last_slot=slot,last_execution=answer.get('execution_status')if isinstance(answer,dict)else None,last_reason=answer.get('reason_code')if isinstance(answer,dict)else error,budget=budget)
            Path(progress_path).write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(progress,ensure_ascii=False),flush=True)
        require(next_slot(m['order'],completed)is None,'attempts_missing')
    return dict(completed=len(completed),planned=len(m['order']),budget=budget_total(completed),new_execution_on_resume=sum(r['measurement']['reexecuted']for r in completed))
