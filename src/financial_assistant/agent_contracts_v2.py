"""Explicit C envelope and bounded protocol; does not change Answer0.1 or money0.3."""
from copy import deepcopy
from dataclasses import asdict,dataclass
import math
from .contracts_v2 import need,shape
from .service_contracts import validate_answer

VERSION='kp3-answer-0.2'
PROTOCOL='kp3-agent-0.2'
PROMPT='bounded-financial-tools-v2'


@dataclass(frozen=True)
class AgentLimits:
    max_calls:int=8
    timeout_s:float=180
    per_call_s:float=60
    max_search_results:int=32
    max_output_tokens:int=384
    max_action_bytes:int=4096
    max_observation_bytes:int=32768
    max_tool_bytes:int=8192

    def validate(self):
        for key,lo,hi in [('max_calls',2,12),('max_search_results',1,32),('max_output_tokens',64,512),('max_action_bytes',256,8192),('max_observation_bytes',2048,65536),('max_tool_bytes',512,16384)]:
            value=getattr(self,key);need(type(value)is int and lo<=value<=hi,'invalid_agent_limits')
        for value in [self.timeout_s,self.per_call_s]:need(type(value)in {int,float}and math.isfinite(value)and 0<value<=180,'invalid_agent_limits')
        need(self.per_call_s<=self.timeout_s,'invalid_agent_limits')
        return asdict(self)


def validate_agent_answer(a):
    # Validation-only adapter: discard usage in a COPY to reuse immutable0.1 financial invariants.
    # The persisted0.2 record always retains actual C counts, not this temporary projection.
    b=deepcopy(a);agent=b.pop('agent');b['schema_version']='kp3-answer-0.1';b['model_calls']=0
    validate_answer(b);need(a['schema_version']==VERSION and a['method']=='C','invalid_agent_version')
    shape(agent,'protocol prompt adapter limits decisions model_attempts mock_decisions usage events stop_reason finished receipt_id')
    need(agent['protocol']==PROTOCOL and agent['prompt']==PROMPT,'invalid_agent_protocol')
    calls=[e for e in agent['events']if e['kind']=='decision']
    need(agent['decisions']==len(calls)and len(calls)<=agent['limits'].get('max_calls',0),'decision_count_mismatch')
    real=[e for e in calls if agent['adapter']['kind']=='local_llm']
    known=sum(e['chat_requests']or 0 for e in real);unknown=sum(e['chat_requests']is None for e in real)
    need(a['model_calls']==(None if unknown else known),'chat_count_mismatch')
    need(agent['usage']['known_chat_requests']==known and agent['usage']['unknown_requests']==unknown,'request_usage_mismatch')
    need(agent['model_attempts']==len(real),'attempt_count_mismatch')
    need(agent['mock_decisions']==(len(calls)if agent['adapter']['kind']=='mock'else 0),'mock_count_mismatch')
    need(all(e['run_id']==a['run_id']for e in agent['events']),'event_run_mismatch')
    if agent['finished']:
        finished=[e for e in agent['events']if e['kind']=='tool'and e['tool']=='finish']
        receipts=[e for e in agent['events']if e['kind']=='receipt']
        need(finished and receipts and finished[-1]['result'].get('validated')is True and finished[-1]['arguments']['receipt_id']==receipts[-1]['receipt_id']==agent['receipt_id'],'finish_receipt_mismatch')
    if a['financial_result']is not None:need(agent['finished']and agent['receipt_id']is not None,'unpublished_calculation')
    if not agent['finished']:need(a['financial_status']is None,'unfinished_financial_status')
