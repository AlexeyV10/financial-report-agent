"""Offline suite integrity and dependency audit. No answering/parser/model imports."""
from collections import Counter,defaultdict
from fractions import Fraction
from decimal import Decimal,localcontext,ROUND_HALF_UP
from .common import exact,require,digest,ident

def semantic_key(c):
    source=c['source']
    if c['target']=='service':value=dict(fields=source['form']['fields'],assumptions=source['form']['assumptions'])
    elif c['target']=='calculator_v03':value={k:v for k,v in source['request'].items()if k not in {'request_id','original_question'}}
    else:value=source
    return digest(dict(profile=c['profile'],target=c['target'],value=value))

def validate_suite(inputs,gold,protocol):
    exact(inputs,'schema_version suite_id known_to_developer reserved_unseen_real cases');require(inputs['schema_version']=='kp3-suite-0.1'and inputs['known_to_developer']is True and inputs['reserved_unseen_real']==0,'suite_version_or_scope')
    exact(gold,'schema_version suite_digest oracle_dependencies cases');require(gold['schema_version']=='kp3-gold-0.1'and gold['suite_digest']==digest(inputs),'gold_binding_mismatch');require(protocol['suite_digest']==digest(inputs)and protocol['schema_version']=='kp3-protocol-0.1','protocol_binding_mismatch')
    ids=[c['case_id']for c in inputs['cases']];gids=[g['case_id']for g in gold['cases']];require(len(ids)==len(set(ids))and set(ids)==set(gids)and len(gids)==len(set(gids)),'duplicate_or_unknown_case_id')
    gs={g['case_id']:g for g in gold['cases']};semantic={};families=defaultdict(set);counts=Counter();categories=Counter();sources=defaultdict(set);economics=defaultdict(set);historical_overlap=[]
    for c in inputs['cases']:
        exact(c,'case_id suite split category profile target data_origin family known_to_developer source answers fault_id');ident(c['case_id']);require(c['known_to_developer']is True,'false_unseen_claim');require(c['suite']in {'financial','interface','scenario','robustness'},'unknown_suite');require(c['data_origin']in {'real','synthetic'},'invalid_origin');counts[(c['suite'],c['split'])]+=1;g=gs[c['case_id']]
        if c['suite']=='financial':
            exact(g,'case_id expected phase intent result inputs sources assumption_checks unfulfilled_requests required_clarification_fields constraints');exact(g['expected'],'execution_status request_status financial_status reason_code');families[c['family']].add(c['split']);key=semantic_key(c);require(key not in semantic,'duplicate_semantic_case');semantic[key]=c['case_id']
            isnum=g['expected']['financial_status']=='answered';require(isnum==(g['result']is not None),'gold_result_status_mismatch')
            if not isnum:require(g['result']is None and g['inputs']==[]and g['sources']==[],'hidden_number_in_refusal')
            else:
                require(g['expected']['execution_status']=='completed'and len(g['inputs'])==len(g['sources'])in {1,2},'gold_inputs_missing');require(g['result']['operation_id']==g['intent']['operation_id'],'gold_operation_mismatch')
                values=[Fraction(f['value'])for f in g['inputs']];op=g['result']['operation_id'];a=values
                if op=='direct_fact_v1':value=a[0]
                elif op=='absolute_change_v1':value=a[1]-a[0]
                elif op=='relative_change_v1':require(a[0]>0,'invalid_relative_gold');value=(a[1]-a[0])*100/a[0]
                elif op=='scale_v1':value=a[0]*Fraction(g['inputs'][0]['source_unit']['scale'],g['result']['result_unit']['scale'])
                elif op=='operating_margin_v1':require(a[1]>0,'invalid_margin_gold');value=a[0]*100/a[1]
                else:require(False,'unregistered_gold_operation')
                require(g['result']['exact_result']==dict(numerator=str(value.numerator),denominator=str(value.denominator)),'gold_numeric_mismatch')
                with localcontext()as context:
                    context.prec=80;decimal_value=Decimal(value.numerator)/Decimal(value.denominator)
                    if op in {'relative_change_v1','operating_margin_v1'}:decimal_value=decimal_value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                    require(Decimal(g['result']['display_value'])==decimal_value,'gold_display_mismatch')
                for f,s in zip(g['inputs'],g['sources']):
                    require(f['document_id']==s['document_id']and f['version_id']==s['version_id']and f['document_sha256']==s['document_sha256']and f['evidence_id']==s['evidence']['evidence_id'],'gold_source_context_mismatch')
                    require(f['locator']==s['evidence']['locator']and f['evidence_digest']==digest(s['evidence']),'gold_evidence_mismatch');require(f['source_unit']==dict(currency=s['evidence']['currency'],scale=s['evidence']['scale']),'gold_unit_mismatch')
                    sources[c['split']].add(f['document_id']);economics[c['split']].add(digest(dict({k:f[k]for k in ['organization_id','consolidation','accounting_standard','metric_id','definition_id','period']},currency=f['source_unit']['currency'])))
            if c['split']=='comparison_known':categories[c['category']]+=1;historical_overlap.append(c['case_id'])
            require(c['target']==('service'if c['profile']=='real05'else'calculator_v03'),'profile_target_mismatch')
        elif c['suite']=='interface':
            exact(g,'case_id expected fields required_clarification_fields assumptions');require(c['target']=='parser','parser_target_required')
        elif c['suite']=='scenario':
            require(c['target']=='scenario'and g['new_model_calls']==0,'scenario_scope_mismatch');require((g['expected']['status']=='completed')==(g['reference']is not None),'scenario_reference_status')
        else:exact(g,'case_id expected execution_on14');require(g['execution_on14']is False and c['fault_id']==c['source']['probe_id'],'robustness_plan_invalid')
    require(all(len(v)==1 for v in families.values()),'family_split_leakage')
    require(not(sources['dev_control']&sources['comparison_known'])and not(economics['dev_control']&economics['comparison_known']),'economic_split_leakage')
    require(dict(counts)=={('financial','dev_control'):20,('financial','comparison_known'):40,('interface','interface_control'):8,('scenario','scenario_control'):12,('robustness','robustness_control'):12},'suite_denominator_changed')
    require(dict(categories)==dict(direct=10,comparison=8,margin=6,scale=4,false_premise=4,refusal=8),'comparison_mix_changed')
    order=protocol['order'];attempts=[x['attempt_id']for x in order];require(len(attempts)==len(set(attempts))==138,'attempt_order_invalid')
    for row in order:
        exact(row,'attempt_id case_id method phase');ident(row['attempt_id']);require(row['case_id']in gs and row['case_id'].startswith('cmp-')and row['method']in {'B','A','C'}and row['phase']in {'primary','warm_repeat'},'unknown_planned_attempt')
    primary=[(x['case_id'],x['method'])for x in order if x['phase']=='primary'];require(len(primary)==120 and len(set(primary))==120,'primary_coverage_mismatch')
    require(sum(gs[x['case_id']]['result']is not None for x in order if x['phase']=='warm_repeat')==18,'warm_refusal_not_planned')
    return dict(schema_version='kp3-family-audit-0.1',suite_cases=len(ids),counts={a+':'+b:n for(a,b),n in counts.items()},comparison_categories=dict(categories),financial_numeric={s:sum(c['suite']=='financial'and c['split']==s and gs[c['case_id']]['result']is not None for c in inputs['cases'])for s in ['dev_control','comparison_known']},financial_refusals={s:sum(c['suite']=='financial'and c['split']==s and gs[c['case_id']]['result']is None for c in inputs['cases'])for s in ['dev_control','comparison_known']},financial_lineage_clusters={s:sorted(f for f,v in families.items()if s in v)for s in ['dev_control','comparison_known']},document_versions={s:sorted(v)for s,v in sources.items()},economic_contexts={s:len(v)for s,v in economics.items()},new_assignment_cross_split_overlap=0,historical_dev_overlap_comparison=historical_overlap,true_document_holdout=0,true_template_holdout=0,reserved_unseen_real=0,known_to_developer=True,interpretation='Known-corpus engineering comparison only; family clustering does not erase03-13 exposure')
