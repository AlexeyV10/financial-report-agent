"""Open known product checks, independent arithmetic oracle stays outside runtime."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.service_b import load_service_context
from financial_assistant.product_history import RunStore
from financial_assistant.product_service import financial,preflight

def run(context):
    manifest=ROOT/'data/product/kp3_product_v1/manifest.json'
    if manifest.exists():
        for p,h in json.loads(manifest.read_text(encoding='utf8'))['file_sha256'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
    ctx=load_service_context(context);cat=ctx.calculation.catalog;ready=preflight(ctx);assert ready['ready']and ready['index_kind']=='prepared'
    spec=importlib.util.spec_from_file_location('independent_reference07',ROOT/'evaluation/reference/kp3_calculator_v1/oracle.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    report=dict(stage='KP3-13',known_to_developer=True,final_eval_freeze=False,new_real_facts=0,model_calls=0,cases=[],historical_blocked=0,deduplicated=0)
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp')as td:
        store=RunStore(Path(td)/'history')
        for d in cat['documents']:
            current={m:next(f for f in cat['facts']if f['document_id']==d['document_id']and f['metric_id']==m and f['origin_role']=='reported_period')for m in ['revenue','operating_profit','operating_cash_flow']}
            previous={m:next(f for f in cat['facts']if f['document_id']==d['document_id']and f['metric_id']==m and f['origin_role']=='comparative_period')for m in current}
            for op in ['direct_fact_v1','absolute_change_v1','relative_change_v1','scale_v1','operating_margin_v1']:
                for metric in ['operating_profit']if op=='operating_margin_v1'else current:
                    fs=[current['operating_profit'],current['revenue']]if op=='operating_margin_v1'else [previous[metric],current[metric]]if op in {'absolute_change_v1','relative_change_v1'}else [current[metric]]
                    fields=dict(organization=d['organization_id'],operation_id=op,metric_ids=['operating_profit','revenue']if op=='operating_margin_v1'else[metric],periods=[f['period']for f in fs]if op in {'absolute_change_v1','relative_change_v1'}else[fs[0]['period']],documents=[dict(document_id=d['document_id'],version_id=d['version_id'])],mode='snapshot')
                    if op=='scale_v1':fields['result_unit']=dict(kind='amount',currency=fs[0]['currency'],scale=1000000000)
                    cid=d['document_id']+'-'+metric+'-'+op;source=dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id=cid,original_question='Явная открытая проверка продуктового адаптера13.',fields=fields,assumptions=[]))
                    record,reused=financial(source,[],'B',ctx,store);assert not reused;a=record['payload']['result'];ref=oracle.evaluate(op,[f['value']for f in fs],fs[0]['scale'],1000000000 if op=='scale_v1'else fs[0]['scale']);assert a['financial_status']==ref['status']
                    result=a['financial_result'];assert [x['fact_id']for x in result['inputs']]==[f['fact_id']for f in fs];assert result['exact_result']==ref['exact_result']and result['display_value']==ref['display_value']
                    assert financial(source,[],'B',ctx,store)==(record,True);report['deduplicated']+=1
                    assert json.loads(store.export(record['record_id'],'json'))==record;assert 'Снимок истории'in store.export(record['record_id'],'markdown').decode()
                    report['cases'].append(dict(case_id=cid,run_id=a['run_id'],reference=ref,matched=True))
                    if op=='direct_fact_v1'and metric=='revenue':
                        fields.update(mode='historical',as_of='2026-11-10T23:59:59+03:00');h=financial(source,[],'B',ctx,store)[0]['payload']['result'];assert h['reason_code']=='publication_unknown'and h['financial_result']is None;report['historical_blocked']+=1
    report['real_numeric_cases']=len(report['cases']);assert len(report['cases'])==104 and report['historical_blocked']==8;return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--context',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();target=a.report.resolve();assert target.is_relative_to((ROOT/'tmp').resolve())and not target.exists();r=run(a.context);target.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in r.items()if k!='cases'}));return 0

if __name__=='__main__':raise SystemExit(main())
