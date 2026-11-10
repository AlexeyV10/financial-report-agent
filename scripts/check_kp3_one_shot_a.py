"""Known open A dev checks. Scripted, real-source LLM and own-source LLM denominators separate."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(ROOT/'scripts'))
from check_kp3_agent_c import real_specs as c_specs
from test_service_b import fixture,source
from test_one_shot_a import ChoiceMock
from financial_assistant.service_b import load_service_context
from financial_assistant.one_shot_a import execute_a
from financial_assistant.one_shot_model import load_one_shot_model
from financial_assistant.one_shot_contracts import SelectionLimits,validate_one_shot_answer


def real_specs(ctx):
    out=[dict(case_id=s['case_id'],source=s['source'],facts=s['facts'],expected=s['expected'],limits=asdict(SelectionLimits(top_k=1 if s['case_id']=='qa07-top1-partial-finish'else 32)))for s in c_specs(ctx)]
    row=deepcopy(out[1]);row['case_id']='false-premise-revenue-increase';row['source']['form']['original_question']='Почему выручка снизилась?';row['source']['form']['fields']['metric_ids']=['revenue'];did=row['source']['form']['fields']['documents'][0]['document_id'];row['facts']=[next(f for f in ctx.calculation.catalog['facts']if f['document_id']==did and f['metric_id']=='revenue'and f['origin_role']==role)for role in ['comparative_period','reported_period']];out.append(row);return out


def run(args):
    manifest=ROOT/'data/selection/kp3_a_v1/manifest.json'
    if manifest.exists():
        for name,h in json.loads(manifest.read_text(encoding='utf8'))['file_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,'A preparation mismatch: '+name
    report=dict(stage='KP3-11',started_at=datetime.now(timezone.utc).isoformat(),known_to_developer=True,reserved_unseen_real=0,final_eval_freeze=False,attempts=[])
    refspec=importlib.util.spec_from_file_location('independent_A_reference',ROOT/'evaluation/reference/kp3_calculator_v1/oracle.py');oracle=importlib.util.module_from_spec(refspec);refspec.loader.exec_module(oracle)
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp')as td:
        if args.real:
            ctx=load_service_context(args.context);adapter=load_one_shot_model(ROOT/'data/config/local_model.json');specs=real_specs(ctx);origin='real_known_corpus05_local_llm'
        elif args.real_own:
            ctx=fixture(Path(td),[dict(fact_id='revenue-2023-comparative',value='0')]);adapter=load_one_shot_model(ROOT/'data/config/local_model.json');specs=[dict(case_id='own-zero-relative-base',source=source(ctx,'relative_change_v1'),facts=[next(f for f in ctx.calculation.catalog['facts']if f['fact_id']==fid)for fid in ['revenue-2023-comparative','revenue-2024']],expected='unsupported',limits=asdict(SelectionLimits()))];origin='own_synthetic_local_llm_not_issuer'
        else:
            ctx=fixture(Path(td));adapter=ChoiceMock();specs=[dict(case_id='own-'+op,source=source(ctx,op),facts=None,expected='answered',limits=asdict(SelectionLimits()))for op in ['direct_fact_v1','absolute_change_v1','relative_change_v1','scale_v1','operating_margin_v1']];origin='own_scripted_controller_not_LLM'
        for case in specs:
            start=time.monotonic();a=execute_a(case['source'],ctx,adapter,limits=SelectionLimits(**case['limits']));validate_one_shot_answer(a);matched=(a['financial_status']==case['expected']if case['expected']in {'answered','unsupported'}else a['request_status']==case['expected']and a['execution_status']=='completed'and a['model_calls']==0)
            row=dict(case_id=case['case_id'],origin=origin,input=case['source'],limits=case['limits'],answer=a,elapsed_s=round(time.monotonic()-start,4),expected_status=case['expected'],matched=matched)
            if case['facts']is not None and case['expected']in {'answered','unsupported'}:
                fs=case['facts'];fields=case['source']['form']['fields'];ref=oracle.evaluate(fields['operation_id'],[f['value']for f in fs],fs[0]['scale'],fields.get('result_unit',{}).get('scale',fs[0]['scale']));row['reference']=ref;row['expected_input_fact_ids']=[f['fact_id']for f in fs]
                result=a['financial_result'];row['matched']=matched and (a['reason_code']==ref['reason']if case['expected']=='unsupported'else result is not None and result['exact_result']==ref['exact_result']and result['display_value']==ref['display_value']and [f['fact_id']for f in result['inputs']]==row['expected_input_fact_ids'])
            if case['case_id']=='false-premise-revenue-increase':row['matched']=row['matched']and a['assumption_checks'][0]['status']=='contradicted'and a['assumption_checks'][0]['explanation_status']=='not_supported'
            report['attempts'].append(row);report['counts']=dict(cases=len(report['attempts']),matched=sum(r['matched']for r in report['attempts']),model_attempts=sum(r['answer']['selection']['model_attempts']for r in report['attempts']),known_chat_requests=sum(r['answer']['selection']['usage']['known_chat_requests']for r in report['attempts']),unknown_chat_attempts=sum(r['answer']['selection']['usage']['unknown_requests']for r in report['attempts']),early_without_model=sum(r['answer']['selection']['model_attempts']==0 for r in report['attempts']))
            args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8');print(json.dumps(dict(case_id=case['case_id'],matched=row['matched'],execution=a['execution_status'],request=a['request_status'],financial=a['financial_status'],reason=a['reason_code'],model_calls=a['model_calls'],searches=[a['selection']['primary_searches'],a['selection']['validation_searches']]),ensure_ascii=False),flush=True)
    return 0 if all(r['matched']for r in report['attempts'])else 1


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group();g.add_argument('--real',action='store_true');g.add_argument('--real-own',action='store_true');p.add_argument('--context',type=Path);p.add_argument('--report',type=Path,required=True);args=p.parse_args();assert args.report.resolve().is_relative_to((ROOT/'tmp').resolve());assert not args.report.exists(),'preserve all prior attempts';return run(args)


if __name__=='__main__':raise SystemExit(main())
