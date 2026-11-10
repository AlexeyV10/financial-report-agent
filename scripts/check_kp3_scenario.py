"""Open scenario12 dev cases and independent ledger reference. No model or final benchmark."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import read_json
from financial_assistant.scenario_service import OWN,ScenarioContext,load_own_context,own_financial,execute_scenario,validate_scenario_binding
from financial_assistant.service_b import execute,load_service_context


def own_cases():
    cases=[]
    for allocation in ['0.2','0.5','1']:
        for fee,slip,lot in [('0','0',1),('1','0',1),('2.35','10',3),('5','100',10)]:
            for threshold in ['10','20']:cases.append(dict(case_id=f'a{allocation}-fee{fee}-slip{slip}-lot{lot}-t{threshold}',changes=dict(allocation=allocation,fee_fixed=fee,slippage_bps=slip,lot_size=lot,threshold_pct=threshold)))
    return cases


def run(args):
    mf=ROOT/'data/scenarios/kp3_scenario_v1/manifest.json'
    if mf.exists():
        for p,h in read_json(mf)['file_sha256'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,'scenario preparation mismatch: '+p
    spec=importlib.util.spec_from_file_location('own_scenario_reference',ROOT/'evaluation/reference/kp3_scenario_v1/oracle.py');refmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(refmod);ctx=load_own_context();fin=own_financial(ctx);base=read_json(OWN/'request_example.json');report=dict(stage='KP3-12',known_to_developer=True,final_eval_freeze=False,model_calls=0,own_cases=[],real_blocks=[],envelope_adapters=[])
    for case in own_cases():
        r=deepcopy(base);r['parameters'].update(case['changes']);out=execute_scenario(fin,r,ctx);assert out['status']=='completed',(case,out);validate_scenario_binding(out,ctx,fin,r);signal=Decimal('20')>Decimal(r['parameters']['threshold_pct']);expected={}
        for key,path,trade in [('scenario',out['scenario'],signal),('cash',out['comparisons']['cash_no_interest'],False),('hold',out['comparisons']['hold_same_allocation'],True)]:
            ref=refmod.reference(ctx.dataset,r,trade);expected[key]=ref;assert path['entry_quantity']==ref['entry_quantity']and Decimal(path['final_cash'])*100==ref['final_cash_cents']and path['max_drawdown']['ratio']==ref['drawdown_ratio'],case
            assert all(Decimal(path[field])*100==ref[target]for field,target in [('pnl','pnl_cents'),('fees','fees_cents'),('slippage_cost','slippage_cents'),('return_pct','return_percent_cents')]),case
            assert Decimal(path['max_drawdown']['percent'])*100==ref['drawdown_percent_cents'],case
            for a,b in zip(path['ledger'],ref['rows']):assert (a['action'],Decimal(a['cash'])*100,a['quantity'],Decimal(a['equity'])*100,Decimal(a['commission'])*100,Decimal(a['gross'])*100,Decimal(a['slippage_cost'])*100)==(b['action'],b['cash_cents'],b['quantity'],b['equity_cents'],b['commission_cents'],b['gross_cents'],b['slippage_cents']),case
        report['own_cases'].append(dict(case_id=case['case_id'],request=r,run_id=out['run_id'],reference=expected,matched=True))
    if args.real_context:
        service=load_service_context(args.real_context);real=ScenarioContext(service,ROOT/'tmp/scenario-runs');cat=service.calculation.catalog
        for d in cat['documents']:
            fs=[next(f for f in cat['facts']if f['document_id']==d['document_id']and f['metric_id']=='revenue'and f['origin_role']==role)for role in ['comparative_period','reported_period']];src=dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id='scenario-known-real',original_question='Проверка выручки для готовности сценария.',fields=dict(organization=d['organization_id'],operation_id='relative_change_v1',metric_ids=['revenue'],periods=[f['period']for f in fs],documents=[dict(document_id=d['document_id'],version_id=d['version_id'])],mode='snapshot'),assumptions=[]));answer=execute(src,'B',service);assert answer['financial_status']=='answered';r=dict(schema_version=base['schema_version'],financial_run_id=answer['run_id'],data_mode='real_source_readiness',decision_at='2026-11-10T23:59:59+03:00',parameters=None);out=execute_scenario(answer,r,real);assert out['status']=='blocked'and out['reason_code']=='publication_unknown'and out['scenario']is None;report['real_blocks'].append(dict(document_id=d['document_id'],financial_run_id=answer['run_id'],run_id=out['run_id'],status=out['status'],reasons=out['eligibility']['reason_codes'],method='B',matched=True))
        # Existing actual C/A envelopes, revalidated without starting either model/controller.
        samples=[('C',ROOT/'evaluation/kp3_10_2026-11-10/real-attempts-v2.json'),('A',ROOT/'evaluation/kp3_11_2026-11-10/a-real-v1.json')]
        for method,p in samples:
            old=read_json(p)['attempts'][0]['answer'];r=dict(schema_version=base['schema_version'],financial_run_id=old['run_id'],data_mode='real_source_readiness',decision_at='2026-11-10T23:59:59+03:00',parameters=None);out=execute_scenario(old,r,real);assert out['status']=='blocked'and out['reason_code']=='publication_unknown',(method,out);report['envelope_adapters'].append(dict(method=method,source_run_id=old['run_id'],run_id=out['run_id'],new_model_calls=0,status='blocked',matched=True))
    report['counts']=dict(own_cases=len(report['own_cases']),own_reference_paths=len(report['own_cases'])*3,real_versions_blocked=len(report['real_blocks']),old_actual_envelopes_revalidated=len(report['envelope_adapters']));return report


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__);p.add_argument('--real-context',type=Path);p.add_argument('--report',type=Path,required=True);a=p.parse_args();assert a.report.resolve().is_relative_to((ROOT/'tmp').resolve())and not a.report.exists(),'new private report required';r=run(a);a.report.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(r['counts']));return 0
if __name__=='__main__':raise SystemExit(main())
