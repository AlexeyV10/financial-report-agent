"""Separate parser/retrieval/own calculator/scenario observations; expected data only in replay."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import json,sys
from kp3_protocol_v1.common import read,require,file_sha
from .ledger import atomic_new
from .runtime import ROOT,validate_manifest,private
from financial_assistant.service_b import load_service_context,execute
from financial_assistant.retrieval_v2 import search_index
from financial_assistant.fact_admission import load_context
from financial_assistant.financial_calculator import calculate
from financial_assistant.russian_input import parse_text
from financial_assistant.input_binding import resolve_input
from financial_assistant.scenario_service import ScenarioContext,load_own_context,own_financial,execute_scenario


def collect(manifest_path,output):
    m,inputs=validate_manifest(manifest_path);out=Path(output);require(not out.exists(),'new_supplement_directory_required');out.mkdir(parents=True);t=private(ROOT/m['private_run_dir'])/'supplement';t.mkdir();ctx=load_service_context(ROOT/m['context_path']);dictionary=ctx.calculation.dictionary;cat=ctx.calculation.catalog;report=dict(schema_version='kp3-supplement-observations-0.1',run_manifest_sha256=file_sha(manifest_path),model_calls=0,financial_dev=[],parser=[],retrieval=[],scenario=[],robustness='reuse actual143dev variants15; not rerun or mislabeled as138comparison')
    own=load_context(ROOT/'data/catalogs/kp3_calculator_dev_v1/runtime_catalog.json',ROOT/'data/dictionaries/kp3_finance_v1/definitions.json',ROOT/'data/calculation/kp3_calculator_v1/synthetic_admission.json')
    for c in inputs['cases']:
        if c['split']=='comparison_known'or c['suite']=='robustness':continue
        start=perf_counter();value=None;error=None
        try:
            if c['target']=='calculator_v03':
                req=deepcopy(c['source']['request']);value=calculate(own,req,req['request_id']);key='financial_dev'
            elif c['target']=='parser':value=resolve_input(parse_text(c['source']['question'],cat,c['case_id']),cat,dictionary);key='parser'
            elif c['target']=='scenario':
                key='scenario';s=c['source'];run=t/c['case_id'];rid='eval16-'+c['case_id']
                if s['kind']=='scenario':
                    sc=load_own_context(run);req=deepcopy(s['request'])
                    if c['fault_id']=='own_price_gap':
                        dataset=deepcopy(sc.dataset);dataset['prices']['observations'].pop(5);sc=ScenarioContext(sc.calculation,run,dataset,sc.source_path)
                    fin=own_financial(sc)
                else:
                    fin=execute(deepcopy(s['financial_source']),'B',ctx,run_id=rid+'-financial');sc=ScenarioContext(ctx,run);req=dict(schema_version='kp3-scenario-request-0.1',financial_run_id=fin['run_id'],data_mode='real_source_readiness',decision_at=s['decision_at'],parameters=None)
                value=execute_scenario(fin,req,sc,run_id=rid)
            else:raise ValueError('unsupported_supplement_target')
        except Exception as e:error=getattr(e,'code',type(e).__name__);key='financial_dev'if c['target']=='calculator_v03'else'parser'if c['target']=='parser'else'scenario'
        row=dict(case_id=c['case_id'],observation=value,error=error,elapsed_ms=round((perf_counter()-start)*1000,4));atomic_new(out/(c['case_id']+'.json'),row);report[key].append(row)
    for q in read(ROOT/'data/evaluation/kp3_eval_v1/search_tasks.json')['queries']:
        start=perf_counter()
        try:value=search_index(ctx.retrieval['db_path'],cat,ctx.calculation.resources,ctx.retrieval['config'],ctx.retrieval['lexicon'],deepcopy(q['spec']));error=None
        except Exception as e:error=getattr(e,'code',type(e).__name__);value=dict(status='error',reason_code=error,results=[],source_kind=None)
        row=dict(query_id=q['query_id'],observation=value,error=error,elapsed_ms=round((perf_counter()-start)*1000,4));atomic_new(out/(q['query_id']+'.json'),row);report['retrieval'].append(row)
    diagnostic=read(ROOT/'tmp/retrieval-run-16/dev-report.json');report['extraction']=dict(**diagnostic['extraction'],measurement='Automatic geometry/lexicon re-run on8 unchanged pinned worker exports; not fresh worker execution, not reading prepared annotation as extraction',new_worker_invocations=0,new_facts_admitted=0)
    atomic_new(out/'observations.json',report);return report


def replay(manifest_path,observations,output):
    m,inputs=validate_manifest(manifest_path);data=read(observations,20000000);require(data['run_manifest_sha256']==file_sha(manifest_path),'supplement_manifest_changed');freeze=read(ROOT/m['freeze_path']);gold=read(ROOT/freeze['gold_path']);gs={g['case_id']:g for g in gold['cases']};cs={c['case_id']:c for c in inputs['cases']}
    from kp3_protocol_v1.evaluator import evaluate_financial,evaluate_parser,evaluate_scenario
    from kp3_protocol_v1.metrics import retrieval_metrics
    scores={}
    for key,grade in [('financial_dev',evaluate_financial),('parser',evaluate_parser),('scenario',evaluate_scenario)]:
        rows=[]
        for row in data[key]:
            c=cs[row['case_id']];g=gs[c['case_id']];rows.append(grade(c,g,row['observation'])if row['observation']is not None else dict(case_id=c['case_id'],matched=False,errors=[row['error']]))
        scores[key]=dict(x=sum(r['matched']for r in rows),n=len(rows),scores=rows)
    scores['retrieval']=retrieval_metrics(read(ROOT/'evaluation/fixtures/kp3_eval_v1/retrieval_gold.json'),data['retrieval']);scores['extraction']=data['extraction'];scores['model_calls']=0;scores['scope']='Separate known controls, no addition to40 financial questions or138attempts';atomic_new(output,scores);return scores
