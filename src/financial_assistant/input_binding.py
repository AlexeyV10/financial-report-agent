"""Resolve a partial input to Request0.3. No financial formulas, PDF parsing, model or service."""
from copy import deepcopy
from itertools import product
from .calculation_contracts import OPERATIONS,validate_request
from .catalog import validate_catalog
from .contracts_v2 import CHECKED,ContractError,digest,need
from .input_contracts import validate_input
from .russian_input import LANGUAGE_VERSION,organizations


def _choices(values):return [dict(value=deepcopy(v),label=str(label))for v,label in values]


def resolve_input(task,catalog,dictionary):
    out=dict(schema_version='kp3-binding-0.1',status='error',reason_code='invalid_input',normalized_input=deepcopy(task),clarifications=[],request=None,assumptions=[],calculations_performed=False,financial_status=None)
    try:return _resolve(out,catalog,dictionary)
    except ContractError as e:out.update(status='error',reason_code=e.code,request=None);return out
    except (ValueError,KeyError,TypeError,AttributeError):out.update(status='error',reason_code='malformed_input',request=None);return out


def _resolve(out,cat,dictionary):
    t=out['normalized_input'];validate_input(t);validate_catalog(cat)
    need(t['catalog_digest']==digest(cat),'catalog_changed');need(t['language_version']==LANGUAGE_VERSION,'language_version_mismatch')
    need(dictionary['dictionary_version']=='1.0','unsupported_dictionary_version')
    definitions={d['definition_id']:d for d in dictionary['definitions']};need(len(definitions)==len(dictionary['definitions']),'duplicate_definition_id')
    f=t['fields'];out['assumptions']=deepcopy(t['assumptions'])
    def put(key,value,origin='catalog_unique'):
        f[key]=deepcopy(value);t['field_origins'][key]=origin;t['issues']=[i for i in t['issues']if i['field']!=key]
    def stop(status,reason):out.update(status=status,reason_code=reason,request=None);return out
    def ask(key,code,message,values=()):
        out['clarifications'].append(dict(field=key,code=code,message=message,options=_choices(values)))
        if not any(i['field']==key and i['code']==code for i in t['issues']):t['issues'].append(dict(field=key,code=code,message=message))
    if t['unsupported_reasons']:return stop('unsupported',t['unsupported_reasons'][0])
    # Catalog metadata can resolve a uniquely determined context; provenance is visible.
    orgs=organizations(cat,f['organization'])if f['organization']else []
    if len(orgs)!=1:
        code='ambiguous_organization'if len(orgs)>1 or any(i['code']=='ambiguous_organization'for i in t['issues'])else 'unknown_organization'if f['organization']or t['hints']['organization_unmatched']else 'missing_organization'
        ask('organization',code,'Выберите одну организацию из подготовленного каталога.',[(o['organization_id'],o['name'])for o in cat['organizations']])
        t['issues']=[i for i in t['issues']if i['field']!='organization']+[dict(field='organization',code=code,message='Имя не разрешено однозначно.')]
        return stop('awaiting_clarification',code)
    org=orgs[0]
    if f['organization']!=org['organization_id']:put('organization',org['organization_id'],t['field_origins']['organization'])
    if f['consolidation']is None:put('consolidation',org['consolidation'])
    if f['accounting_standard']is None and len(org['accounting_standards'])==1:put('accounting_standard',org['accounting_standards'][0])
    if f['consolidation']!='group' or f['accounting_standard']not in {None,'IFRS'}:return stop('unsupported','scope_not_supported')
    if f['accounting_standard']is None:ask('accounting_standard','standard_required','Выберите стандарт.',[(s,s)for s in org['accounting_standards']])
    op=f['operation_id']
    if op is None:
        changes=any(i['code']in {'ambiguous_change','multiple_operations'}for i in t['issues'])
        ask('operation_id','operation_required','Уточните действие: сумма, разность, процент, масштаб или маржа.',[(k,v['plan_name'])for k,v in OPERATIONS.items()if not changes or k in {'absolute_change_v1','relative_change_v1'}])
    elif op not in OPERATIONS:return stop('unsupported','unsupported_operation')
    if op=='operating_margin_v1'and f['metric_ids']is None:put('metric_ids',['operating_profit','revenue'],'operation')
    mids=f['metric_ids'];metrics={m['metric_id']:m for m in cat['metrics']}
    if mids is None:ask('metric_ids','metric_required','Выберите показатель.',[([k],m['label'])for k,m in metrics.items()])
    elif any(m not in metrics for m in mids):return stop('unsupported','unsupported_metric')
    elif (op=='operating_margin_v1'and mids!=['operating_profit','revenue'])or(op and op!='operating_margin_v1'and len(mids)!=1):return stop('conflict','metric_operation_mismatch')
    if mids:
        possible=[[d for d in definitions.values()if d['metric_id']==m and d['accounting_standard']=='IFRS'and d['consolidation']=='group'and d['organization_type']=='nonfinancial']for m in mids]
        if f['definition_ids']is None:
            if all(len(p)==1 for p in possible):put('definition_ids',[p[0]['definition_id']for p in possible])
            else:ask('definition_ids','definition_ambiguous','Выберите версию определения для каждого показателя.',[(list(ids),' / '.join(ids))for ids in product(*[[d['definition_id']for d in p]for p in possible])])
        else:
            need(all(d in definitions for d in f['definition_ids']),'unknown_definition_id')
            if len(f['definition_ids'])!=len(mids)or any(definitions[d]['metric_id']!=m for d,m in zip(f['definition_ids'],mids)):return stop('conflict','definition_mismatch')
    count=2 if op in {'absolute_change_v1','relative_change_v1'}else 1
    periods=f['periods']
    if periods is None:
        available={digest(x['period']):x['period']for x in cat['facts']if x['organization_id']==org['organization_id']and(not mids or x['metric_id']in mids)and(not t['hints']['years']or int(x['period'].get('start',x['period'].get('date','0000'))[:4])in t['hints']['years'])}
        opts=list(available.values())
        # Bare years only resolve when each year has exactly one known full window.
        year_options=[[p for p in opts if p.get('start','')[:4]==str(y)]for y in t['hints']['years']]
        if op and len(year_options)==count and all(len(p)==1 for p in year_options):put('periods',[p[0]for p in year_options]);periods=f['periods']
        else:ask('periods','period_required','Укажите полные периоды и порядок previous/current; накопленный период и квартал различаются.',[([p],str(p))for p in opts])
    if periods:
        if len(periods)!=count and op:ask('periods','wrong_period_count','Для этого действия нужен другой набор полных периодов.')
        if any(p['kind']!='duration'or p['duration_type']not in {'full_year','year_to_date','quarter'}for p in periods):return stop('unsupported','period_type_not_supported')
        if len(periods)==2:
            from .financial_calculator import comparable
            if not comparable(*periods):return stop('conflict','incompatible_periods')
    if f['mode']is None:ask('mode','mode_required','Выберите снимок документа или анализ на дату.',[('snapshot','Снимок документа'),('historical','Что было известно на дату')])
    if f['mode']=='historical'and f['as_of']is None:ask('as_of','as_of_required','Укажите момент YYYY-MM-DDTHH:MM:SS±HH:MM; дата/подпись отчёта его не заменяют.')
    if f['mode']=='snapshot'and f['as_of']is not None:return stop('conflict','as_of_requires_historical')
    docs={d['document_id']:d for d in cat['documents']};chosen=f['documents']
    if chosen:
        for ref in chosen:
            need(ref['document_id']in docs,'unknown_document_id');d=docs[ref['document_id']];need(ref['version_id']==d['version_id'],'document_version_mismatch')
            if d['organization_id']!=org['organization_id']or d['accounting_standard']!=f['accounting_standard']:return stop('conflict','document_context_mismatch')
        if f['version_policy']is None:put('version_policy','explicit_versions')
    if t['hints']['document_report_year']and chosen is None:
        ds=[d for d in cat['documents']if d['organization_id']==org['organization_id']and d['report_period']['kind']=='duration'and d['report_period']['duration_type']=='full_year'and int(d['report_period']['start'][:4])==t['hints']['document_report_year']]
        if not ds:return stop('missing','source_report_not_in_catalog')
        if len(ds)==1:put('documents',[dict(document_id=ds[0]['document_id'],version_id=ds[0]['version_id'])]);chosen=f['documents']
        else:ask('documents','source_report_ambiguous','Уточните exact-версию запрошенного отчёта.',[([dict(document_id=d['document_id'],version_id=d['version_id'])],d['document_id'])for d in ds])
    if chosen and t['hints']['document_report_year']and any(docs[r['document_id']]['report_period'].get('start','')[:4]!=str(t['hints']['document_report_year'])for r in chosen):return stop('conflict','source_report_year_mismatch')
    if f['version_policy']is None:ask('version_policy','version_policy_required','Выберите точные версии или исходные отчёты соответствующих периодов.',[('explicit_versions','Явно выбранные версии'),('original_period_documents','Исходные документы периодов')])
    if out['clarifications']:return stop('awaiting_clarification','fields_required')
    # Match the exact complete financial context. Values are not used in lookup or options.
    requests=[(mids[0],f['definition_ids'][0],p)for p in periods]if op!='operating_margin_v1'else [(m,d,periods[0])for m,d in zip(mids,f['definition_ids'])]
    candidates=[];selected_ids={x['document_id']for x in chosen}if chosen else None
    for mid,did,p in requests:
        rows=[x for x in cat['facts']if x['organization_id']==org['organization_id']and x['metric_id']==mid and x['definition_id']==did and x['period']==p and(not selected_ids or x['document_id']in selected_ids)and(f['version_policy']!='original_period_documents'or x['origin_role']=='reported_period')and(f['source_unit']is None or {k:x[k]for k in ['currency','scale']}==f['source_unit'])]
        candidates.append(rows)
    if any(not rows for rows in candidates):
        if f['source_unit']is not None:
            for (mid,did,p),rows in zip(requests,candidates):
                if not rows and any(x['organization_id']==org['organization_id']and x['metric_id']==mid and x['definition_id']==did and x['period']==p and(not selected_ids or x['document_id']in selected_ids)for x in cat['facts']):return stop('conflict','incompatible_source_units')
        return stop('missing','no_compatible_fact')
    if any(len(rows)>1 for rows in candidates):
        if chosen:
            return stop('conflict','duplicate_or_conflicting_facts')
        ds={x['document_id']:docs[x['document_id']]for rows in candidates for x in rows}
        ask('documents','version_ambiguous','Есть несколько exact-версий; сравнительная колонка не является первоначальным отчётом.',[([dict(document_id=d['document_id'],version_id=d['version_id'])],d['document_id']+' / '+d['version_id'])for d in ds.values()]);return stop('awaiting_clarification','version_ambiguous')
    fs=[rows[0]for rows in candidates];evs={e['evidence_id']:e for e in cat['evidence']}
    if len({(x['currency'],x['scale'])for x in fs})!=1:return stop('conflict','incompatible_source_units')
    for x in fs:
        e=evs.get(x['evidence_id']);d=docs[x['document_id']]
        if x['value']is None or x['provenance']['status']not in CHECKED or e is None or e['provenance']['status']not in CHECKED or d['preparation_status']not in {'ready','checked'}:return stop('missing','unverified_candidate')
    unit=dict(currency=fs[0]['currency'],scale=fs[0]['scale'])
    if f['source_unit']is None:put('source_unit',unit)
    if f['documents']is None:put('documents',list({x['document_id']:dict(document_id=x['document_id'],version_id=x['version_id'])for x in fs}.values()))
    if f['result_unit']is None:
        if op=='scale_v1':ask('result_unit','target_unit_required','Выберите валюту и масштаб результата; FX не поддерживается.',[(dict(kind='amount',currency=unit['currency'],scale=s),'x'+str(s)+' '+unit['currency'])for s in [1,1000,1000000,1000000000]]);return stop('awaiting_clarification','target_unit_required')
        put('result_unit',dict(kind='percent')if OPERATIONS[op]['result_kind']=='percent'else dict(kind='amount',**unit),'operation'if OPERATIONS[op]['result_kind']=='percent'else 'catalog_unique')
    roles=OPERATIONS[op]['roles']
    refs=[dict(role=role,**{k:deepcopy(x[k])for k in ['fact_id','document_id','version_id','metric_id','definition_id','period']},source_unit=dict(currency=x['currency'],scale=x['scale']))for role,x in zip(roles,fs)]
    req=dict(schema_version='0.3',request_id=t['input_id'],original_question=t['original_question'],operation_id=op,organization_id=org['organization_id'],consolidation=f['consolidation'],accounting_standard=f['accounting_standard'],inputs=refs,version_policy=f['version_policy'],comparability_id=f['comparability_id'],result_unit=f['result_unit'],mode=f['mode'],as_of=f['as_of'])
    validate_request(req);out.update(status='resolved',reason_code='ok',request=req);validate_input(t);return out


def probe_adapter(ctx,binding,retrieval_gate=None):
    """Narrow explicit integration probe, not a router/service. Re-resolve before using any request."""
    from .financial_calculator import calculate,validate_calculation_binding
    fresh=resolve_input(binding['normalized_input'],ctx.catalog,ctx.dictionary)
    need(binding==fresh,'input_binding_mismatch');need(fresh['status']=='resolved','input_not_resolved')
    outcome=calculate(ctx,fresh['request'],retrieval_gate=retrieval_gate);validate_calculation_binding(outcome,ctx,fresh['request'],retrieval_gate)
    checks=[]
    for assumption in fresh['assumptions']:
        result=dict(assumption=deepcopy(assumption),status='not_checked',observed_direction=None,explanation_status='not_supported'if assumption['why_requested']else 'not_requested')
        if outcome['financial_status']=='answered'and fresh['request']['operation_id']in {'absolute_change_v1','relative_change_v1'}:
            n=int(outcome['financial_result']['intermediates']['difference']['numerator']);direction='increase'if n>0 else 'decrease'if n<0 else 'unchanged'
            result.update(status='supported'if direction==assumption['asserted_direction']else 'contradicted',observed_direction=direction)
        checks.append(result)
    return dict(probe_schema='kp3-input-probe-0.1',binding=fresh,outcome=outcome,assumption_checks=checks,unfulfilled_requests=deepcopy(fresh['normalized_input']['unfulfilled_requests']),service_created=False)


def syntax_status(task):
    validate_input(task)
    return 'unsupported'if task['unsupported_reasons']else 'awaiting_clarification'if task['issues']else 'parsed'
