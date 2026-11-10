"""Open developer protocol checks. Actual Qwen runs require --real and are separate."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'tests'))
from test_agent_c import Scripted
from test_service_b import fixture,source
from financial_assistant.service_b import load_service_context
from financial_assistant.agent_model_v2 import load_agent_model
from financial_assistant.agent_contracts_v2 import AgentLimits,validate_agent_answer
from financial_assistant.agent_c import execute_c


def real_specs(ctx):
    out=[];cat=ctx.calculation.catalog
    ops=['direct_fact_v1','absolute_change_v1','relative_change_v1','scale_v1','operating_margin_v1','direct_fact_v1','absolute_change_v1','operating_margin_v1']
    metrics=['operating_cash_flow','operating_profit','revenue','operating_cash_flow','operating_profit','operating_profit','operating_cash_flow','operating_profit']
    for d,op,metric in zip(cat['documents'],ops,metrics):
        fs={m:{role:next(f for f in cat['facts']if f['document_id']==d['document_id']and f['metric_id']==m and f['origin_role']==role)for role in ['reported_period','comparative_period']}for m in ['revenue','operating_profit','operating_cash_flow']}
        selected=[fs['operating_profit']['reported_period'],fs['revenue']['reported_period']]if op=='operating_margin_v1'else [fs[metric]['comparative_period'],fs[metric]['reported_period']]if op in {'absolute_change_v1','relative_change_v1'}else [fs[metric]['reported_period']]
        fields=dict(organization=d['organization_id'],consolidation='group',accounting_standard='IFRS',operation_id=op,metric_ids=['operating_profit','revenue']if op=='operating_margin_v1'else [metric],periods=[f['period']for f in selected]if op in {'absolute_change_v1','relative_change_v1'}else [selected[0]['period']],documents=[dict(document_id=d['document_id'],version_id=d['version_id'])],mode='snapshot')
        if op=='scale_v1':fields['result_unit']=dict(kind='amount',currency='RUB',scale=1000000000)
        cid=d['document_id']+'-'+op
        src=dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id=cid,original_question='Явный выбор учебного dev-контекста C.',fields=fields,assumptions=[]))
        out.append(dict(case_id=cid,source=src,facts=selected,limits=asdict(AgentLimits()),expected='answered'))
    for cid,base,patch,lim in [('historical-publication-unknown',out[0],dict(mode='historical',as_of='2030-01-01T23:59:59+03:00'),AgentLimits()),('qa07-top1-partial-finish',out[2],{},AgentLimits(max_search_results=1))]:
        s=deepcopy(base['source']);s['form']['fields'].update(patch);out.append(dict(case_id=cid,source=s,facts=base['facts'],limits=asdict(lim),expected='missing'))
    return out


def run(args):
    report=dict(stage='KP3-10',started_at=datetime.now(timezone.utc).isoformat(),known_to_developer=True,reserved_unseen_real=0,final_eval_freeze=False,attempts=[])
    manifest=ROOT/'data/agent/kp3_c_v2/manifest.json'
    if manifest.exists():
        for name,h in json.loads(manifest.read_text(encoding='utf8'))['file_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,'agent preparation mismatch: '+name
    if args.real:
        ctx=load_service_context(args.context);adapter=load_agent_model(ROOT/'data/config/local_model.json');specs=real_specs(ctx)
        if args.case:specs=[s for s in specs if s['case_id']==args.case];assert specs,'unknown case'
        origin='real_local_llm_known_corpus05'
    else:
        specs=None;origin='own_mock_protocol'
    spec=importlib.util.spec_from_file_location('independent_agent_reference',ROOT/'evaluation/reference/kp3_calculator_v1/oracle.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp')as td:
        if specs is None:
            ctx=fixture(Path(td));adapter=Scripted();specs=[dict(case_id='own-'+op,source=source(ctx,op),facts=None,limits=asdict(AgentLimits()),expected='answered')for op in ['direct_fact_v1','absolute_change_v1','relative_change_v1','scale_v1','operating_margin_v1']]
        for spec in specs:
            a=execute_c(spec['source'],ctx,adapter,limits=AgentLimits(**spec['limits']));validate_agent_answer(a)
            row=dict(case_id=spec['case_id'],origin=origin,input=spec['source'],limits=spec['limits'],answer=a,expected_status=spec['expected'],matched=(a['financial_status']=='answered'if spec['expected']=='answered'else a['request_status']==spec['expected']and a['agent']['finished']and a['financial_result']is None and a['execution_status']=='completed'))
            if spec['facts']is not None and spec['expected']=='answered':
                fs=spec['facts'];fields=spec['source']['form']['fields'];ref=oracle.evaluate(fields['operation_id'],[f['value']for f in fs],fs[0]['scale'],fields.get('result_unit',{}).get('scale',fs[0]['scale']));row['independent_reference']=ref;row['expected_input_fact_ids']=[f['fact_id']for f in fs]
                r=a['financial_result'];row['matched']=row['matched']and r is not None and r['exact_result']==ref['exact_result']and r['display_value']==ref['display_value']and [f['fact_id']for f in r['inputs']]==row['expected_input_fact_ids']
            report['attempts'].append(row)
            # Persist each attempt immediately, including a failure; no best-of selection.
            report['counts']=dict(attempted=len(report['attempts']),matched=sum(r['matched']for r in report['attempts']),model_calls=sum(r['answer']['model_calls']or 0 for r in report['attempts']),unknown_call_runs=sum(r['answer']['model_calls']is None for r in report['attempts']))
            args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
            print(json.dumps(dict(case_id=spec['case_id'],matched=row['matched'],execution=a['execution_status'],request=a['request_status'],financial=a['financial_status'],reason=a['reason_code'],model_calls=a['model_calls']),ensure_ascii=False),flush=True)
    return 0 if all(r['matched']for r in report['attempts'])else 1


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__);p.add_argument('--real',action='store_true');p.add_argument('--context',type=Path);p.add_argument('--case');p.add_argument('--report',type=Path,required=True);args=p.parse_args();assert args.report.resolve().is_relative_to((ROOT/'tmp').resolve()),'private raw run path required';assert not args.report.exists(),'preserve previous attempts';return run(args)


if __name__=='__main__':raise SystemExit(main())
