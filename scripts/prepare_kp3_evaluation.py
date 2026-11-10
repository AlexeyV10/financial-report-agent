"""Prepare declared known-corpus tasks/gold in a NEW private draft. Never obtain model answers."""
from copy import deepcopy as cp
from pathlib import Path
import argparse,importlib.util,random,sys
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_protocol_v1.common import read,write_new,digest,require

METRICS={'revenue':'выручка','operating_profit':'операционная прибыль','operating_cash_flow':'чистый операционный денежный поток'}
OPS={'direct_fact_v1':('fact',),'scale_v1':('fact',),'absolute_change_v1':('previous','current'),'relative_change_v1':('previous','current'),'operating_margin_v1':('profit','revenue')}
FORMULAS={'direct_fact_v1':'selected reported value','absolute_change_v1':'current - previous','relative_change_v1':'(current - previous) / previous * 100','scale_v1':'value * source_scale / target_scale','operating_margin_v1':'operating_profit / revenue * 100'}

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def prepare(directory):
    directory=directory.resolve();require(directory.is_relative_to((ROOT/'tmp').resolve())and not directory.exists(),'new_private_draft_required')
    directory.mkdir();real=read(ROOT/'data/catalogs/kp3_corpus_v1/runtime_catalog.json');own=read(ROOT/'data/catalogs/kp3_calculator_dev_v1/runtime_catalog.json');ref=module('reference07','evaluation/reference/kp3_calculator_v1/oracle.py');sref=module('reference12','evaluation/reference/kp3_scenario_v1/oracle.py');dataset=read(ROOT/'data/scenarios/kp3_scenario_v1/dataset.json');cases=[];gold=[]
    def add(cid,suite,split,category,profile,target,origin,family,source,g,answers=None,fault=None):
        cases.append(dict(case_id=cid,suite=suite,split=split,category=category,profile=profile,target=target,data_origin=origin,family=family,known_to_developer=True,source=source,answers=answers or [],fault_id=fault));gold.append(dict(case_id=cid,**g))
    def pick(cat,doc,metric,role='reported_period'):return next(f for f in cat['facts']if f['document_id']==doc and f['metric_id']==metric and f['origin_role']==role)
    def financial(cid,cat,fs,op,category,scale=None,assumption=None,overrides=None,refusal=None):
        ds={d['document_id']:d for d in cat['documents']};ev={e['evidence_id']:e for e in cat['evidence']};isreal=cat is real
        mids=['operating_profit','revenue']if op=='operating_margin_v1'else[fs[0]['metric_id']];defs=[next(f['definition_id']for f in fs if f['metric_id']==m)for m in mids]
        periods=[f['period']for f in fs]if op in {'absolute_change_v1','relative_change_v1'}else[fs[0]['period']]
        documents=list({f['document_id']:dict(document_id=f['document_id'],version_id=f['version_id'])for f in fs}.values());unit=dict(currency=fs[0]['currency'],scale=fs[0]['scale']);percent=op in {'relative_change_v1','operating_margin_v1'};result_unit=dict(kind='percent')if percent else dict(kind='amount',currency=unit['currency'],scale=scale or unit['scale'])
        question='Параметры финансового вопроса явно заданы в структурированной форме.'
        assumptions=[]
        if assumption:
            question='Почему '+METRICS[fs[0]['metric_id']]+' '+assumption+'? Рассчитай '+('относительное'if op=='relative_change_v1'else'абсолютное')+' изменение. '+question
            assumptions=[dict(kind='direction',asserted_direction='increase'if assumption=='выросла'else'decrease',text_fragment=assumption,requires_check=True,why_requested=True)]
        fields=dict(organization=fs[0]['organization_id'],consolidation='group',accounting_standard='IFRS',operation_id=op,metric_ids=mids,definition_ids=defs,periods=cp(periods),documents=cp(documents),version_policy='explicit_versions',source_unit=cp(unit),result_unit=result_unit,mode='snapshot',as_of=None,comparability_id=None)
        fields.update(cp(overrides or {}));refs=[dict(role=role,**{k:cp(f[k])for k in ['fact_id','document_id','version_id','metric_id','definition_id','period']},source_unit=dict(currency=f['currency'],scale=f['scale']))for role,f in zip(OPS[op],fs)]
        request=dict(schema_version='0.3',request_id=cid,original_question=question,operation_id=op,organization_id=fields['organization'],consolidation=fields['consolidation'],accounting_standard=fields['accounting_standard'],inputs=refs,version_policy=fields['version_policy'],comparability_id=None,result_unit=cp(fields['result_unit']),mode=fields['mode'],as_of=fields['as_of'])
        source=dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id=cid,original_question=question,fields=fields,assumptions=assumptions))if isreal else dict(kind='calculation',request=request)
        result=None;inputs=[];sources=[];checks=[]
        if refusal:execution,reqstatus,financial_status,reason,phase=refusal
        else:
            expected=ref.evaluate(op,[f['value']for f in fs],unit['scale'],fields['result_unit'].get('scale',unit['scale']));execution='completed';reqstatus='resolved';financial_status=expected['status'];reason='ok'if financial_status=='answered'else expected['reason'];phase='answer'if financial_status=='answered'else'calculation'
            if financial_status=='answered':
                inter={};v=[Fraction(f['value'])for f in fs];pair=lambda x:dict(numerator=str(x.numerator),denominator=str(x.denominator))
                if op in {'absolute_change_v1','relative_change_v1'}:inter['difference']=pair(v[1]-v[0])
                if op=='relative_change_v1':inter['current_divided_by_previous']=pair(v[1]/v[0])
                if op=='scale_v1':inter['scale_multiplier']=pair(Fraction(unit['scale'],fields['result_unit']['scale']))
                if op=='operating_margin_v1':inter['profit_divided_by_revenue']=pair(v[0]/v[1])
                warnings=['exact_arithmetic_does_not_improve_source_precision','source_status_inherited_not_upgraded']
                if any(ds[f['document_id']]['publication']['precision']=='unknown'for f in fs):warnings.append('publication_unknown_snapshot_only')
                if not isreal:warnings.append('own_synthetic_not_issuer_data')
                if any(ds[f['document_id']]['rights']['status']=='unconfirmed'for f in fs):warnings.append('primary_document_redistribution_rights_unconfirmed')
                result=dict(operation_id=op,formula=FORMULAS[op],formula_version='1.0',intermediates=inter,exact_result=expected['exact_result'],display_value=expected['display_value'],result_unit=cp(fields['result_unit']),rounding='HALF_UP_2_integer_exact'if percent else'exact_input_decimal'if op=='direct_fact_v1'else'exact_finite_decimal',warnings=warnings)
                for role,f in zip(OPS[op],fs):
                    e=ev[f['evidence_id']];d=ds[f['document_id']]
                    inputs.append(dict(role=role,**{k:cp(f[k])for k in ['fact_id','organization_id','document_id','version_id','metric_id','definition_id','period','value','origin_role','provenance','evidence_id','evidence_digest']},document_sha256=d['sha256'],source_unit=dict(currency=f['currency'],scale=f['scale']),raw_value=e['raw_value'],numeric_encoding=e['numeric_encoding'],locator=cp(e['locator']),consolidation='group',accounting_standard='IFRS'))
                    url=None if not d['document_url']else d['document_url']+('#page='+str(e['locator']['pdf_page'])if e['locator']['kind']=='pdf'else'')
                    sources.append(dict(evidence=cp(e),**{k:cp(d[k])for k in ['document_id','version_id','data_origin','audit','rights','publication']},source_url=url,document_sha256=d['sha256']))
        if isreal and phase in {'answer','calculation'}:reqstatus='evaluated'
        for a in assumptions:
            observed=None if result is None else'increase'if ref.evaluate('absolute_change_v1',[f['value']for f in fs],unit['scale'],unit['scale'])['exact_result']['numerator'][0]!='-'else'decrease'
            checks.append(dict(assumption=a,status='not_checked'if observed is None else'supported'if a['asserted_direction']==observed else'contradicted',observed_direction=observed,explanation_status='not_supported'))
        add(cid,'financial','comparison_known'if isreal else'dev_control',category,'real05'if isreal else'own07','service'if isreal else'calculator_v03','real'if isreal else'synthetic','real-lineage-'+fs[0]['organization_id']if isreal else'own07-lineage',source,dict(expected=dict(execution_status=execution,request_status=reqstatus,financial_status=financial_status,reason_code=reason),phase=phase,intent=fields,result=result,inputs=inputs,sources=sources,assumption_checks=checks,unfulfilled_requests=['causal_explanation_not_supported']if assumptions else[],required_clarification_fields=[],constraints=['publication_unknown_snapshot_only','assistant_checked_not_human','source_precision_not_improved']if isreal else['own_synthetic_not_issuer_data']))
    #20 distinct own07 method controls; no fabricated PDF/search/model path for these inputs.
    n=1
    for f in own['facts']:financial(f'dev-{n:02}',own,[f],'direct_fact_v1','direct');n+=1
    for op in ['absolute_change_v1','relative_change_v1']:
        for m in METRICS:financial(f'dev-{n:02}',own,[pick(own,'method-synthetic-2024',m,'comparative_period'),pick(own,'method-synthetic-2024',m)],op,'comparison');n+=1
    for doc,role in [('method-synthetic-2023','reported_period'),('method-synthetic-2024','reported_period'),('method-synthetic-2024','comparative_period')]:financial(f'dev-{n:02}',own,[pick(own,doc,m,role)for m in ['operating_profit','revenue']],'operating_margin_v1','margin');n+=1
    for m in ['revenue','operating_cash_flow']:financial(f'dev-{n:02}',own,[pick(own,'method-synthetic-2024',m)],'scale_v1','scale',scale=1000);n+=1
    require(n==21,'dev_count')
    #32 numeric real cases. These selectors are authored here, never taken from parser/answers.
    selections=[('phosagro-2023','revenue','comparative_period'),('phosagro-2024','revenue','reported_period'),('phosagro-2025','operating_profit','reported_period'),('phosagro-2025-q1','operating_cash_flow','reported_period'),('phosagro-2025-h1','revenue','reported_period'),('phosagro-2025-9m','operating_cash_flow','reported_period'),('segezha-2021','operating_profit','reported_period'),('segezha-2022','operating_cash_flow','reported_period'),('segezha-2021','operating_cash_flow','reported_period'),('segezha-2022','operating_cash_flow','comparative_period')]
    n=1
    for d,m,r in selections:financial(f'cmp-{n:02}',real,[pick(real,d,m,r)],'direct_fact_v1','direct');n+=1
    pairs=[('phosagro-2023','revenue','absolute_change_v1'),('phosagro-2024','operating_profit','absolute_change_v1'),('phosagro-2025','operating_cash_flow','relative_change_v1'),('phosagro-2025-q1','revenue','relative_change_v1'),('phosagro-2025-h1','operating_profit','absolute_change_v1'),('phosagro-2025-9m','operating_cash_flow','relative_change_v1'),('segezha-2021','revenue','relative_change_v1'),('segezha-2022','operating_profit','absolute_change_v1')]
    for d,m,op in pairs:financial(f'cmp-{n:02}',real,[pick(real,d,m,r)for r in ['comparative_period','reported_period']],op,'comparison');n+=1
    for d in ['phosagro-2024','phosagro-2025','phosagro-2025-q1','phosagro-2025-h1','segezha-2021','segezha-2022']:financial(f'cmp-{n:02}',real,[pick(real,d,m)for m in ['operating_profit','revenue']],'operating_margin_v1','margin');n+=1
    for d,m,s in [('phosagro-2023','operating_profit',1000000000),('phosagro-2025-h1','revenue',1),('segezha-2021','operating_cash_flow',1000000000),('segezha-2022','revenue',1000000000)]:financial(f'cmp-{n:02}',real,[pick(real,d,m)],'scale_v1','scale',scale=s);n+=1
    for d,m,asserted,op in [('phosagro-2024','revenue','снизилась','absolute_change_v1'),('phosagro-2023','operating_cash_flow','выросла','relative_change_v1'),('segezha-2022','operating_profit','выросла','relative_change_v1'),('phosagro-2025-q1','operating_cash_flow','снизилась','absolute_change_v1')]:financial(f'cmp-{n:02}',real,[pick(real,d,m,r)for r in ['comparative_period','reported_period']],op,'false_premise',assumption=asserted);n+=1
    require(n==33,'numeric_count')
    for d,m in [('phosagro-2024','revenue'),('segezha-2022','operating_cash_flow')]:financial(f'cmp-{n:02}',real,[pick(real,d,m)],'direct_fact_v1','refusal',overrides=dict(mode='historical',as_of='2026-11-10T12:00:00+03:00'),refusal=('completed','missing',None,'publication_unknown','search'));n+=1
    f=pick(real,'segezha-2021','operating_cash_flow');ds={d['document_id']:d for d in real['documents']}
    financial('cmp-35',real,[f],'direct_fact_v1','refusal',overrides=dict(documents=[dict(document_id=k,version_id=ds[k]['version_id'])for k in ['segezha-2021','segezha-2022']],source_unit=None),refusal=('completed','conflict',None,'duplicate_or_conflicting_facts','catalog_filters'))
    f=pick(real,'phosagro-2024','revenue');p=dict(kind='duration',duration_type='full_year',start='2026-01-01',end='2026-12-31')
    financial('cmp-36',real,[f],'direct_fact_v1','refusal',overrides=dict(periods=[p]),refusal=('completed','missing',None,'no_compatible_fact','catalog_filters'))
    financial('cmp-37',real,[f],'direct_fact_v1','refusal',overrides=dict(source_unit=dict(currency='RUB',scale=1000)),refusal=('completed','conflict',None,'incompatible_source_units','catalog_filters'))
    financial('cmp-38',real,[f],'scale_v1','refusal',overrides=dict(result_unit=dict(kind='amount',currency='USD',scale=1000000)),refusal=('completed','resolved','unsupported','currency_conversion_not_supported','calculation'))
    financial('cmp-39',real,[pick(real,'phosagro-2023','revenue'),f],'relative_change_v1','refusal',overrides=dict(version_policy='original_period_documents'),refusal=('completed','resolved','conflict','comparability_not_established','calculation'))
    financial('cmp-40',real,[f],'direct_fact_v1','refusal',overrides=dict(accounting_standard='RAS',consolidation='legal_entity'),refusal=('completed','unsupported',None,'scope_not_supported','catalog_filters'))
    #8 independently specified input semantics, not parser output as gold.
    p24=cp(f['period']);p23=cp(p24);p23.update(start='2023-01-01',end='2023-12-31')
    interface=[('Какая выручка группы ФосАгро по МСФО за 2024 год из отчёта за 2024 год? Снимок.','resolved','ok',dict(operation_id='direct_fact_v1',organization='phosagro_group',periods=[p24],mode='snapshot'),[]),('На сколько процентов изменилась выручка группы ФосАгро по МСФО за 2023 и 2024 годы из отчёта за 2024 год? Снимок.','resolved','ok',dict(operation_id='relative_change_v1',periods=[p23,p24]),[]),('Рассчитай операционную маржу группы ФосАгро по МСФО за 2024 год из отчёта за 2024 год. Снимок.','resolved','ok',dict(operation_id='operating_margin_v1',metric_ids=['operating_profit','revenue']),[]),('Покажи выручку группы ФосАгро по МСФО за 2024 год из отчёта за 2024 год в млрд рублей. Снимок.','resolved','ok',dict(operation_id='scale_v1',result_unit=dict(kind='amount',currency='RUB',scale=1000000000)),[]),('Какая выручка по МСФО за 2024 год из отчёта за 2024 год? Снимок.','awaiting_clarification','missing_organization',dict(organization=None),['organization']),('На сколько изменилась выручка группы ФосАгро по МСФО за 2023 и 2024 годы из отчёта за 2024 год? Снимок.','awaiting_clarification','fields_required',dict(operation_id=None),['operation_id']),('Какая выручка группы ФосАгро по МСФО за 2024 год из отчёта за 2024 год на 2026-11-09?','awaiting_clarification','fields_required',dict(mode='historical',as_of=None),['as_of']),('Почему выручка группы ФосАгро по МСФО снизилась за 2023 и 2024 годы из отчёта за 2024 год? Снимок.','resolved','ok',dict(operation_id='absolute_change_v1',periods=[p23,p24]),[])]
    for i,(q,status,reason,fields,clarifications)in enumerate(interface,1):
        add(f'input-{i:02}','interface','interface_control','russian_input','real05','parser','real','interface-known-'+str(i),dict(kind='text',input_id=f'input-{i:02}',question=q),dict(expected=dict(binding_status=status,reason_code=reason),fields=fields,required_clarification_fields=clarifications,assumptions=[dict(asserted_direction='decrease',why_requested=True,requires_check=True)]if i==8 else[]))
    base=read(ROOT/'data/scenarios/kp3_scenario_v1/request_example.json');variants=[('signal',{},None,None,'completed','signal_true'),('no_signal',dict(threshold_pct='20'),None,None,'completed','signal_false'),('expenses',dict(fee_fixed='2.35',slippage_bps='10',lot_size=3),None,None,'completed','signal_true'),('weekend',{},'2025-06-07T12:00:00+03:00',None,'completed','signal_true'),('before_publication',{},'2025-06-04T18:30:00+03:00',None,'blocked','not_yet_available'),('missing_price',{},None,'own_price_gap','blocked','price_missing'),('no_future_open',{},'2025-06-09T18:00:00+03:00',None,'blocked','no_future_session_open'),('invalid_capital',dict(initial_cash='-1'),None,None,'error','invalid_capital')]
    for i,(name,changes,stamp,fault,status,reason)in enumerate(variants,1):
        req=cp(base);req['parameters'].update(changes)
        if stamp:req['decision_at']=stamp
        signal=None if status!='completed'else reason=='signal_true';reference=None
        if signal is not None:reference={k:sref.reference(dataset,req,trade)for k,trade in [('scenario',signal),('cash',False),('hold',True)]}
        add(f'scenario-{i:02}','scenario','scenario_control',name,'own12','scenario','synthetic','own12-lineage',dict(kind='scenario',request=req),dict(expected=dict(status=status,reason_code=reason),signal=signal,reference=reference,label='ИСКУССТВЕННЫЕ ДАННЫЕ / ВИРТУАЛЬНЫЙ СЦЕНАРИЙ',new_model_calls=0),fault=fault)
    for i,d in enumerate(['phosagro-2024','phosagro-2025-h1','segezha-2021','segezha-2022'],9):
        fs=[pick(real,d,'revenue',r)for r in ['comparative_period','reported_period']];doc=ds[d];fields=dict(organization=doc['organization_id'],operation_id='relative_change_v1',metric_ids=['revenue'],periods=[f['period']for f in fs],documents=[dict(document_id=d,version_id=doc['version_id'])],mode='snapshot')
        add(f'scenario-{i:02}','scenario','scenario_control','real_readiness','real05','scenario','real','real-lineage-'+doc['organization_id'],dict(kind='real_readiness',financial_source=dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id=f'scenario-{i:02}',original_question='Проверить готовность реального источника; без подстановки цен.',fields=fields,assumptions=[])),decision_at='2026-11-10T12:00:00+03:00'),dict(expected=dict(status='blocked',reason_code='publication_unknown'),signal=None,reference=None,label='ПРОВЕРКА РЕАЛЬНОГО ИСТОЧНИКА / ТОРГОВЛИ НЕТ',new_model_calls=0,required_gaps=['publication_unknown','real_prices_unavailable','real_calendar_unavailable','corporate_actions_unchecked','price_rights_unconfirmed','real_execution_not_supported']))
    faults=[('unknown_id','reject_unregistered_reference'),('duplicate_id','reject_duplicate_reference'),('swapped_roles','reject_order_change'),('other_cell','reject_wrong_evidence'),('wrong_sha_page','reject_wrong_version_or_page'),('lost_header','reject_missing_unit_or_header'),('extra_claim','reject_extra_numerical_narrative'),('lost_claim','reject_incomplete_answer'),('automatic_candidate','no_checked_admission'),('changed_artifact','technical_not_financial_missing'),('untrusted_instruction','no_execution_or_value_injection'),('unknown_usage','preserve_unknown_not_zero')]
    for i,(fault,invariant)in enumerate(faults,1):add(f'robust-{i:02}','robustness','robustness_control',fault,'isolated_own_fixture','probe_plan','synthetic','robustness-'+fault,dict(kind='probe_plan',probe_id=fault),dict(expected=dict(invariant=invariant),execution_on14=False),fault=fault)
    inputs=dict(schema_version='kp3-suite-0.1',suite_id='kp3-known-corpus-v1',known_to_developer=True,reserved_unseen_real=0,cases=cases);goldfile=dict(schema_version='kp3-gold-0.1',suite_digest=digest(inputs),oracle_dependencies=['evaluation/reference/kp3_calculator_v1/oracle.py','evaluation/reference/kp3_scenario_v1/oracle.py'],cases=gold)
    rng=random.Random(20261110);ids=[f'cmp-{i:02}'for i in range(1,41)];rng.shuffle(ids);order=[]
    for i,cid in enumerate(ids):
        for m in (['A','C','B']if i%2==0 else['C','A','B']):order.append(dict(attempt_id=f'primary-{len(order)+1:03}',case_id=cid,method=m,phase='primary'))
    for cid in ['cmp-02','cmp-12','cmp-13','cmp-19','cmp-26','cmp-29']:
        for m in ['C','A','B']:order.append(dict(attempt_id=f'warm-{len(order)-119:02}',case_id=cid,method=m,phase='warm_repeat'))
    protocol=dict(schema_version='kp3-protocol-0.1',suite_digest=digest(inputs),design='controlled_comparison_on_known_corpus',seed=20261110,methods=['B','A','C'],order=order,primary_attempts=120,warm_attempts=18,max_attempts=138,max_model_requests=414,top_k=32,outer_timeout_s=180,retry_policy='no_automatic_retries_keep_first_outcome',cold_warm='record_actual_setup_and_state_counterbalanced_A_C',answer_format='typed_registered_Answer_not_A_raw',dev_target='own07_calculator_v03_not_fabricated_B_search',reserved_unseen_real=0,actual_method_runs_on14=0,scope_gates=['nonfinancial_group_IFRS','same_exact_version_margin','no_unproven_cross_original_comparability','all8_real_publications_unknown','no_automatic_candidates','no_FX_or_pp_operation'])
    querymap={};querycases={};tags={'revenue':'выручка','operating_profit':'операционная прибыль','operating_cash_flow':'CFO'}
    for c,g in zip(cases,gold):
        if c['split']!='comparison_known'or g['result']is None:continue
        fs=g['inputs'];spec=dict(schema_version='kp3-search-0.1',query=' и '.join(dict.fromkeys(tags[f['metric_id']]for f in fs)),organization_id=g['intent']['organization'],consolidation='group',accounting_standard='IFRS',metrics=list({f['metric_id']:dict(metric_id=f['metric_id'],definition_id=f['definition_id'])for f in fs}.values()),periods=list({digest(f['period']):f['period']for f in fs}.values()),documents=list({f['document_id']:dict(document_id=f['document_id'],version_id=f['version_id'])for f in fs}.values()),source_units=list({digest(f['source_unit']):f['source_unit']for f in fs}.values()),version_policy=g['intent']['version_policy'],mode='snapshot',as_of=None,top_k=32)
        key='query-'+digest(spec)[:20];querycases[c['case_id']]=key;querymap.setdefault(key,dict(query_id=key,spec=spec,required_evidence=[s['evidence']for s in g['sources']]))
    search_tasks=dict(schema_version='kp3-search-suite-0.1',queries=[dict(query_id=k,spec=v['spec'])for k,v in querymap.items()]);retrieval_gold=dict(schema_version='kp3-search-gold-0.1',tasks_digest=digest(search_tasks),queries=list(querymap.values()),case_to_query=querycases)
    protocol['retrieval_unique_queries']=len(querymap)
    model=read(ROOT/'data/config/local_model.json');protocol['model']={k:model[k]for k in ['model','model_digest','server_version','endpoint','cloud_enabled','executable_sha256']}
    protocol['versions']=dict(Catalog='0.2',Calculation='0.3',Input='kp3-input-0.1',B='kp3-answer-0.1',C='kp3-answer-0.2',A='kp3-a-answer-0.1',scenario='kp3-scenario-outcome-0.1',history='kp3-history-0.1',C_prompt='bounded-financial-tools-v2',A_prompt='one-shot-financial-selection-v1')
    protocol['limits']=dict(C=dict(max_calls=8,timeout_s=180,per_call_s=60,max_search_results=32,max_output_tokens=384,max_action_bytes=4096,max_observation_bytes=32768,max_tool_bytes=8192),A=dict(timeout_s=180,per_call_s=60,top_k=32,max_output_tokens=384,max_choice_bytes=4096,max_observation_bytes=32768),B=dict(outer_timeout_s=180,model_calls=0))
    protocol['budget']=dict(max_A_requests=46,max_C_requests=368,max_chat_requests=414,max_output_tokens=158976,max_model_input_context_per_call=8192,max_serial_wall_s=24840,unknown_usage_policy='keep_unknown_and_conservatively_reserve_remaining_per_method_cap',new_actual_calls_authorized_on14=False)
    protocol['metric_denominators']=dict(financial_primary_per_method=dict(attempts=40,numeric=32,refusal=8),warm_repeats_per_method=6,parser=8,scenario=dict(total=12,own=8,real_readiness=4),robustness=12,retrieval_queries=len(querymap),retrieval_required_evidence=sum(len(x['required_evidence'])for x in querymap.values()),source_lineage_clusters=2,reserved_unseen_real=0)
    protocol['fault_registry']=dict([(name,dict(profile='isolated_own_fixture',invariant=invariant,execution_on14=False))for name,invariant in faults]+[('own_price_gap',dict(profile='own12_copy_only',invariant='blocked_price_missing_no_partial_pnl',execution_on14=False))])
    protocol['input_policy']='Only case.source and case.answers enter registered methods; target/profile/fault setup is trusted; no evaluator gold/targets/expected/override sent to model'
    protocol['retrieval_profile']=dict(primary_kind='prepared',top_k=32,automatic='candidate_diagnostic_only_not_admitted',validation_rechecks='count_actual07_rechecks_separately')
    for name,obj in [('inputs',inputs),('gold',goldfile),('protocol',protocol),('search_tasks',search_tasks),('retrieval_gold',retrieval_gold)]:write_new(directory/(name+'.json'),obj)
    return dict(cases=len(cases),gold=len(gold),draft=str(directory),production_answers=0,model_calls=0)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--draft',type=Path,required=True);print(prepare(p.parse_args().draft))
