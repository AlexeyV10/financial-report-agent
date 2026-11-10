"""Two preregistered own-dev native pinned transport boundaries, no server start/retry."""
from pathlib import Path
from time import perf_counter
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
for p in ['src','tests','evaluation']:sys.path.insert(0,str(ROOT/p))
from kp3_probes_v1.campaign import fixture,source,read,write_new,private_child,require,no_money
from financial_assistant.agent_model_v2 import load_agent_model
from financial_assistant.one_shot_model import load_one_shot_model
from financial_assistant.agent_c import execute_c
from financial_assistant.one_shot_a import execute_a
from financial_assistant.agent_contracts_v2 import AgentLimits
from financial_assistant.one_shot_contracts import SelectionLimits


def declaration():
    return dict(schema_version='kp3-native-boundary-plan-0.1',stage='KP3-15',source='own07_hash_fixture_not_issuer_pdf',methods=['A','C'],server_start=False,automatic_retry=False,model_config='data/config/local_model.json',question='Явная собственная учебная форма.',operation='direct_fact_v1',max_chat_requests=5,max_output_tokens=1920,limits=dict(A=dict(timeout_s=20,per_call_s=5),C=dict(max_calls=4,timeout_s=20,per_call_s=5)),expected=dict(offline='technical error/limit; no financial result; zero chat after failed native setup probe',online='actual pinned dev boundary; retain first outcome, never mock/replay, do not start comparison16'),comparison16_attempts=0)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--declare',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--report',type=Path);p.add_argument('--private',type=Path);a=p.parse_args()
    if a.declare:write_new(a.declare,declaration());return 0
    require(read(a.plan)==declaration(),'native_plan_drift');d=private_child(a.private);require(not d.exists(),'new_native_directory_required');d.mkdir(parents=True);rows=[]
    for method in ['A','C']:
        folder=d/method;folder.mkdir();ctx=fixture(folder);s=source(ctx);adapter=load_one_shot_model(ROOT/'data/config/local_model.json')if method=='A'else load_agent_model(ROOT/'data/config/local_model.json');t=perf_counter()
        answer=execute_a(s,ctx,adapter,limits=SelectionLimits(timeout_s=20,per_call_s=5))if method=='A'else execute_c(s,ctx,adapter,limits=AgentLimits(max_calls=4,timeout_s=20,per_call_s=5));elapsed=round((perf_counter()-t)*1000,3)
        usage=answer['selection'if method=='A'else'agent']['usage'];require(answer['method']==method,'native method fallback')
        if answer['execution_status']in {'error','limit'}:no_money(answer)
        write_new(a.report.parent/('native-'+method+'.json'),answer);rows.append(dict(method=method,adapter_kind='native_pinned_local_llm_not_mock',execution_status=answer['execution_status'],reason_code=answer['reason_code'],model_calls=answer['model_calls'],usage=usage,elapsed_ms=elapsed,raw='native-'+method+'.json'))
    known=sum(r['usage']['known_chat_requests']for r in rows);require(known<=5,'native_budget_exceeded');report=dict(stage='KP3-15',declared=2,executed=2,rows=rows,known_chat_requests=known,unknown_requests=sum(r['usage'].get('unknown_requests',0)for r in rows),server_started=False,comparison16_attempts=0,model_quality='not_measured');write_new(a.report,report);print(json.dumps(report));return 0


if __name__=='__main__':raise SystemExit(main())
