"""Versioned partial input, separate from monetary Task0.2 and financial Request0.3."""
from copy import deepcopy
from .calculation_contracts import OPERATIONS,result_unit
from .contracts_v2 import boundary,identifier,instant,need,period,shape,text,unit

SCHEMA='kp3-input-0.1'
FORM_SCHEMA='kp3-form-0.1'
FIELDS='organization consolidation accounting_standard operation_id metric_ids definition_ids periods documents version_policy source_unit result_unit mode as_of comparability_id'.split()


@boundary
def validate_fields(fields,partial=False):
    need(type(fields)is dict and not(set(fields)-set(FIELDS)),'input_fields_mismatch')
    if not partial:need(set(fields)==set(FIELDS),'input_fields_mismatch')
    for k,v in fields.items():
        if v is None:continue
        if k=='organization':text(v)
        elif k in {'operation_id','comparability_id'}:identifier(v)
        elif k in {'metric_ids','definition_ids'}:
            need(type(v)is list and 1<=len(v)<=2 and len(v)==len(set(v)),'invalid_metric_selection')
            for x in v:identifier(x)
        elif k=='periods':
            need(type(v)is list and 1<=len(v)<=2,'invalid_period_selection')
            for p in v:period(p)
        elif k=='documents':
            need(type(v)is list and 1<=len(v)<=2 and len({r['document_id']for r in v})==len(v),'invalid_document_selection')
            for d in v:shape(d,'document_id version_id');identifier(d['document_id']);identifier(d['version_id'])
        elif k=='source_unit':unit(v)
        elif k=='result_unit':result_unit(v)
        elif k=='as_of':instant(v)
        else:
            allowed={'consolidation':{'group','legal_entity'},'accounting_standard':{'IFRS','RAS'},'version_policy':{'explicit_versions','original_period_documents'},'mode':{'snapshot','historical'}}
            need(v in allowed[k],'invalid_input_'+k)


@boundary
def validate_assumptions(rows,question):
    need(type(rows)is list and len(rows)<=2,'invalid_assumptions')
    for a in rows:
        shape(a,'kind asserted_direction text_fragment requires_check why_requested')
        need(a['kind']=='direction' and a['asserted_direction']in {'increase','decrease','unchanged'}and a['requires_check']is True and type(a['why_requested'])is bool,'invalid_assumption')
        text(a['text_fragment']);need(a['text_fragment']in question,'assumption_source_mismatch')


def new_input(input_id,question,kind,catalog_digest,language_version):
    identifier(input_id);text(question)
    return dict(schema_version=SCHEMA,input_id=input_id,original_question=question,input_kind=kind,raw_fields=None,fields={k:None for k in FIELDS},field_origins={k:'unset'for k in FIELDS},assumptions=[],assumption_origin='none',hints=dict(years=[],as_of_text=None,document_report_year=None,organization_unmatched=None),issues=[],unsupported_reasons=[],unfulfilled_requests=[],history=[],catalog_digest=catalog_digest,language_version=language_version)


@boundary
def validate_input(task):
    shape(task,'schema_version input_id original_question input_kind raw_fields fields field_origins assumptions assumption_origin hints issues unsupported_reasons unfulfilled_requests history catalog_digest language_version')
    need(task['schema_version']==SCHEMA and task['input_kind']in {'text','form'},'unsupported_input_version')
    identifier(task['input_id']);text(task['original_question']);validate_fields(task['fields']);validate_assumptions(task['assumptions'],task['original_question'])
    need(task['assumption_origin']in {'none','text','form'}and bool(task['assumptions'])==(task['assumption_origin']!='none'),'invalid_assumption_origin')
    if task['raw_fields']is not None:validate_fields(task['raw_fields'],partial=True)
    need(set(task['field_origins'])==set(FIELDS)and all(x in {'unset','text','form','clarification','catalog_unique','operation'}for x in task['field_origins'].values()),'invalid_field_origins')
    shape(task['hints'],'years as_of_text document_report_year organization_unmatched')
    need(type(task['issues'])is list and type(task['unsupported_reasons'])is list and type(task['unfulfilled_requests'])is list and type(task['history'])is list and len(task['history'])<=16,'invalid_input_history')
    need(len(task['issues'])<=64 and len(task['unsupported_reasons'])<=16 and len(task['unfulfilled_requests'])<=16,'input_metadata_limit')
    for i in task['issues']:
        shape(i,'field code message');need(i['field']in FIELDS,'unknown_issue_field');identifier(i['code']);text(i['message'])
    for code in task['unsupported_reasons']+task['unfulfilled_requests']:identifier(code)
    for h in task['history']:
        shape(h,'answers replaced_unresolved');validate_fields(h['answers'],partial=True);validate_fields(h['replaced_unresolved'],partial=True)
    hints=task['hints'];need(type(hints['years'])is list and len(hints['years'])<=16 and all(type(y)is int and 2000<=y<=2099 for y in hints['years']),'invalid_period_hints')
    for k in ['as_of_text','organization_unmatched']:
        if hints[k]is not None:text(hints[k])
    need(hints['document_report_year']is None or type(hints['document_report_year'])is int and 2000<=hints['document_report_year']<=2099,'invalid_document_hint')
    from .contracts_v2 import sha
    sha(task['catalog_digest']);identifier(task['language_version'])


@boundary
def clarification(task,answers):
    """Only fill unset fields. Original wording, assumptions and existing choices stay immutable."""
    validate_input(task);validate_fields(answers,partial=True);need(bool(answers),'empty_clarification')
    need(len(task['history'])<16,'clarification_limit')
    result=deepcopy(task)
    replaced={}
    for k,v in answers.items():
        need(v is not None,'empty_clarification')
        old=result['fields'][k]
        if old is not None and old!=v:
            replace_unknown=any(i['field']==k and i['code']=='unknown_organization'for i in result['issues'])
            complete_periods=k=='periods'and any(i['field']==k and i['code']=='wrong_period_count'for i in result['issues'])and all(p in v for p in old)
            need(replace_unknown or complete_periods,'clarification_conflict');replaced[k]=deepcopy(old)
        if old!=v:result['fields'][k]=deepcopy(v);result['field_origins'][k]='clarification'
    result['history'].append(dict(answers=deepcopy(answers),replaced_unresolved=replaced))
    # Parser diagnostics for a field are discharged only by an explicit answer to that field.
    result['issues']=[x for x in result['issues']if x['field']not in answers]
    validate_input(result);return result
