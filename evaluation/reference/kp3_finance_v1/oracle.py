"""Independent development oracle: exact Fractions, no production imports or I/O.

Not a runtime calculator. Case overlays are own reference fixtures, not admitted
mutations of verified facts. Never import this module from the answering path.
"""
from copy import deepcopy
from datetime import date, datetime
from fractions import Fraction
from calendar import monthrange
import re

COUNTS = {'direct_fact_v1':1,'absolute_change_v1':2,'relative_change_v1':2,'annual_growth_v1':2,
          'scale_v1':1,'operating_margin_v1':2,'margin_change_pp_v1':4}
SCALES={1,1000,1000000,1000000000}
OVERRIDES={'value','currency','scale','definition_id','period','organization_id','accounting_standard',
           'consolidation','version_id','document_id','provenance_status','evidence_present','origin_role'}


class FixtureError(ValueError):
    pass


def numeric(value):
    if not isinstance(value,str) or not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',value) or len(value)>60:
        raise ValueError('invalid_decimal')
    return Fraction(value)


def rational(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator)}


def rounded(value,places=2):
    """HALF_UP by integer quotient/remainder; independent of Decimal rounding."""
    denominator=value.denominator
    quotient,remainder=divmod(abs(value.numerator)*10**places,denominator)
    if remainder*2>=denominator:quotient+=1
    digits=str(quotient).zfill(places+1)
    body=digits[:-places]+'.'+digits[-places:] if places else digits
    return ('-' if value<0 and quotient else '')+body


def finite_decimal(value):
    denominator=value.denominator;twos=fives=0
    while denominator%2==0:twos+=1;denominator//=2
    while denominator%5==0:fives+=1;denominator//=5
    if denominator!=1:raise ValueError('not_finite_decimal')
    places=max(twos,fives);integer=abs(value.numerator)*10**places//value.denominator
    digits=str(integer).zfill(places+1)
    body=(digits[:-places]+'.'+digits[-places:]).rstrip('0').rstrip('.') if places else digits
    return ('-' if value<0 else '')+body


def comparable(previous,current,annual=False):
    if previous.get('kind')!='duration' or current.get('kind')!='duration':return False
    kind=previous.get('duration_type')
    if kind not in {'full_year','year_to_date','quarter'} or current.get('duration_type')!=kind:return False
    try:
        a,b,c,d=[date.fromisoformat(x) for x in (previous['start'],previous['end'],current['start'],current['end'])]
    except (KeyError,ValueError,TypeError):return False
    if not(a<=b<c<=d) or (a.month,a.day,b.month,b.day)!=(c.month,c.day,d.month,d.day):return False
    if annual:return kind=='full_year' and (a.month,a.day,b.month,b.day)==(1,1,12,31) and c.year==a.year+1
    return True


def valid_duration(value):
    if not isinstance(value,dict) or set(value)!={'kind','duration_type','start','end'} or value['kind']!='duration':return False
    try:start,end=date.fromisoformat(value['start']),date.fromisoformat(value['end'])
    except (TypeError,ValueError):return False
    if start>end or start.year!=end.year:return False
    kind=value['duration_type']
    if kind=='full_year':return (start.month,start.day,end.month,end.day)==(1,1,12,31)
    if kind=='year_to_date':return (start.month,start.day)==(1,1) and end.month<12
    if kind=='quarter':return start.month in {1,4,7,10} and start.day==1 and end.month==start.month+2 and end.day==monthrange(end.year,end.month)[1]
    return False


def make_gold(catalog,dataset,dictionary):
    if set(dataset)!={'case_schema_version','dataset_id','known_to_codex','purpose','cases'} or dataset['case_schema_version']!='1.0':raise FixtureError('invalid_dataset')
    defs={d['definition_id']:d for d in dictionary['definitions']}
    docs={d['document_id']:d for d in catalog['documents']};orgs={o['organization_id']:o for o in catalog['organizations']}
    evs={e['evidence_id']:e for e in catalog['evidence']};facts={}
    for f in catalog['facts']:
        d=docs[f['document_id']];org=orgs[f['organization_id']]
        facts[f['fact_id']]={**deepcopy(f),'accounting_standard':d['accounting_standard'],
            'declared_document_id':d['document_id'],'declared_version_id':d['version_id'],
            'consolidation':org['consolidation'],'provenance_status':f['provenance']['status'],
            'evidence_present':f['evidence_id'] in evs and evs[f['evidence_id']]['provenance']['status'] in {'assistant_checked','human_reviewed'},
            'publication':deepcopy(d['publication'])}
    ids=set();rows=[]
    fields={'case_id','split','data_origin','operation_id','input_fact_ids','input_overrides','result_unit','mode','as_of','execution_fixture'}
    for case in dataset['cases']:
        if not isinstance(case,dict) or set(case)-{'version_policy'}!=fields or case['case_id'] in ids:raise FixtureError('invalid_case_fields_or_duplicate_id')
        ids.add(case['case_id'])
        if case['split']!='dev_open' or case['data_origin']!='own_synthetic':raise FixtureError('not_own_open_dev')
        if not isinstance(case['input_overrides'],dict):raise FixtureError('invalid_overrides')
        for fid,changes in case['input_overrides'].items():
            if fid not in case['input_fact_ids'] or not isinstance(changes,dict) or set(changes)-OVERRIDES:raise FixtureError('forbidden_fixture_override')
        rows.append(reference_case(case,facts,defs))
    return {'gold_schema_version':'1.0','dataset_id':dataset['dataset_id'],'basis':'independent Fraction/integer development oracle, not production answers',
            'blind_evaluation':False,'model_calls':0,'cases':rows}


def reference_case(case,facts,defs):
    def finish(financial,reason,calculation=None,execution='completed',fields=None):
        return {'case_id':case['case_id'],'execution_status':execution,'financial_status':financial,
                'reason_code':reason,'clarification_fields':fields or [],'calculation':calculation,'label':'SYNTHETIC_METHOD_ONLY'}
    fixture=case['execution_fixture']
    if fixture is not None:
        if fixture in {'source_missing','model_unavailable'}:return finish(None,fixture,execution='error')
        if fixture=='call_limit':return finish(None,fixture,execution='limit_exceeded')
        if fixture=='missing_period':return finish(None,'missing_fields',execution='awaiting_clarification',fields=['periods'])
        raise FixtureError('unknown_execution_fixture')
    operation=case['operation_id']
    if operation not in COUNTS:return finish('unsupported','unsupported_operation')
    if len(case['input_fact_ids'])!=COUNTS[operation]:return finish(None,'input_invalid',execution='error')
    if len(set(case['input_fact_ids']))!=len(case['input_fact_ids']):return finish('conflict','duplicate_candidates')
    selected=[]
    for fid in case['input_fact_ids']:
        if fid not in facts:return finish(None,'input_invalid',execution='error')
        f=deepcopy(facts[fid]);f.update(deepcopy(case['input_overrides'].get(fid,{})));selected.append(f)
    if case['mode']=='snapshot':
        if case['as_of'] is not None:return finish(None,'input_invalid',execution='error')
    elif case['mode']=='historical':
        if case['as_of'] is None:return finish(None,'missing_fields',execution='awaiting_clarification',fields=['as_of'])
        try:stamp=datetime.fromisoformat(case['as_of'].replace('Z','+00:00'))
        except (ValueError,TypeError,AttributeError):return finish(None,'input_invalid',execution='error')
        if stamp.utcoffset() is None:return finish(None,'input_invalid',execution='error')
        # All selected source publications in this dataset are intentionally unknown.
        if any(f['publication']['precision']!='unknown' for f in selected):raise FixtureError('this_dev_oracle_has_no_new_publication_evidence')
        return finish('missing','publication_unknown')
    else:return finish(None,'input_invalid',execution='error')
    for f in selected:
        if f['value'] is None:return finish('missing','value_missing')
        try:numeric(f['value'])
        except ValueError:return finish(None,'input_invalid',execution='error')
        if type(f['scale']) is not int or f['scale'] not in SCALES or f['currency'] not in {'RUB','USD'}:return finish(None,'input_invalid',execution='error')
        if f['provenance_status'] not in {'assistant_checked','human_reviewed'} or not f['evidence_present']:return finish('missing','unverified_candidate')
        if case.get('version_policy')=='original_period_documents' and f['origin_role']!='reported_period':return finish('missing','original_version_missing')
        if f['accounting_standard']!='IFRS' or f['consolidation']!='group':return finish('conflict','entity_or_standard_mismatch')
        if f['definition_id'] not in defs or defs[f['definition_id']]['metric_id']!=f['metric_id']:return finish('conflict','definition_mismatch')
        if not valid_duration(f['period']):return finish('conflict','incompatible_periods')
    if len({f['organization_id'] for f in selected})!=1:return finish('conflict','entity_or_standard_mismatch')
    if len({(f['currency'],f['scale']) for f in selected})!=1:return finish('conflict','incompatible_units')
    if any(f['version_id']!=f['declared_version_id'] or f['document_id']!=f['declared_document_id'] for f in selected):return finish('conflict','incompatible_versions')
    if len({f['document_id'] for f in selected})>1 and any(f['origin_role']!='reported_period' for f in selected):return finish('conflict','incompatible_versions')
    values=[numeric(f['value']) for f in selected];intermediates={}
    target=case['result_unit']
    expected_kind='percent' if operation in {'relative_change_v1','annual_growth_v1','operating_margin_v1'} else 'percentage_point' if operation=='margin_change_pp_v1' else 'amount'
    if not isinstance(target,dict) or target.get('kind')!=expected_kind:return finish(None,'input_invalid',execution='error')
    if expected_kind=='amount':
        if set(target)!={'kind','currency','scale'} or type(target['scale']) is not int or target['scale'] not in SCALES:return finish(None,'input_invalid',execution='error')
        if target['currency']!=selected[0]['currency']:return finish('unsupported','currency_conversion_not_supported')
        if operation!='scale_v1' and target['scale']!=selected[0]['scale']:return finish('conflict','incompatible_units')
    elif set(target)!={'kind'}:return finish(None,'input_invalid',execution='error')
    if operation in {'absolute_change_v1','relative_change_v1','annual_growth_v1'}:
        if len({(f['metric_id'],f['definition_id']) for f in selected})!=1:return finish('conflict','definition_mismatch')
        if not comparable(selected[0]['period'],selected[1]['period'],operation=='annual_growth_v1'):return finish('conflict','incompatible_periods')
        difference=values[1]-values[0];intermediates['difference']=rational(difference)
        if operation=='absolute_change_v1':value=difference
        else:
            if values[0]<=0:return finish('unsupported','nonpositive_base')
            intermediates['current_divided_by_previous']=rational(values[1]/values[0]);value=difference/values[0]*100
    elif operation in {'operating_margin_v1','margin_change_pp_v1'}:
        margins=[]
        for index in range(0,len(selected),2):
            profit,revenue=selected[index:index+2]
            if (profit['metric_id'],revenue['metric_id'])!=('operating_profit','revenue'):return finish('conflict','definition_mismatch')
            if profit['period']!=revenue['period']:return finish('conflict','incompatible_periods')
            if profit['document_id']!=revenue['document_id']:return finish('conflict','incompatible_versions')
            if values[index+1]==0:return finish('unsupported','zero_denominator')
            if values[index+1]<0:return finish('unsupported','negative_revenue_denominator')
            margins.append(values[index]/values[index+1]*100)
        if operation=='margin_change_pp_v1':
            if not comparable(selected[0]['period'],selected[2]['period']):return finish('conflict','incompatible_periods')
            intermediates.update(previous_margin_pct=rational(margins[0]),current_margin_pct=rational(margins[1]))
            value=margins[1]-margins[0]
        else:
            intermediates['profit_divided_by_revenue']=rational(values[0]/values[1]);value=margins[0]
    elif operation=='scale_v1':
        multiplier=Fraction(selected[0]['scale'],target['scale']);intermediates['scale_multiplier']=rational(multiplier);value=values[0]*multiplier
    else:value=values[0]
    display=(selected[0]['value'] if operation=='direct_fact_v1' else finite_decimal(value)) if expected_kind=='amount' else rounded(value)
    calc={'formula_id':operation,'inputs':[{'fact_id':f['fact_id'],'value':f['value'],'currency':f['currency'],'scale':f['scale']} for f in selected],
          'intermediates':intermediates,'exact_result':rational(value),'display_value':display,'result_unit':deepcopy(target),
          'rounding':'exact_input_decimal' if operation=='direct_fact_v1' else 'exact_finite_decimal' if expected_kind=='amount' else 'integer_HALF_UP_2',
          'precision_note':'Exact arithmetic on supplied rounded inputs does not improve source precision.'}
    return finish('answered','ok',calc)
