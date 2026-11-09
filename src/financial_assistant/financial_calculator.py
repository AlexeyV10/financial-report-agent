"""Five registered operations over admitted Fact IDs. Exact integer arithmetic; no model formula execution."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from math import gcd

from .calculation_contracts import OPERATIONS,VERSION,validate_outcome,validate_request
from .catalog import available_from
from .contracts_v2 import CHECKED,ClarificationRequired,ContractError,digest,instant,need
from .document_extraction import ExtractionError
from .retrieval_v2 import RetrievalError,search_index


def rat(n,d=1):
    if d==0:raise ArithmeticError('zero denominator after admission')
    if d<0:n,d=-n,-d
    g=gcd(n,d);return n//g,d//g


def from_decimal(s):return rat(*Decimal(s).as_integer_ratio())
def add(a,b):return rat(a[0]*b[1]+b[0]*a[1],a[1]*b[1])
def sub(a,b):return rat(a[0]*b[1]-b[0]*a[1],a[1]*b[1])
def mul(a,b):return rat(a[0]*b[0],a[1]*b[1])
def div(a,b):return rat(a[0]*b[1],a[1]*b[0])
def pair(r):return dict(numerator=str(r[0]),denominator=str(r[1]))


def finite_decimal(r):
    n,d=r;remaining=d;a=b=0
    while remaining%2==0:remaining//=2;a+=1
    while remaining%5==0:remaining//=5;b+=1
    if remaining!=1:raise ArithmeticError('registered amount must have a finite decimal')
    places=max(a,b);coefficient=abs(n)*2**(places-a)*5**(places-b)
    digits=str(coefficient).zfill(places+1)
    body=digits if not places else (digits[:-places]+'.'+digits[-places:]).rstrip('0').rstrip('.')
    return ('-'if n<0 else '')+body


def rounded_percent(r):
    n,d=r;q,rem=divmod(abs(n)*100,d)
    if rem*2>=d:q+=1
    digits=str(q).zfill(3);return ('-'if n<0 and q else '')+digits[:-2]+'.'+digits[-2:]


def comparable(previous,current):
    if previous['kind']!='duration' or current['kind']!='duration':return False
    kind=previous['duration_type']
    if kind not in {'full_year','year_to_date','quarter'} or current['duration_type']!=kind:return False
    a,b,c,d=[date.fromisoformat(x)for x in [previous['start'],previous['end'],current['start'],current['end']]]
    return a<=b<c<=d and (a.month,a.day,b.month,b.day)==(c.month,c.day,d.month,d.day)


def standard_duration(p):
    if p['kind']!='duration' or p['duration_type'] not in {'full_year','year_to_date','quarter'}:return False
    start,end=date.fromisoformat(p['start']),date.fromisoformat(p['end'])
    return start.year==end.year


def _base(request,run_id):
    return dict(schema_version=VERSION,run_id=run_id,request_id=request.get('request_id','invalid-request') if isinstance(request,dict)else 'invalid-request',execution_status='completed',financial_status=None,reason_code='ok',clarification_fields=[],technical_details=None,financial_result=None)


def _refuse(out,status,reason):
    out.update(financial_status=status,reason_code=reason);return out


def _technical(out,reason,subsystem,code):
    out.update(execution_status='error',financial_status=None,reason_code=reason,clarification_fields=[],technical_details=dict(subsystem=subsystem,code=code),financial_result=None)
    return out


def _snapshot(f,e,d,org,role):
    return dict(role=role,fact_id=f['fact_id'],organization_id=f['organization_id'],consolidation=org['consolidation'],accounting_standard=d['accounting_standard'],document_id=d['document_id'],version_id=d['version_id'],document_sha256=d['sha256'],metric_id=f['metric_id'],definition_id=f['definition_id'],period=deepcopy(f['period']),value=f['value'],source_unit=dict(currency=f['currency'],scale=f['scale']),origin_role=f['origin_role'],provenance=deepcopy(f['provenance']),evidence_id=e['evidence_id'],evidence_digest=digest(e),raw_value=e['raw_value'],numeric_encoding=e['numeric_encoding'],locator=deepcopy(e['locator']))


def _source(e,d):
    return dict(evidence=deepcopy(e),document_id=d['document_id'],version_id=d['version_id'],document_sha256=d['sha256'],source_url=d['document_url']+(f"#page={e['locator']['pdf_page']}"if e['locator']['kind']=='pdf'else '') if d['document_url'] else None,data_origin=d['data_origin'],audit=deepcopy(d['audit']),rights=deepcopy(d['rights']),publication=deepcopy(d['publication']))


def _retrieval_gate(ctx,req,selected,gate,out):
    if gate is None:return None
    # Trusted setup supplies artifact paths. The request cannot provide paths/exports/ready values.
    need(set(gate)=={'db_path','config','lexicon','export_paths'},'invalid_retrieval_guard')
    documents=list({f['document_id']:dict(document_id=d['document_id'],version_id=d['version_id'])for f,e,d,org in selected}.values())
    metrics=list({f['metric_id']:dict(metric_id=f['metric_id'],definition_id=f['definition_id'])for f,e,d,org in selected}.values())
    periods=list({digest(f['period']):f['period']for f,e,d,org in selected}.values())
    units=list({digest(dict(currency=f['currency'],scale=f['scale'])):dict(currency=f['currency'],scale=f['scale'])for f,e,d,org in selected}.values())
    tags={'revenue':'выручка','operating_profit':'операционная прибыль','operating_cash_flow':'CFO'}
    spec=dict(schema_version='kp3-search-0.1',query=' и '.join(tags[m['metric_id']]for m in metrics),organization_id=req['organization_id'],consolidation=req['consolidation'],accounting_standard=req['accounting_standard'],metrics=metrics,periods=periods,documents=documents,source_units=units,version_policy=req['version_policy'],mode=req['mode'],as_of=req['as_of'],top_k=32)
    hits=search_index(gate['db_path'],ctx.catalog,ctx.resources,gate['config'],gate['lexicon'],spec,gate['export_paths'])
    if hits['source_kind']!='prepared':return _refuse(out,'missing','unverified_candidate')
    if hits['status']!='found':return _refuse(out,'missing','retrieval_context_missing')
    needed={e['evidence_id']:e for f,e,d,org in selected};covered=set()
    for hit in hits['results']:
        ev=needed.get(hit['evidence_id'])
        if ev is None:continue
        if not(hit['source_kind']=='prepared_evidence' and hit['verification_status'] in CHECKED and hit['evidence_digest']==digest(ev)):raise RetrievalError('retrieval_evidence_mismatch')
        if not(hit['locator']==ev['locator'] and all(hit[k]==ev[k]for k in ['document_id','version_id','document_sha256','metric_id','definition_id','period','currency','scale','raw_value'])):raise RetrievalError('retrieval_evidence_mismatch')
        f=next(f for f,e,d,org in selected if e['evidence_id']==ev['evidence_id'])
        if hit['value']!=f['value']:raise RetrievalError('retrieval_evidence_mismatch')
        covered.add(ev['evidence_id'])
    if covered!=set(needed):return _refuse(out,'missing','retrieval_context_missing')
    return dict(kind='prepared',matched_evidence_ids=sorted(covered),retrieved_records=len(hits['results']),index_sha256=hits['index_sha256'],reverification_performed=False)


def _calculate(ctx,req,out,retrieval_gate):
    validate_request(req)
    try:ctx.validate()
    except ContractError as exc:return _technical(out,'context_invalid','admission',exc.code)
    op=req['operation_id']
    if op not in OPERATIONS:return _refuse(out,'unsupported','unsupported_operation')
    cat=ctx.catalog;docs={d['document_id']:d for d in cat['documents']};orgs={o['organization_id']:o for o in cat['organizations']};facts={f['fact_id']:f for f in cat['facts']};evs={e['evidence_id']:e for e in cat['evidence']};defs={d['definition_id']:d for d in ctx.dictionary['definitions']};metrics={m['metric_id']for m in cat['metrics']}
    need(req['organization_id'] in orgs,'unknown_organization_id')
    if req['consolidation']!='group' or req['accounting_standard']!='IFRS':return _refuse(out,'conflict','entity_or_standard_mismatch')
    ids=[r['fact_id']for r in req['inputs']]
    if len(ids)!=len(set(ids)):return _refuse(out,'conflict','duplicate_candidates')
    selected=[]
    for ref in req['inputs']:
        need(ref['fact_id'] in facts and ref['document_id'] in docs and ref['metric_id'] in metrics and ref['definition_id'] in defs,'unknown_input_id')
        f=facts[ref['fact_id']];d=docs[f['document_id']];org=orgs[f['organization_id']]
        if f['organization_id']!=req['organization_id'] or org['consolidation']!=req['consolidation'] or d['accounting_standard']!=req['accounting_standard']:return _refuse(out,'conflict','entity_or_standard_mismatch')
        if f['document_id']!=ref['document_id'] or f['version_id']!=ref['version_id']:return _refuse(out,'conflict','incompatible_versions')
        if f['metric_id']!=ref['metric_id'] or f['definition_id']!=ref['definition_id']:return _refuse(out,'conflict','definition_mismatch')
        if f['period']!=ref['period']:return _refuse(out,'conflict','incompatible_periods')
        if dict(currency=f['currency'],scale=f['scale'])!=ref['source_unit']:return _refuse(out,'conflict','incompatible_units')
        definition=defs[f['definition_id']]
        if definition['metric_id']!=f['metric_id'] or definition['accounting_standard']!='IFRS' or definition['consolidation']!='group' or definition['organization_type']!='nonfinancial':return _refuse(out,'conflict','definition_mismatch')
        if not standard_duration(f['period']):return _refuse(out,'conflict','incompatible_periods')
        key=lambda x:tuple(digest(x[k])for k in ['organization_id','document_id','version_id','metric_id','definition_id','period','currency','scale'])
        if sum(key(other)==key(f)for other in cat['facts'])!=1:return _refuse(out,'conflict','duplicate_candidates')
        if d['preparation_status'] not in {'ready','checked'} or d['provenance']['status'] not in CHECKED:return _refuse(out,'missing','document_unchecked')
        if f['value'] is None:return _refuse(out,'missing','value_missing')
        e=evs.get(f['evidence_id'])
        if f['provenance']['status'] not in CHECKED or e is None or e['provenance']['status'] not in CHECKED:return _refuse(out,'missing','unverified_candidate')
        if req['version_policy']=='original_period_documents' and f['origin_role']!='reported_period':return _refuse(out,'missing','original_version_missing')
        ctx.source_proof(f,e,d);ctx.check_local_source(d);selected.append((f,e,d,org))
    if req['mode']=='historical':
        stamps=[available_from(d)for f,e,d,org in selected]
        if any(t is None for t in stamps):return _refuse(out,'missing','publication_unknown')
        if any(instant(req['as_of'])<t for t in stamps):return _refuse(out,'missing','not_yet_available')
    fs=[x[0]for x in selected]
    if len({(f['currency'],f['scale'])for f in fs})!=1:return _refuse(out,'conflict','incompatible_units')
    unit=req['result_unit']
    if unit['kind']=='amount':
        if unit['currency']!=fs[0]['currency']:return _refuse(out,'unsupported','currency_conversion_not_supported')
        if op!='scale_v1' and unit['scale']!=fs[0]['scale']:return _refuse(out,'conflict','incompatible_units')
    comp=req['comparability_id'];records={r['comparability_id']:r for r in ctx.admission['comparability_records']}
    if comp is not None:need(comp in records,'unknown_comparability_id')
    if op in {'absolute_change_v1','relative_change_v1'}:
        if len({(f['metric_id'],f['definition_id'])for f in fs})!=1:return _refuse(out,'conflict','definition_mismatch')
        if not comparable(fs[0]['period'],fs[1]['period']):return _refuse(out,'conflict','incompatible_periods')
        if fs[0]['document_id']!=fs[1]['document_id']:
            if any(f['origin_role']!='reported_period'for f in fs):return _refuse(out,'conflict','incompatible_versions')
            if comp is None:return _refuse(out,'conflict','comparability_not_established')
            r=records[comp]
            if r['organization_id']!=req['organization_id'] or r['metric_id']!=fs[0]['metric_id'] or r['definition_id']!=fs[0]['definition_id'] or r['review_status'] not in CHECKED or r['documents']!=[dict(document_id=d['document_id'],version_id=d['version_id'],document_sha256=d['sha256'])for f,e,d,org in selected] or r['periods']!=[f['period']for f in fs]:return _refuse(out,'conflict','comparability_not_established')
        elif comp is not None:return _refuse(out,'conflict','comparability_not_established')
    elif comp is not None:return _refuse(out,'conflict','comparability_not_established')
    if op=='operating_margin_v1':
        if [f['metric_id']for f in fs]!=['operating_profit','revenue']:return _refuse(out,'conflict','definition_mismatch')
        if fs[0]['period']!=fs[1]['period']:return _refuse(out,'conflict','incompatible_periods')
        if fs[0]['document_id']!=fs[1]['document_id'] or fs[0]['version_id']!=fs[1]['version_id']:return _refuse(out,'conflict','incompatible_versions')
    gate=_retrieval_gate(ctx,req,selected,retrieval_gate,out)
    if gate is out:return out
    # No financial operation runs until every source/context/temporal/evidence gate above succeeds.
    values=[from_decimal(f['value'])for f in fs];inter={}
    if op=='direct_fact_v1':value=values[0]
    elif op in {'absolute_change_v1','relative_change_v1'}:
        if op=='relative_change_v1' and values[0][0]<=0:return _refuse(out,'unsupported','nonpositive_base')
        difference=sub(values[1],values[0]);inter['difference']=pair(difference)
        if op=='absolute_change_v1':value=difference
        else:inter['current_divided_by_previous']=pair(div(values[1],values[0]));value=mul(div(difference,values[0]),(100,1))
    elif op=='scale_v1':
        multiplier=rat(fs[0]['scale'],unit['scale']);inter['scale_multiplier']=pair(multiplier);value=mul(values[0],multiplier)
    else:
        if values[1][0]==0:return _refuse(out,'unsupported','zero_denominator')
        if values[1][0]<0:return _refuse(out,'unsupported','negative_revenue_denominator')
        quotient=div(values[0],values[1]);inter['profit_divided_by_revenue']=pair(quotient);value=mul(quotient,(100,1))
    display=fs[0]['value']if op=='direct_fact_v1'else finite_decimal(value)if unit['kind']=='amount'else rounded_percent(value)
    warnings=['exact_arithmetic_does_not_improve_source_precision','source_status_inherited_not_upgraded']
    if req['mode']=='snapshot' and any(d['publication']['precision']=='unknown'for f,e,d,org in selected):warnings.append('publication_unknown_snapshot_only')
    if any(d['data_origin']=='synthetic'for f,e,d,org in selected):warnings.append('own_synthetic_not_issuer_data')
    if any(d['rights']['status']=='unconfirmed'for f,e,d,org in selected):warnings.append('primary_document_redistribution_rights_unconfirmed')
    out.update(financial_status='answered',reason_code='ok',financial_result=dict(calculation_schema_version=VERSION,operation_id=op,formula=OPERATIONS[op]['formula'],formula_version='1.0',request=deepcopy(req),admission_context=dict(context_id=ctx.admission['context_id'],catalog_id=cat['catalog_id'],component_digests=deepcopy(ctx.admission['component_digests']),admission_digest=digest(ctx.admission)),inputs=[_snapshot(f,e,d,org,ref['role'])for ref,(f,e,d,org)in zip(req['inputs'],selected)],sources=[_source(e,d)for f,e,d,org in selected],intermediates=inter,exact_result=pair(value),display_value=display,result_unit=deepcopy(unit),rounding='exact_input_decimal'if op=='direct_fact_v1'else 'exact_finite_decimal'if unit['kind']=='amount'else 'HALF_UP_2_integer_exact',precision_note='Exact arithmetic on the supplied rounded source values; no extra source precision is established.',warnings=warnings,retrieval_resolution=gate))
    return out


def calculate(ctx,request,run_id='calculation-run',retrieval_gate=None):
    out=_base(request,run_id)
    try:
        result=_calculate(ctx,request,out,retrieval_gate);validate_outcome(result);return result
    except ClarificationRequired as exc:
        out.update(execution_status='awaiting_clarification',financial_status=None,reason_code='missing_fields',clarification_fields=list(exc.fields),financial_result=None)
    except (ContractError,ExtractionError,RetrievalError) as exc:
        code=exc.code
        if code in {'source_missing','source_version_mismatch'}:reason=code;subsystem='source'
        elif isinstance(exc,RetrievalError):reason='artifact_integrity_error';subsystem='retrieval'
        elif code.startswith(('context_','admission_','source_')) or code in {'bindings_required','source_checks_required'}:reason='context_invalid';subsystem='admission'
        else:reason='input_invalid';subsystem='input'
        _technical(out,reason,subsystem,code)
    except OSError:_technical(out,'source_access_error','source','io_error')
    except ArithmeticError:_technical(out,'internal_error','calculation','arithmetic_invariant_failed')
    except (KeyError,TypeError,ValueError,AttributeError):_technical(out,'input_invalid','input','malformed_record')
    # Invalid caller IDs must not make even an error envelope invalid.
    from .contracts_v2 import identifier
    for key,fallback in [('request_id','invalid-request'),('run_id','invalid-run')]:
        try:identifier(out[key])
        except ContractError:out[key]=fallback
    validate_outcome(out);return out


def validate_calculation_binding(out,ctx,request,retrieval_gate=None):
    """Re-resolve and re-execute registered code, never use a supplied result as input.

    This is runtime output validation, not the independent evaluation oracle.
    It also checks refusals: changing a refusal into an answer or vice versa fails.
    """
    validate_outcome(out)
    expected=calculate(ctx,request,out['run_id'],retrieval_gate)
    need(out==expected,'calculation_binding_mismatch')
