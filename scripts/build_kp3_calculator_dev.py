"""Reproduce open calculator dev inputs/reference gold; never imports the production calculator."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads((ROOT/p).read_text(encoding='utf8'))
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(p,v):
    dest=ROOT/p;dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')


def admission(cat,dictionary,bindings=None,checks=None,comparability_records=None):
    return dict(admission_version='1.0',context_id=cat['catalog_id']+'-calculator-v1',data_origin=cat['documents'][0]['data_origin'],catalog_id=cat['catalog_id'],component_digests={k:digest(v)for k,v in dict(catalog=cat,dictionary=dictionary,bindings=bindings,checks=checks).items()},resource_policy='required_for_real',comparability_records=comparability_records or [])


def request(cat,operation,facts,case_id,comp=None,target_scale=None,policy='explicit_versions'):
    roles={'direct_fact_v1':['fact'],'scale_v1':['fact'],'absolute_change_v1':['previous','current'],'relative_change_v1':['previous','current'],'operating_margin_v1':['profit','revenue']}[operation]
    refs=[dict(role=role,**{k:deepcopy(f[k]) for k in ['fact_id','document_id','version_id','metric_id','definition_id','period']},source_unit=dict(currency=f['currency'],scale=f['scale']))for role,f in zip(roles,facts)]
    unit=dict(kind='percent')if operation in {'relative_change_v1','operating_margin_v1'}else dict(kind='amount',currency=facts[0]['currency'],scale=target_scale or facts[0]['scale'])
    return dict(schema_version='0.3',request_id=case_id,original_question='Explicit structured dev request; no language parser.',operation_id=operation,organization_id=facts[0]['organization_id'],consolidation='group',accounting_standard='IFRS',inputs=refs,version_policy=policy,comparability_id=comp,result_unit=unit,mode='snapshot',as_of=None)


def real_cases(cat):
    cases=[]
    def add(op,fs,target=None):
        cid='real-'+str(len(cases)+1).zfill(3)
        cases.append(dict(case_id=cid,family=op,fixture_overrides=[],request=request(cat,op,fs,cid,target_scale=target)))
    for f in cat['facts']:
        add('direct_fact_v1',[f]);add('scale_v1',[f],1000000000)
    for d in cat['documents']:
        fs=[f for f in cat['facts']if f['document_id']==d['document_id']]
        for metric in ['revenue','operating_profit','operating_cash_flow']:
            pair=sorted([f for f in fs if f['metric_id']==metric],key=lambda f:f['period']['start'])
            for op in ['absolute_change_v1','relative_change_v1']:add(op,pair)
        for rv in [f for f in fs if f['metric_id']=='revenue']:
            op=next(f for f in fs if f['metric_id']=='operating_profit'and f['period']==rv['period'])
            add('operating_margin_v1',[op,rv])
    return cases


def own_synthetic():
    cat=read('data/catalogs/kp3_finance_dev_v1/runtime_catalog.json');cat['catalog_id']='kp3_calculator_dev_v1'
    # New explicitly own fixture, not a new issuer document or copied source fact.
    current=cat['documents'][1]
    for old in list(cat['facts'][:3]):
        f=deepcopy(old);ev=deepcopy(next(e for e in cat['evidence']if e['evidence_id']==old['evidence_id']))
        f.update(fact_id=old['fact_id']+'-comparative',document_id=current['document_id'],version_id=current['version_id'],origin_role='comparative_period',evidence_id=old['evidence_id']+'-comparative')
        ev.update(evidence_id=f['evidence_id'],document_id=current['document_id'],version_id=current['version_id'],document_sha256=current['sha256'])
        ev['locator']['record_id']=f['fact_id'];f['evidence_digest']=digest(ev);cat['facts'].append(f);cat['evidence'].append(ev)
    comps=[]
    for metric in ['revenue','operating_profit','operating_cash_flow']:
        fs=[next(f for f in cat['facts']if f['fact_id']==metric+'-'+y)for y in ['2023','2024']]
        ds=[next(d for d in cat['documents']if d['document_id']==f['document_id'])for f in fs]
        comps.append(dict(comparability_id='own-'+metric,organization_id=fs[0]['organization_id'],metric_id=metric,definition_id=fs[0]['definition_id'],review_status='assistant_checked',documents=[dict(document_id=d['document_id'],version_id=d['version_id'],document_sha256=d['sha256'])for d in ds],periods=[f['period']for f in fs],basis='Own artificial construction with identical definition/classification. This does not establish comparability of real issuer versions.',support_evidence_ids=[f['evidence_id']for f in fs],same_definition_and_classification=True,source_checks_reviewed=True))
    cases=[]
    def add(op,ids,overrides=None,target=None,comp=None):
        cid='synthetic-'+str(len(cases)+1).zfill(3);fs=[next(f for f in cat['facts']if f['fact_id']==fid)for fid in ids]
        cases.append(dict(case_id=cid,family=op,fixture_overrides=[dict(fact_id=k,value=v)for k,v in (overrides or {}).items()],request=request(cat,op,fs,cid,comp=comp,target_scale=target)))
    for value in ['0','-0','-5','123.4500','0.000000001','999999999999999999999999999999.999999999']:
        for op in ['direct_fact_v1','scale_v1']:add(op,['revenue-2024'],{'revenue-2024':value},target=1000000000 if op=='scale_v1'else None)
    for a,b in [('100','120'),('100','80'),('0','12'),('-5','12'),('100','0'),('32','32.01'),('32','31.99'),('100000','99999'),('100','-10')]:
        for op in ['absolute_change_v1','relative_change_v1']:add(op,['revenue-2023-comparative','revenue-2024'],{'revenue-2023-comparative':a,'revenue-2024':b})
    for op,rv in [('18','120'),('-18','120'),('0','120'),('1','32'),('-1','32'),('-0.000001','100'),('1','0'),('1','-100'),('0','0')]:
        add('operating_margin_v1',['operating_profit-2024','revenue-2024'],{'operating_profit-2024':op,'revenue-2024':rv})
    for op in ['absolute_change_v1','relative_change_v1']:
        for metric in ['revenue','operating_profit','operating_cash_flow']:add(op,[metric+'-2023',metric+'-2024'],comp='own-'+metric)
    return cat,comps,cases


def gold(cat,cases,oracle):
    facts={f['fact_id']:f for f in cat['facts']};rows=[]
    for c in cases:
        overrides={x['fact_id']:x['value']for x in c['fixture_overrides']};r=c['request'];fs=[facts[x['fact_id']]for x in r['inputs']]
        values=[overrides.get(f['fact_id'],f['value'])for f in fs]
        rows.append(dict(case_id=c['case_id'],**oracle.evaluate(r['operation_id'],values,fs[0]['scale'],r['result_unit'].get('scale',fs[0]['scale']))))
    return rows


def main():
    spec=importlib.util.spec_from_file_location('independent_calculator_reference',ROOT/'evaluation/reference/kp3_calculator_v1/oracle.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    dictionary=read('data/dictionaries/kp3_finance_v1/definitions.json');real=read('data/catalogs/kp3_corpus_v1/runtime_catalog.json');syn,comps,scases=own_synthetic();rcases=real_cases(real)
    write('data/catalogs/kp3_calculator_dev_v1/runtime_catalog.json',syn)
    write('data/calculation/kp3_calculator_v1/real_admission.json',admission(real,dictionary,read('data/catalogs/kp3_corpus_v1/source_bindings.json'),read('evaluation/kp3_05_2026-11-09/source-checks.json')))
    write('data/calculation/kp3_calculator_v1/synthetic_admission.json',admission(syn,dictionary,comparability_records=comps))
    for name,cat,cases in [('real',real,rcases),('synthetic',syn,scases)]:
        write('data/dev_cases/kp3_calculator_v1/'+name+'_cases.json',dict(case_version='1.0',data_origin=name,all_known_to_developer=True,final_eval_freeze=False,cases=cases))
        write('evaluation/fixtures/kp3_calculator_v1/'+name+'_gold.json',dict(reference_version='1.0',oracle='Fraction/integer, separately Decimal80/HALF_UP checked',runtime_allowed=False,cases=gold(cat,cases,oracle)))
    files=[]
    for folder in ['data/calculation/kp3_calculator_v1','data/catalogs/kp3_calculator_dev_v1','data/dev_cases/kp3_calculator_v1','evaluation/fixtures/kp3_calculator_v1']:
        files.extend(p.relative_to(ROOT).as_posix()for p in (ROOT/folder).glob('*.json')if p.name!='manifest.json')
    files.extend(['evaluation/reference/kp3_calculator_v1/oracle.py','scripts/build_kp3_calculator_dev.py','scripts/calculate_financial_v3.py','scripts/check_kp3_calculator.py','src/financial_assistant/calculation_contracts.py','src/financial_assistant/fact_admission.py','src/financial_assistant/financial_calculator.py','tests/test_financial_calculator.py','docs/kp3/calculator_v03.md'])
    write('data/calculation/kp3_calculator_v1/manifest.json',dict(manifest_version='1.0',scope='open_dev_preparation_not_final_eval',runtime_reads_gold=False,file_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in sorted(files)}))
    print(json.dumps(dict(real_cases=len(rcases),synthetic_cases=len(scases),gold_generated_by='independent reference; production calculator not imported')))


if __name__=='__main__':main()
