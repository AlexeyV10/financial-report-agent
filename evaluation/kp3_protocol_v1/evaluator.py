"""Offline grading of existing registered typed answers and fixed exports. No production imports."""
from copy import deepcopy
from decimal import Decimal
import json,math
from .common import exact,require,digest,ProtocolError

BASE='schema_version run_id task_id method execution_status request_status financial_status reason_code original_question normalized_input clarifications financial_result outcome assumption_checks unfulfilled_requests retrieval trace context_digest source_input_digest saved_run model_calls'
RESULT='calculation_schema_version operation_id formula formula_version request admission_context inputs sources intermediates exact_result display_value result_unit rounding precision_note warnings retrieval_resolution'
SCHEMAS={'B':'kp3-answer-0.1','C':'kp3-answer-0.2','A':'kp3-a-answer-0.1'}
STAGES=['input','catalog_filters','search','fact_resolution','source_validation','calculation','result_validation','answer']
MODEL=dict(model='qwen3:4b',model_digest='359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7',server_version='0.40.15')

def usage(a):
    m=a.get('method');calls=a.get('model_calls');require(calls is None or type(calls)is int and calls>=0,'invalid_chat_count');rows=[];details={};unknown=0
    if m=='B':require(calls==0,'B_has_model_calls')
    elif m in {'A','C'}:
        details=a['selection'if m=='A'else'agent'];require(details['adapter']['kind']=='local_llm','mock_or_replay_not_actual');require(all(details['adapter'].get(k)==v for k,v in MODEL.items()),'wrong_model_pin');require(details['adapter'].get('prompt')==('one-shot-financial-selection-v1'if m=='A'else'bounded-financial-tools-v2'),'wrong_prompt_pin');event='choice'if m=='A'else'decision';rows=[x for x in details['events']if x['kind']==event];require(all(x['chat_requests']is None or type(x['chat_requests'])is int and x['chat_requests']==1 for x in rows),'invalid_event_chat_count');known=sum(x['chat_requests']or 0 for x in rows);unknown=sum(x['chat_requests']is None for x in rows);require(calls==(None if unknown else known),'usage_event_mismatch');require(m!='A'or len(rows)<=1,'multiple_A_choices')
        require(details['usage']['known_chat_requests']==known and details['usage']['unknown_requests']==unknown,'usage_totals_mismatch')
    return dict(chat_requests=calls,unknown_requests=unknown,usage=deepcopy(details.get('usage')),adapter=deepcopy(details.get('adapter')))

def evaluate_financial(case,gold,answer):
    errors=[];a=answer;expected=gold['expected'];claim_matches=[];actual_claims=0
    def check(ok,code):
        if not ok:errors.append(code)
    try:
        if case['target']=='calculator_v03':
            require(a['schema_version']=='0.3','wrong_calculation_schema');method='calculation_v03';actual=dict(execution_status=a['execution_status'],request_status='resolved',financial_status=a['financial_status'],reason_code=a['reason_code']);checks=[];unfulfilled=[];u=dict(chat_requests=0,unknown_requests=0,usage=None,adapter=None)
        else:
            method=a['method'];require(method in SCHEMAS,'unregistered_method');exact(a,BASE+(' agent'if method=='C'else' selection'if method=='A'else''));require(a['schema_version']==SCHEMAS[method],'wrong_answer_schema');require(a['task_id']==a['run_id'],'task_run_mismatch');u=usage(a)
            actual={k:a[k]for k in expected};checks=a['assumption_checks'];unfulfilled=a['unfulfilled_requests'];source=case['source'];q=source['question']if source['kind']=='text'else source['form']['original_question'];check(a['original_question']==q,'question_changed');check(a['source_input_digest']==digest(dict(source=source,answers=case['answers'])),'input_digest_mismatch');check(a['normalized_input']is None or a['normalized_input']['original_question']==q,'normalized_question_changed')
            check(all(t['run_id']==a['run_id']and t['status']in {'completed','blocked','skipped','error','awaiting_clarification'}and type(t['elapsed_ms'])in {int,float}and math.isfinite(t['elapsed_ms'])and t['elapsed_ms']>=0 for t in a['trace']),'trace_invalid')
            stages=STAGES[:5]+['model_selection']+STAGES[5:]if method=='A'else STAGES
            check([t['stage']for t in a['trace']]==stages,'trace_stage_order_mismatch')
            if a['normalized_input']is not None:check(a['normalized_input']['fields']==gold['intent'],'normalized_intent_mismatch')
            check(a['outcome']is None or a['outcome']['financial_result']==a['financial_result']and a['outcome']['run_id']==a['run_id'],'outcome_mismatch')
            if a['normalized_input']is not None:
                check(a['normalized_input']['input_kind']==source['kind'],'input_kind_changed')
                check(a['normalized_input']['raw_fields']==(source['form']['fields']if source['kind']=='form'else None),'raw_fields_changed')
        check(actual==expected,'status_or_reason_mismatch');r=a['financial_result'];check(checks==gold['assumption_checks'],'assumption_check_mismatch');check(unfulfilled==gold['unfulfilled_requests'],'unfulfilled_lost')
        if case['target']=='service'and actual==expected:
            if gold['phase']=='answer':check(all(t['status']=='completed'for t in a['trace']),'answered_with_skipped_stage')
            elif gold['phase']in {'catalog_filters','search'}:
                later=STAGES[STAGES.index(gold['phase'])+1:-1];check(all(t['status']=='skipped'for t in a['trace']if t['stage']in later or t['stage']=='model_selection'),'early_refusal_claims_unperformed_work')
        if r is not None:
            actual_claims=len(r.get('inputs',[]))+1+len(checks);exact(r,RESULT);check(a['execution_status']=='completed'and a['financial_status']=='answered','technical_or_refusal_has_number')
        if gold['result']is None:check(r is None,'refusal_has_hidden_number')
        elif r is None:errors.append('answer_missing_required_claims')
        else:
            check(all(r.get(k)==v for k,v in gold['result'].items()),'result_formula_unit_rounding_or_value_mismatch');claim_matches.append(all(r.get(k)==v for k,v in gold['result'].items()))
            check(r['inputs']==gold['inputs'],'input_cell_context_or_value_mismatch');check(r['sources']==gold['sources'],'source_locator_header_sha_or_provenance_mismatch')
            for i,f in enumerate(r['inputs']):claim_matches.append(i<len(gold['inputs'])and f==gold['inputs'][i]and i<len(r['sources'])and r['sources'][i]==gold['sources'][i])
            req=r['request'];check(req['request_id']==a['run_id']and req['original_question']==a.get('original_question',case['source'].get('request',{}).get('original_question'))and req['operation_id']==gold['intent']['operation_id']and req['organization_id']==gold['intent']['organization']and req['consolidation']==gold['intent']['consolidation']and req['accounting_standard']==gold['intent']['accounting_standard']and req['mode']==gold['intent']['mode']and req['as_of']==gold['intent']['as_of']and req['version_policy']==gold['intent']['version_policy']and req['result_unit']==gold['intent']['result_unit'],'request_context_mismatch')
            refs=[dict(role=f['role'],**{k:f[k]for k in ['fact_id','document_id','version_id','metric_id','definition_id','period']},source_unit=f['source_unit'])for f in gold['inputs']];check(req['inputs']==refs,'request_refs_mismatch')
            if case['target']=='service':
                check(a['retrieval']is not None and a['retrieval']['source_kind']=='prepared'and a['retrieval']['status']=='found','answer_without_prepared_search');gate=r['retrieval_resolution'];check(gate is not None and gate['kind']=='prepared'and set(gate['matched_evidence_ids'])=={f['evidence_id']for f in gold['inputs']}and gate['index_sha256']==a['retrieval']['index_sha256'],'calculation_retrieval_receipt_mismatch')
                spec=a['retrieval']['spec'];check(spec['organization_id']==gold['intent']['organization']and spec['documents']==list({f['document_id']:dict(document_id=f['document_id'],version_id=f['version_id'])for f in gold['inputs']}.values())and spec['periods']==list({digest(f['period']):f['period']for f in gold['inputs']}.values()),'searched_context_mismatch')
            if method=='A':check(a['selection']['choice_valid']and a['selection']['primary_searches']==1 and a['selection']['validation_searches']>=2,'A_selection_or_search_missing')
            if method=='C':check(a['agent']['finished']and a['agent']['receipt_id']is not None,'C_finish_missing')
        if gold['assumption_checks']:
            claim_matches.extend(c==g for c,g in zip(checks,gold['assumption_checks']))
        technical=a.get('execution_status')in {'error','limit'};isnum=gold['result']is not None
        return dict(case_id=case['case_id'],method=method,matched=not errors,errors=errors,numeric_expected=isnum,numeric_correct=isnum and not errors,refusal_expected=not isnum,refusal_correct=not isnum and not errors and not technical,false_refusal=isnum and not technical and a.get('execution_status')=='completed'and r is None,technical_completed=a.get('execution_status')=='completed',supported_claims=sum(claim_matches),observed_claims=actual_claims,required_claims=(len(gold['inputs'])+1+len(gold['assumption_checks']))if isnum else 0,complete_claims=isnum and not errors,usage=u)
    except (KeyError,TypeError,ValueError,AttributeError,IndexError)as exc:
        # Invalid schemas/unknown extra narrative are failures, not financial refusals.
        return dict(case_id=case['case_id'],method=a.get('method','invalid')if isinstance(a,dict)else'invalid',matched=False,errors=errors+[str(exc)if isinstance(exc,ProtocolError)else'malformed_answer'],numeric_expected=gold['result']is not None,numeric_correct=False,refusal_expected=gold['result']is None,refusal_correct=False,false_refusal=False,technical_completed=False,supported_claims=0,observed_claims=max(actual_claims,1),required_claims=len(gold['inputs'])+1 if gold['result']is not None else 0,complete_claims=False,usage=dict(chat_requests=None,unknown_requests=1,usage=None,adapter=None))

def evaluate_parser(case,gold,binding):
    try:
        t=binding['normalized_input'];checks=[binding['status']==gold['expected']['binding_status'],binding['reason_code']==gold['expected']['reason_code'],t['original_question']==case['source']['question'],all(t['fields'][k]==v for k,v in gold['fields'].items()),set(gold['required_clarification_fields'])<={c['field']for c in binding['clarifications']},binding['financial_status']is None,binding['calculations_performed']is False]
        checks.append(len(t['assumptions'])==len(gold['assumptions'])and all(all(a[k]==v for k,v in g.items())for a,g in zip(t['assumptions'],gold['assumptions'])))
        return dict(case_id=case['case_id'],matched=all(checks),checks=checks,quality_scope='known separate parser control; not financial QA')
    except (KeyError,TypeError):return dict(case_id=case['case_id'],matched=False,checks=[],quality_scope='malformed parser observation')

def evaluate_scenario(case,gold,out):
    errors=[]
    try:
        require(all(out[k]==v for k,v in gold['expected'].items()),'scenario_status_mismatch');require(out['schema_version']=='kp3-scenario-outcome-0.1','scenario_schema_mismatch');require(out['label']==gold['label']and out['model_calls']==0,'scenario_origin_or_usage');require(out['signal']==gold['signal'],'scenario_signal_mismatch')
        require(all(t['run_id']==out['run_id']for t in out['trace']),'scenario_trace_run_mismatch')
        if case['source']['kind']=='scenario':
            require(all(out['request'][k]==case['source']['request'][k]for k in ['parameters','data_mode','decision_at']),'scenario_request_changed')
        if out['financial']is not None and out['financial']['status']=='verified':
            require(out['request']['financial_run_id']==out['financial']['run_id'],'upstream_run_lost');require(all(s['data_origin']==case['data_origin']for s in out['financial']['financial_result']['sources']),'scenario_source_origin_mixed')
            if case['source']['kind']=='real_readiness':
                f=case['source']['financial_source']['form']['fields'];r=out['financial']['request'];require(r['organization_id']==f['organization']and r['operation_id']==f['operation_id']and [x['period']for x in r['inputs']]==f['periods']and {x['document_id']for x in r['inputs']}=={d['document_id']for d in f['documents']},'real_financial_intent_changed');require(out['request']['decision_at']==case['source']['decision_at'],'real_decision_changed')
        if gold['reference']is None:require(out['scenario']is None and out['comparisons']is None,'blocked_has_pnl')
        else:
            require(out['data_mode']=='own_synthetic'and out['eligibility']['status']=='eligible','completed_real_or_ineligible_trade')
            for key,path in [('scenario',out['scenario']),('cash',out['comparisons']['cash_no_interest']),('hold',out['comparisons']['hold_same_allocation'])]:
                ref=gold['reference'][key];require(len(path['ledger'])==len(ref['rows']),'ledger_length_mismatch');require(path['entry_quantity']==ref['entry_quantity']and path['final_quantity']==0,'quantity_mismatch')
                for field,k in [('final_cash','final_cash_cents'),('pnl','pnl_cents'),('fees','fees_cents'),('slippage_cost','slippage_cents'),('return_pct','return_percent_cents')]:require(Decimal(path[field])*100==ref[k],'scenario_money_mismatch')
                require(path['max_drawdown']['ratio']==ref['drawdown_ratio']and Decimal(path['max_drawdown']['percent'])*100==ref['drawdown_percent_cents'],'drawdown_mismatch')
                require(path['final_equity']==path['final_cash']and path['entry_at']==ref['entry_at']and path['exit_at']==ref['exit_at'],'final_equity_or_execution_time_mismatch')
                for x,y in zip(path['ledger'],ref['rows']):require((x['action'],Decimal(x['cash'])*100,x['quantity'],Decimal(x['equity'])*100,Decimal(x['commission'])*100,Decimal(x['gross'])*100,Decimal(x['slippage_cost'])*100)==(y['action'],y['cash_cents'],y['quantity'],y['equity_cents'],y['commission_cents'],y['gross_cents'],y['slippage_cents']),'ledger_row_mismatch')
        if 'required_gaps'in gold:require(out['data_mode']=='real_source_readiness'and out['request']['parameters']is None and set(gold['required_gaps'])<=set(out['eligibility']['reason_codes']),'real_gap_lost_or_synthetic_mixing')
    except (KeyError,TypeError,ValueError,ArithmeticError)as e:errors.append(str(e))
    return dict(case_id=case['case_id'],matched=not errors,errors=errors)
