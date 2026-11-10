"""Protocol14 audit and declared dev controls only; NEVER run comparison40 methods."""
from copy import deepcopy
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'));sys.path.insert(0,str(ROOT/'src'))
from kp3_protocol_v1.common import read,write_new,require,digest
from kp3_protocol_v1.suite import validate_suite
from kp3_protocol_v1.controls import prior_controls
from kp3_protocol_v1.evaluator import evaluate_financial,evaluate_parser
from kp3_protocol_v1.freeze import runtime_isolation

def paths(draft=None):
    return {k:(draft/(k+'.json')if draft else ROOT/v)for k,v in dict(inputs='data/evaluation/kp3_eval_v1/inputs.json',gold='evaluation/fixtures/kp3_eval_v1/gold.json',protocol='evaluation/protocols/kp3_eval_v1/protocol.json',search_tasks='data/evaluation/kp3_eval_v1/search_tasks.json',retrieval_gold='evaluation/fixtures/kp3_eval_v1/retrieval_gold.json').items()}

def run(draft=None,dev_smoke=False):
    p=paths(draft);bundle={k:read(v)for k,v in p.items()};inputs=bundle['inputs'];gold=bundle['gold'];report=dict(stage='KP3-14',model_calls=0,final_comparison_method_attempts=0,known_to_developer=True,audit=validate_suite(inputs,gold,bundle['protocol']),isolation=runtime_isolation(ROOT),binding_checks=[],parser_controls=[],prior_actual_controls=[],new_own_calculator_controls=[])
    require(bundle['retrieval_gold']['tasks_digest']==digest(bundle['search_tasks']),'retrieval_gold_binding_mismatch')
    require(len(bundle['retrieval_gold']['queries'])==bundle['protocol']['retrieval_unique_queries'],'retrieval_denominator_mismatch')
    from financial_assistant.agent_contracts_v2 import AgentLimits
    from financial_assistant.one_shot_contracts import SelectionLimits
    require(bundle['protocol']['limits']['C']==AgentLimits().validate()and bundle['protocol']['limits']['A']==SelectionLimits().validate(),'protocol_runtime_limits_drift')
    cfg=read(ROOT/'data/config/local_model.json');require(all(cfg[k]==v for k,v in bundle['protocol']['model'].items()),'protocol_model_pin_drift');require(bundle['protocol']['max_model_requests']==46+46*AgentLimits().max_calls==414,'chat_budget_mismatch')
    from financial_assistant.russian_input import parse_form,parse_text
    from financial_assistant.input_binding import resolve_input
    from financial_assistant.calculation_contracts import validate_request
    cat=read(ROOT/'data/catalogs/kp3_corpus_v1/runtime_catalog.json');dictionary=read(ROOT/'data/dictionaries/kp3_finance_v1/definitions.json');gs={g['case_id']:g for g in gold['cases']}
    for case in inputs['cases']:
        g=gs[case['case_id']]
        if case['suite']=='financial'and case['target']=='service':
            binding=resolve_input(parse_form(case['source']['form'],cat),cat,dictionary)
            expected_status=g['expected']['request_status']if g['phase']=='catalog_filters'else'resolved'
            require(binding['status']==expected_status,(case['case_id'],binding['status'],binding['reason_code'],expected_status))
            if g['phase']=='catalog_filters':require(binding['reason_code']==g['expected']['reason_code'],'binder_reason_changed')
            if g['result']is not None:
                req=binding['request'];refs=[dict(role=f['role'],**{k:f[k]for k in ['fact_id','document_id','version_id','metric_id','definition_id','period']},source_unit=f['source_unit'])for f in g['inputs']];require(req['inputs']==refs,'independent_expected_context_mismatch');require(binding['normalized_input']['fields']==g['intent'],'hand_intent_mismatch')
            report['binding_checks'].append(dict(case_id=case['case_id'],binding_status=binding['status'],matched=True,financial_answer_computed=False))
        elif case['suite']=='financial':validate_request(case['source']['request'])
        elif case['suite']=='interface':
            b=resolve_input(parse_text(case['source']['question'],cat,case['case_id']),cat,dictionary);r=evaluate_parser(case,g,b);require(r['matched'],(case['case_id'],r,b['status'],b['reason_code'],b['normalized_input']['fields']));report['parser_controls'].append(r)
    for row in prior_controls(ROOT,inputs,gold):
        score=evaluate_financial(row['case'],row['gold'],row['answer']);require(score['matched'],score);report['prior_actual_controls'].append(dict(origin=row['origin'],run_id=row['answer']['run_id'],method=row['answer']['method'],score=score,new_model_calls=0))
    if dev_smoke:
        #Exactly two predeclared method controls, not B/A/C comparison cases.
        from financial_assistant.fact_admission import load_context
        from financial_assistant.financial_calculator import calculate
        ctx=load_context(ROOT/'data/catalogs/kp3_calculator_dev_v1/runtime_catalog.json',ROOT/'data/dictionaries/kp3_finance_v1/definitions.json',ROOT/'data/calculation/kp3_calculator_v1/synthetic_admission.json')
        for cid in ['dev-03','dev-15']:
            c=next(c for c in inputs['cases']if c['case_id']==cid);req=deepcopy(c['source']['request']);answer=calculate(ctx,req,req['request_id']);score=evaluate_financial(c,gs[cid],answer);require(score['matched'],score);report['new_own_calculator_controls'].append(dict(case_id=cid,score=score,model_calls=0))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--draft',type=Path);p.add_argument('--report',type=Path,required=True);p.add_argument('--dev-smoke',action='store_true');a=p.parse_args();r=run(a.draft,a.dev_smoke);write_new(a.report,r);print(json.dumps(dict(audit=r['audit'],binding_checks=len(r['binding_checks']),parser_controls=len(r['parser_controls']),prior_actual_controls=len(r['prior_actual_controls']),new_own_calculator_controls=len(r['new_own_calculator_controls']),model_calls=0,final_method_attempts=0),ensure_ascii=False))
