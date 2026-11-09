"""Explicit financial request/outcome0.3; Catalog0.2 and legacy0.1/0.2 stay unchanged."""
from .contracts_v2 import (ClarificationRequired,ContractError,identifier,instant,need,
                          period,shape,text,unit)

VERSION='0.3'
OPERATIONS={
    'direct_fact_v1':dict(plan_name='get_fact',roles=['fact'],result_kind='amount',formula='selected reported value'),
    'absolute_change_v1':dict(plan_name='absolute_delta',roles=['previous','current'],result_kind='amount',formula='current - previous'),
    'relative_change_v1':dict(plan_name='relative_change',roles=['previous','current'],result_kind='percent',formula='(current - previous) / previous * 100'),
    'scale_v1':dict(plan_name='scale_conversion',roles=['fact'],result_kind='amount',formula='value * source_scale / target_scale'),
    'operating_margin_v1':dict(plan_name='operating_margin',roles=['profit','revenue'],result_kind='percent',formula='operating_profit / revenue * 100')}
REQUEST_FIELDS='schema_version request_id original_question operation_id organization_id consolidation accounting_standard inputs version_policy comparability_id result_unit mode as_of'
REFERENCE_FIELDS='role fact_id document_id version_id metric_id definition_id period source_unit'


def result_unit(value):
    need(type(value) is dict,'invalid_result_unit')
    if value.get('kind')=='amount':
        shape(value,'kind currency scale');unit({k:value[k]for k in ['currency','scale']})
    else:
        shape(value,'kind');need(value['kind'] in {'percent','percentage_point'},'invalid_result_unit')


def validate_request(req):
    need(type(req) is dict,'invalid_request')
    need(req.get('schema_version')==VERSION,'unsupported_schema_version')
    allowed=set(REQUEST_FIELDS.split());need(not(set(req)-allowed),'fields_mismatch')
    missing=[k for k in allowed-{'comparability_id','as_of'}if k not in req or req[k] is None or req[k]=='' or req[k]==[]]
    if missing:raise ClarificationRequired('missing_fields',sorted(missing))
    shape(req,REQUEST_FIELDS)
    for k in ['request_id','operation_id','organization_id']:identifier(req[k])
    text(req['original_question'])
    need(req['consolidation'] in {'group','legal_entity'} and req['accounting_standard'] in {'IFRS','RAS'},'invalid_scope')
    need(type(req['inputs']) is list and 1<=len(req['inputs'])<=2,'wrong_input_count')
    for i,ref in enumerate(req['inputs']):
        need(type(ref) is dict and not(set(ref)-set(REFERENCE_FIELDS.split())),'fields_mismatch')
        missing=[f'inputs[{i}].{k}'for k in REFERENCE_FIELDS.split()if k not in ref or ref[k] is None or ref[k]=='']
        if missing:raise ClarificationRequired('missing_fields',missing)
        shape(ref,REFERENCE_FIELDS)
        for k in ['fact_id','document_id','version_id','metric_id','definition_id']:identifier(ref[k])
        need(ref['role'] in {'fact','previous','current','profit','revenue'},'invalid_input_role')
        period(ref['period']);unit(ref['source_unit'])
    result_unit(req['result_unit'])
    if req['operation_id'] in OPERATIONS:
        expected=OPERATIONS[req['operation_id']]
        need([r['role']for r in req['inputs']]==expected['roles'],'wrong_input_roles')
        need(req['result_unit'].get('kind')==expected['result_kind'],'wrong_result_kind')
    need(req['version_policy'] in {'explicit_versions','original_period_documents'},'invalid_version_policy')
    if req['comparability_id'] is not None:identifier(req['comparability_id'])
    need(req['mode'] in {'snapshot','historical'},'invalid_mode')
    if req['mode']=='historical':
        if req['as_of'] is None:raise ClarificationRequired('missing_fields',['as_of'])
        instant(req['as_of'])
    else:need(req['as_of'] is None,'as_of_requires_historical')


FINANCIAL_REASONS={
    'missing':{'value_missing','unverified_candidate','publication_unknown','not_yet_available','document_unchecked','original_version_missing','retrieval_context_missing'},
    'conflict':{'duplicate_candidates','entity_or_standard_mismatch','definition_mismatch','incompatible_periods','incompatible_units','incompatible_versions','input_fact_context_mismatch','comparability_not_established'},
    'unsupported':{'unsupported_operation','nonpositive_base','zero_denominator','negative_revenue_denominator','currency_conversion_not_supported'}}
TECHNICAL_REASONS={'input_invalid','context_invalid','source_missing','source_version_mismatch','source_access_error','artifact_integrity_error','retrieval_invalid','output_error','internal_error'}


def validate_outcome(out):
    shape(out,'schema_version run_id request_id execution_status financial_status reason_code clarification_fields technical_details financial_result')
    need(out['schema_version']==VERSION,'unsupported_schema_version')
    identifier(out['run_id']);identifier(out['request_id'])
    fields=out['clarification_fields'];need(type(fields) is list and len(fields)==len(set(fields)) and all(isinstance(f,str)and f for f in fields),'invalid_clarification_fields')
    if out['execution_status']=='completed':
        need(not fields and out['technical_details'] is None,'mixed_status')
        if out['financial_status']=='answered':
            need(out['reason_code']=='ok' and type(out['financial_result']) is dict,'answer_required')
            calc=out['financial_result'];shape(calc,'calculation_schema_version operation_id formula formula_version request admission_context inputs sources intermediates exact_result display_value result_unit rounding precision_note warnings retrieval_resolution')
            need(calc['calculation_schema_version']==VERSION and calc['operation_id'] in OPERATIONS and calc['formula']==OPERATIONS[calc['operation_id']]['formula'] and calc['formula_version']=='1.0','invalid_calculation')
            validate_request(calc['request'])
            need(calc['request']['request_id']==out['request_id'] and calc['request']['operation_id']==calc['operation_id'],'invalid_calculation_request')
            need(type(calc['inputs']) is list and len(calc['inputs'])==len(OPERATIONS[calc['operation_id']]['roles']),'invalid_calculation_inputs')
            need(type(calc['sources']) is list and len(calc['sources'])==len(calc['inputs']),'invalid_calculation_sources')
            shape(calc['admission_context'],'context_id catalog_id component_digests admission_digest')
            identifier(calc['admission_context']['context_id']);identifier(calc['admission_context']['catalog_id'])
            import re
            need(isinstance(calc['display_value'],str) and len(calc['display_value'])<=300 and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',calc['display_value']),'invalid_display_decimal')
            result_unit(calc['result_unit'])
            need(calc['result_unit']['kind']==OPERATIONS[calc['operation_id']]['result_kind'],'wrong_result_kind')
            rational(calc['exact_result'])
            need(type(calc['intermediates']) is dict,'invalid_intermediates')
            for value in calc['intermediates'].values():rational(value)
        else:
            need(out['financial_status'] in FINANCIAL_REASONS and out['reason_code'] in FINANCIAL_REASONS[out['financial_status']] and out['financial_result'] is None,'invalid_financial_refusal')
    else:
        need(out['financial_status'] is None and out['financial_result'] is None,'technical_status_has_no_financial_result')
        if out['execution_status']=='awaiting_clarification':need(out['reason_code']=='missing_fields' and bool(fields) and out['technical_details'] is None,'invalid_clarification')
        else:
            need(out['execution_status']=='error' and out['reason_code'] in TECHNICAL_REASONS and not fields and type(out['technical_details']) is dict,'invalid_technical_error')
            shape(out['technical_details'],'subsystem code');text(out['technical_details']['subsystem']);identifier(out['technical_details']['code'])


def rational(value):
    shape(value,'numerator denominator')
    import re
    need(isinstance(value['numerator'],str) and re.fullmatch(r'-?(?:0|[1-9][0-9]*)',value['numerator']) and len(value['numerator'])<=300,'invalid_rational')
    need(isinstance(value['denominator'],str) and re.fullmatch(r'[1-9][0-9]*',value['denominator']) and len(value['denominator'])<=300,'invalid_rational')
