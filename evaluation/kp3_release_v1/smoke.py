"""Known release bridge checks; gold is consumed AFTER the unchanged product service."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import json
from .verify import read,need

CASE_IDS=['cmp-01','cmp-11','cmp-13','cmp-19','cmp-25','cmp-29','cmp-30','cmp-33','cmp-35','cmp-36','cmp-37','cmp-38','cmp-39','cmp-40']


def call_financial(fn,case,ctx,store):
    # No case/gold/target/expected/overrides object crosses the runtime boundary.
    return fn(deepcopy(case['source']),deepcopy(case.get('answers',[])),'B',ctx,store)


def export_check(store,record):
    exported=json.loads(store.export(record['record_id'],'json'))
    need(exported==record,'release_json_export_mismatch')
    md=store.export(record['record_id'],'markdown').decode('utf8')
    embedded=json.loads(md.split('```json\n',1)[1].rsplit('\n```',1)[0])
    need(embedded==record['payload'],'release_markdown_payload_mismatch')
    need(store.load(record['record_id'])==record,'release_history_mismatch')
    return dict(json_equal=True,markdown_payload_equal=True,history_equal=True)


def run(root,context_path,work_dir):
    from financial_assistant.service_b import load_service_context
    from financial_assistant.product_service import financial,scenario
    from financial_assistant.product_history import RunStore
    from financial_assistant.desktop_presentation import number,unit_label,period_label
    from financial_assistant.scenario_service import load_own_context,ScenarioContext
    from kp3_protocol_v1.evaluator import evaluate_financial,evaluate_scenario
    root=Path(root).resolve();work=Path(work_dir).resolve()if work_dir else None
    need(work is not None and work.is_relative_to(root/'tmp')and work!=root/'tmp'and not work.exists(),'new_private_smoke_dir_required');work.mkdir(parents=True)
    ctx=load_service_context(context_path);store=RunStore(work/'history')
    inputs=read(root/'data/evaluation/kp3_eval_v1/inputs.json');cases={c['case_id']:c for c in inputs['cases']};gold={g['case_id']:g for g in read(root/'evaluation/fixtures/kp3_eval_v1/gold.json')['cases']}
    out=dict(schema_version='kp3-release-smoke-0.1',known_to_developer=True,financial_cases=[],clarifications=[],technical_cases=[],scenario_cases=[],model_chat_requests=0,new_final_comparison=False,new_gold=False)
    for cid in CASE_IDS:
        case=cases[cid];record,reused=call_financial(financial,case,ctx,store);answer=record['payload']['result']
        score=evaluate_financial(case,gold[cid],answer);need(not reused,'release_unexpected_reuse');need(answer['model_calls']==0,'release_unexpected_chat')
        need(call_financial(financial,case,ctx,store)==(record,True),'release_dedup_mismatch')
        export=export_check(store,record);result=answer['financial_result'];display=None
        if result:
            display=dict(value=number(result['display_value']),unit=unit_label(result['result_unit']),periods=[period_label(x['period'])for x in result['inputs']])
            need(Decimal(display['value'].replace('\u00a0','').replace(',','.'))==Decimal(result['display_value']),'release_display_value_mismatch')
        out['financial_cases'].append(dict(case_id=cid,run_id=answer['run_id'],record_id=record['record_id'],matched=score['matched'],score=score,export=export,ui_presentation=display,original_question_preserved=answer['original_question']==record['payload']['source']['form']['original_question'],answer=answer))
    source=dict(kind='text',input_id='rc17-clarification',question='Какая выручка за полный 2024 год?')
    record,_=financial(source,[],'B',ctx,store);a=record['payload']['result'];need(a['execution_status']=='awaiting_clarification'and a['financial_result']is None and a['original_question']==source['question'],'release_clarification_failed');out['clarifications'].append(dict(run_id=a['run_id'],status=a['execution_status'],no_financial_result=True,export=export_check(store,record)))
    cfg=read(context_path);maps=read((root/cfg['resources']).resolve());doc=cases['cmp-01']['source']['form']['fields']['documents'][0]['document_id'];d=next(x for x in ctx.calculation.catalog['documents']if x['document_id']==doc)
    for fault in ['source_missing','index_missing']:
        bad=deepcopy(cfg)
        if fault=='source_missing':
            altered=deepcopy(maps);altered[d['availability']['local_resource_id']]=str(work/'absent-source.pdf');mp=work/'missing-source-map.json';mp.write_text(json.dumps(altered),encoding='utf8');bad['resources']=str(mp)
        else:bad['retrieval']['db_path']=str(work/'absent-index.sqlite')
        path=work/(fault+'-context.json');path.write_text(json.dumps(bad),encoding='utf8');badctx=load_service_context(path);record,_=call_financial(financial,cases['cmp-01'],badctx,store);a=record['payload']['result']
        matched=a['execution_status']=='error'and a['financial_result']is None and a['reason_code']==fault
        out['technical_cases'].append(dict(fault=fault,matched=matched,execution_status=a['execution_status'],reason_code=a['reason_code'],no_financial_result=a['financial_result']is None,assumption_checks=a['assumption_checks'],export=export_check(store,record)))
    for cid in ['scenario-01','scenario-09']:
        c=cases[cid];s=c['source']
        if s['kind']=='scenario':sc=load_own_context(work/cid);source=dict(request=deepcopy(s['request']),financial=None)
        else:
            fin=financial(deepcopy(s['financial_source']),[],'B',ctx,store)[0]['payload']['result'];sc=ScenarioContext(ctx,work/cid)
            source=dict(request=dict(schema_version='kp3-scenario-request-0.1',financial_run_id=fin['run_id'],data_mode='real_source_readiness',decision_at=s['decision_at'],parameters=None),financial=fin)
        record,_=scenario(source,sc,store);a=record['payload']['result'];score=evaluate_scenario(c,gold[cid],a);need(a['model_calls']==0,'release_scenario_chat')
        out['scenario_cases'].append(dict(case_id=cid,matched=score['matched'],score=score,status=a['status'],reason_code=a['reason_code'],export=export_check(store,record),outcome=a))
    out['passed']=all(r['matched']for key in ['financial_cases','technical_cases','scenario_cases']for r in out[key])
    out['counts']=dict(financial_known=len(out['financial_cases']),clarification=1,technical_faults=2,scenario_known=2,unique_financial_numeric=sum(r['answer']['financial_result']is not None for r in out['financial_cases']),new_model_chat=0)
    return out
