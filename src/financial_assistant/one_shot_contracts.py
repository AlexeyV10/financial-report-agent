"""A selection/Answer envelopes, separate from B/C and monetary contracts."""
from copy import deepcopy
from dataclasses import asdict,dataclass
import math
from .contracts_v2 import need,shape
from .service_contracts import STAGES as B_STAGES,validate_answer
from .calculation_contracts import validate_request

VERSION='kp3-a-answer-0.1'
PROTOCOL='kp3-one-shot-a-0.1'
CHOICE='kp3-a-choice-0.1'
PROMPT='one-shot-financial-selection-v1'
STAGES=['input','catalog_filters','search','fact_resolution','source_validation','model_selection','calculation','result_validation','answer']


@dataclass(frozen=True)
class SelectionLimits:
    timeout_s:float=180
    per_call_s:float=60
    top_k:int=32
    max_output_tokens:int=384
    max_choice_bytes:int=4096
    max_observation_bytes:int=32768

    def validate(self):
        for name,lo,hi in [('top_k',1,32),('max_output_tokens',64,512),('max_choice_bytes',256,8192),('max_observation_bytes',2048,65536)]:
            n=getattr(self,name);need(type(n)is int and lo<=n<=hi,'invalid_selection_limits')
        for n in [self.timeout_s,self.per_call_s]:need(type(n)in {int,float}and math.isfinite(n)and 0<n<=180,'invalid_selection_limits')
        need(self.per_call_s<=self.timeout_s,'invalid_selection_limits');return asdict(self)


def choice_schema(req,pool):
    return dict(type='object',properties=dict(schema_version=dict(const=CHOICE),operation_id=dict(const=req['operation_id']),inputs=dict(type='array',minItems=len(req['inputs']),maxItems=len(req['inputs']),items=dict(type='object',properties=dict(role=dict(type='string',enum=[r['role']for r in req['inputs']]),fact_id=dict(type='string',enum=[f['fact_id']for f in pool])),required=['role','fact_id'],additionalProperties=False))),required=['schema_version','operation_id','inputs'],additionalProperties=False)


def bind_choice(req,pool,choice):
    shape(choice,'schema_version operation_id inputs');need(choice['schema_version']==CHOICE,'invalid_choice_version');need(choice['operation_id']==req['operation_id'],'selection_operation_mismatch')
    rows=choice['inputs'];need(type(rows)is list and len(rows)==len(req['inputs']),'selection_input_count')
    for r in rows:shape(r,'role fact_id');need(type(r['fact_id'])is str and type(r['role'])is str,'invalid_selection_id')
    need(len({r['fact_id']for r in rows})==len(rows),'selection_duplicate_id');need(len({r['role']for r in rows})==len(rows),'selection_duplicate_role')
    facts={f['fact_id']:f for f in pool};need(len(facts)==len(pool),'candidate_id_conflict');refs=[]
    for r in rows:
        need(r['fact_id']in facts,'selection_unknown_id');f=facts[r['fact_id']]
        refs.append(dict(role=r['role'],fact_id=f['fact_id'],document_id=f['document_id'],version_id=f['version_id'],metric_id=f['metric_id'],definition_id=f['definition_id'],period=deepcopy(f['period']),source_unit=dict(currency=f['currency'],scale=f['scale'])))
    selected=deepcopy(req);selected['inputs']=refs;validate_request(selected)
    # Immutable normalized contexts, not evaluator gold: no value/formula/expected is read.
    need(selected==req,'selection_context_mismatch');return selected


def validate_one_shot_answer(a):
    b=deepcopy(a);s=b.pop('selection');b['schema_version']='kp3-answer-0.1';b['model_calls']=0;b['trace']=[t for t in b['trace']if t['stage']!='model_selection'];validate_answer(b)
    need(a['schema_version']==VERSION and a['method']=='A','invalid_one_shot_version');need([t['stage']for t in a['trace']]==STAGES,'incomplete_selection_trace')
    shape(s,'protocol prompt adapter limits model_attempts mock_choices choice choice_valid usage events search_audit primary_searches validation_searches unknown_search_steps observation_digest stop_reason')
    need(s['protocol']==PROTOCOL and s['prompt']==PROMPT,'invalid_selection_protocol')
    calls=[e for e in s['events']if e['kind']=='choice'];real=s['adapter'].get('kind')=='local_llm';need(len(calls)<=1,'multiple_model_choices')
    need(s['model_attempts']==(len(calls)if real else 0)and s['mock_choices']==(0 if real else len(calls)),'choice_attempt_mismatch')
    known=sum(e['chat_requests']or 0 for e in calls);unknown=sum(e['chat_requests']is None for e in calls)
    need(a['model_calls']==(None if unknown else known)and s['usage']['known_chat_requests']==known and s['usage']['unknown_requests']==unknown,'selection_usage_mismatch')
    need(all(e['run_id']==a['run_id']for e in s['events']),'selection_run_mismatch')
    for purpose,key in [('primary','primary_searches'),('validation','validation_searches')]:
        expected=None if purpose in s['unknown_search_steps']else sum(r['purpose']==purpose for r in s['search_audit']);need(s[key]==expected,'search_accounting_mismatch')
    if a['financial_status']=='answered':
        need(s['choice_valid']and len(calls)==1 and s['primary_searches']==1 and s['validation_searches']>=2,'answer_without_single_validated_choice')
        c=s['choice'];shape(c,'schema_version operation_id inputs');r=a['financial_result']
        need(c['schema_version']==CHOICE and c['operation_id']==r['operation_id']and c['inputs']==[dict(role=f['role'],fact_id=f['fact_id'])for f in r['inputs']],'answer_choice_binding_mismatch')
