"""Exclusive durable attempts, strict identities and conservative actual/unknown budgets."""
from contextlib import contextmanager
from pathlib import Path
import json,os,uuid
from kp3_protocol_v1.common import read,require,digest,ident


def atomic_new(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.parent/('.pending-'+uuid.uuid4().hex)
    try:
        with tmp.open('x',encoding='utf8',newline='\n')as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.link(tmp,p)
    finally:
        if tmp.exists():tmp.unlink()


@contextmanager
def run_lock(path):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a+b')as f:
        if p.stat().st_size==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)


def validate_order(order):
    ids=[]
    for r in order:
        require(set(r)=={'attempt_id','case_id','method','phase'},'invalid_planned_slot');ident(r['attempt_id']);ident(r['case_id']);require(r['method']in {'B','A','C'}and r['phase']in {'primary','warm_repeat'},'invalid_method_phase');ids.append(r['attempt_id'])
    require(len(ids)==len(set(ids)),'duplicate_attempt_id')


def run_id(manifest_sha,slot):return 'eval16-'+manifest_sha[:16]+'-'+slot['attempt_id']


def validate_observation(row,slot,manifest_sha):
    require(type(row)is dict and set(row)=={'schema_version','attempt_id','case_id','method','phase','source','answer','measurement'},'invalid_observation')
    require(row['schema_version']=='kp3-observation-0.1'and row['source']=='actual','nonactual_raw');require(all(row[k]==v for k,v in slot.items()),'slot_identity_mismatch');m=row['measurement'];require(m['run_manifest_sha256']==manifest_sha,'run_manifest_mismatch');require(m['cold_warm']in {'cold','warm','unknown'},'invalid_model_state')
    if row['answer']is not None:require(row['answer']['method']==slot['method']and row['answer']['run_id']==run_id(manifest_sha,slot),'answer_identity_mismatch')


def budget_charge(row):
    method=row['method'];cap=0 if method=='B'else 1 if method=='A'else 8;a=row['answer'];known=0;unknown=0;tokens=0;token_unknown=False
    if type(a)is dict:
        if method=='B':require(a['model_calls']==0,'B_has_model_calls')
        else:
            usage=a['selection'if method=='A'else'agent']['usage'];known=usage['known_chat_requests'];unknown=usage['unknown_requests']
            if method=='A':tokens=usage['output_tokens']or 0;token_unknown=known>0 and usage['output_tokens']is None
            else:tokens=usage['known_output_tokens'];token_unknown=usage['unknown_usage']>0
            require(type(known)is int and type(unknown)is int and known>=0 and unknown>=0 and known+unknown<=cap,'invalid_usage_budget')
            require(a['model_calls']==(None if unknown else known),'unknown_request_lost')
    elif method!='B':unknown=1;token_unknown=True
    require(type(tokens)is int and tokens>=0 and tokens<=cap*384,'invalid_token_budget')
    reserved=cap if unknown or token_unknown else known
    ms=row['measurement']['elapsed_ms'];require(ms is None or type(ms)in {int,float}and ms>=0,'invalid_elapsed')
    return dict(known_chat_requests=known,unknown_requests=unknown,reserved_chat_requests=reserved,known_output_tokens=tokens,reserved_output_tokens=cap*384 if unknown or token_unknown else tokens,serial_wall_s=180 if ms is None else ms/1000)


def budget_total(rows):
    charges=[budget_charge(r)for r in rows];return {key:sum(c[key]for c in charges)for key in ['known_chat_requests','unknown_requests','reserved_chat_requests','known_output_tokens','reserved_output_tokens','serial_wall_s']}


def next_slot(order,rows):
    validate_order(order);seen={r['attempt_id']:r for r in rows};require(len(seen)==len(rows),'duplicate_observation');require(set(seen)<={s['attempt_id']for s in order},'unknown_attempt');missing=False;result=None
    for slot in order:
        if slot['attempt_id']not in seen:
            if result is None:result=slot
            missing=True
        else:require(not missing,'noncontiguous_attempts')
    return result
