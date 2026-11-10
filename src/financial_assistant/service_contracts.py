"""Service/Answer0.1 envelopes; old contracts and financial arithmetic are unchanged."""
from .contracts_v2 import identifier,need,shape
from .calculation_contracts import validate_outcome

VERSION='kp3-answer-0.1'
STAGES=['input','catalog_filters','search','fact_resolution','source_validation','calculation','result_validation','answer']


def validate_answer(a):
    shape(a,'schema_version run_id task_id method execution_status request_status financial_status reason_code original_question normalized_input clarifications financial_result outcome assumption_checks unfulfilled_requests retrieval trace context_digest source_input_digest saved_run model_calls')
    need(a['schema_version']==VERSION,'unsupported_answer_version');identifier(a['run_id']);need(a['task_id']==a['run_id'],'task_run_mismatch')
    need(a['execution_status']in {'completed','awaiting_clarification','error','limit'},'invalid_execution_status')
    need(a['model_calls']==0 and type(a['trace'])is list,'invalid_fixed_service_usage')
    need([t['stage']for t in a['trace']]==STAGES,'incomplete_trace')
    for t in a['trace']:
        shape(t,'stage run_id status elapsed_ms reason_code details')
        need(t['run_id']==a['run_id']and t['status']in {'completed','skipped','error','blocked','awaiting_clarification'},'invalid_stage')
        need(type(t['elapsed_ms'])in {int,float}and t['elapsed_ms']>=0,'invalid_timing')
        if t['status']=='skipped':need(t['elapsed_ms']==0,'skipped_stage_timed')
    if a['outcome']is not None:
        validate_outcome(a['outcome']);need(a['outcome']['run_id']==a['run_id']and a['outcome']['request_id']==a['run_id'],'outcome_run_mismatch')
        need(a['financial_status']==a['outcome']['financial_status']and a['financial_result']==a['outcome']['financial_result'],'answer_outcome_mismatch')
    else:need(a['financial_status']is None and a['financial_result']is None,'uncomputed_financial_result')
    if a['execution_status']!='completed':need(a['financial_status']is None and a['financial_result']is None,'technical_result_has_money')
    if a['financial_status']!='answered':need(all(c['status']=='not_checked'for c in a['assumption_checks']),'premise_confirmed_without_answer')
    if a['financial_status']=='answered':
        need(a['retrieval']is not None and a['retrieval']['source_kind']=='prepared'and a['retrieval']['status']=='found','answer_without_prepared_search')
        need(a['normalized_input']['original_question']==a['original_question'],'question_lost')


def assumption_checks(assumptions,outcome):
    from copy import deepcopy
    checks=[]
    for assumption in assumptions:
        row=dict(assumption=deepcopy(assumption),status='not_checked',observed_direction=None,explanation_status='not_supported'if assumption['why_requested']else 'not_requested')
        if outcome and outcome['financial_status']=='answered'and outcome['financial_result']['operation_id']in {'absolute_change_v1','relative_change_v1'}:
            n=int(outcome['financial_result']['intermediates']['difference']['numerator']);direction='increase'if n>0 else 'decrease'if n<0 else 'unchanged'
            row.update(status='supported'if direction==assumption['asserted_direction']else 'contradicted',observed_direction=direction)
        checks.append(row)
    return checks
