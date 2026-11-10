"""Open deterministic service checks, separate from runtime and any future model evaluation."""
import argparse,hashlib,importlib.util,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'tests'))
from financial_assistant.service_b import execute,load_service_context
from financial_assistant.service_contracts import validate_answer
from test_service_b import fixture,source


def run(context_path=None):
    manifest=json.loads((ROOT/'data/service/kp3_b_v1/manifest.json').read_text(encoding='utf8'))
    for name,h in manifest['file_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,'service preparation manifest mismatch: '+name
    spec=importlib.util.spec_from_file_location('independent_service_reference',ROOT/'evaluation/reference/kp3_calculator_v1/oracle.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    report=dict(stage='KP3-09',model_calls=0,new_real_facts=0,known_to_developer=True,final_eval_freeze=False,cases=[])
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp')as td:
        own=fixture(Path(td))
        for op,expected in [('direct_fact_v1','120'),('absolute_change_v1','20'),('relative_change_v1','20.00'),('scale_v1','0.12'),('operating_margin_v1','15.00')]:
            a=execute(source(own,op),'B',own);validate_answer(a);assert a['financial_result']['display_value']==expected
            report['cases'].append(dict(case_id='own-'+op,origin='own_synthetic',operation_id=op,matched=True))
    if context_path:
        ctx=load_service_context(context_path);cat=ctx.calculation.catalog
        for d in cat['documents']:
            current={m:next(f for f in cat['facts']if f['document_id']==d['document_id']and f['metric_id']==m and f['origin_role']=='reported_period')for m in ['revenue','operating_profit','operating_cash_flow']}
            previous={m:next(f for f in cat['facts']if f['document_id']==d['document_id']and f['metric_id']==m and f['origin_role']=='comparative_period')for m in current}
            for op in ['direct_fact_v1','absolute_change_v1','relative_change_v1','scale_v1','operating_margin_v1']:
                for metric in ['operating_profit']if op=='operating_margin_v1'else current:
                    fs=[current['operating_profit'],current['revenue']]if op=='operating_margin_v1'else [previous[metric],current[metric]]if op in {'absolute_change_v1','relative_change_v1'}else [current[metric]]
                    periods=[f['period']for f in fs]if op in {'absolute_change_v1','relative_change_v1'}else [fs[0]['period']]
                    fields=dict(organization=d['organization_id'],consolidation='group',accounting_standard='IFRS',operation_id=op,metric_ids=['operating_profit','revenue']if op=='operating_margin_v1'else [metric],periods=periods,documents=[dict(document_id=d['document_id'],version_id=d['version_id'])],mode='snapshot')
                    if op=='scale_v1':fields['result_unit']=dict(kind='amount',currency=fs[0]['currency'],scale=1000000000)
                    cid=d['document_id']+'-'+metric+'-'+op
                    src=dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id=cid,original_question='Явная открытая проверка фиксированного сервиса.',fields=fields,assumptions=[]))
                    ref=oracle.evaluate(op,[f['value']for f in fs],fs[0]['scale'],1000000000 if op=='scale_v1'else fs[0]['scale'])
                    a=execute(src,'B',ctx);validate_answer(a);assert a['financial_status']==ref['status'],(cid,a)
                    result=a['financial_result'];assert [f['fact_id']for f in result['inputs']]==[f['fact_id']for f in fs],cid
                    assert result['exact_result']==ref['exact_result']and result['display_value']==ref['display_value'],cid
                    report['cases'].append(dict(case_id=cid,origin='real_known_corpus05',operation_id=op,expected_input_fact_ids=[f['fact_id']for f in fs],reference=ref,matched=True,run_id=a['run_id']))
    report['counts']={k:sum(x['origin']==k for x in report['cases'])for k in ['own_synthetic','real_known_corpus05']};return report


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__);p.add_argument('--context',type=Path);p.add_argument('--report',type=Path);args=p.parse_args();r=run(args.context)
    if args.report:
        target=args.report.resolve();assert target.is_relative_to((ROOT/'tmp').resolve());target.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in r.items()if k!='cases'}));return 0


if __name__=='__main__':raise SystemExit(main())
