"""Open dev verification. Gold/fixture overrides belong only to this evaluator, never runtime."""
from copy import deepcopy
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import digest,read_json
from financial_assistant.fact_admission import CalculationContext
from financial_assistant.financial_calculator import calculate,validate_calculation_binding


def read(p):return read_json(ROOT/p)


def context(kind,overrides=(),resources=None):
    cat=read('data/catalogs/'+('kp3_corpus_v1'if kind=='real'else 'kp3_calculator_dev_v1')+'/runtime_catalog.json')
    for change in overrides:
        assert kind=='synthetic','Only explicitly own fixtures may be changed by the evaluator'
        f=next(f for f in cat['facts']if f['fact_id']==change['fact_id']);f['value']=change['value']
        e=next(e for e in cat['evidence']if e['evidence_id']==f['evidence_id']);e['raw_value']=change['value'];e['numeric_encoding']='decimal_string';f['evidence_digest']=digest(e)
    dictionary=read('data/dictionaries/kp3_finance_v1/definitions.json');a=read('data/calculation/kp3_calculator_v1/'+kind+'_admission.json')
    if kind=='synthetic':a['component_digests']['catalog']=digest(cat)
    return CalculationContext(cat,dictionary,a,read('data/catalogs/kp3_corpus_v1/source_bindings.json')if kind=='real'else None,read('evaluation/kp3_05_2026-11-09/source-checks.json')if kind=='real'else None,resources)


def run(resources=None):
    manifest=read('data/calculation/kp3_calculator_v1/manifest.json')
    assert manifest['scope']=='open_dev_preparation_not_final_eval' and manifest['runtime_reads_gold'] is False
    for name,h in manifest['file_sha256'].items():
        p=(ROOT/name).resolve();assert p.is_relative_to(ROOT) and hashlib.sha256(p.read_bytes()).hexdigest()==h,'calculator dev manifest mismatch: '+name
    spec=importlib.util.spec_from_file_location('calculator_reference',ROOT/'evaluation/reference/kp3_calculator_v1/oracle.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    report=dict(schema_version='1.0',model_calls=0,final_eval_freeze=False,reserved_unseen_real=0,cases=[],reference_decimal80_matched=0)
    for kind in ['synthetic','real']:
        cases=read('data/dev_cases/kp3_calculator_v1/'+kind+'_cases.json')['cases'];gold={g['case_id']:g for g in read('evaluation/fixtures/kp3_calculator_v1/'+kind+'_gold.json')['cases']}
        for case in cases:
            ctx=context(kind,case['fixture_overrides'],resources);req=case['request'];facts={f['fact_id']:f for f in ctx.catalog['facts']};fs=[facts[r['fact_id']]for r in req['inputs']]
            ref=oracle.evaluate(req['operation_id'],[f['value']for f in fs],fs[0]['scale'],req['result_unit'].get('scale',fs[0]['scale']))
            assert dict(case_id=case['case_id'],**ref)==gold[case['case_id']],'frozen reference mismatch'
            report['reference_decimal80_matched']+=ref['status']=='answered'
            if kind=='real' and resources is None:continue
            out=calculate(ctx,req,case['case_id']);assert out['execution_status']=='completed',(case['case_id'],out)
            assert out['financial_status']==ref['status'] and out['reason_code']==ref['reason'],(case['case_id'],out,ref)
            if ref['status']=='answered':
                assert out['financial_result']['display_value']==ref['display_value'] and out['financial_result']['exact_result']==ref['exact_result'],(case['case_id'],out,ref)
            else:assert out['financial_result'] is None
            validate_calculation_binding(out,ctx,req)
            report['cases'].append(dict(case_id=case['case_id'],data_origin=kind,operation_id=req['operation_id'],financial_status=out['financial_status'],reason_code=out['reason_code'],matched_reference=True))
    report['counts']={k:sum(c['data_origin']==k for c in report['cases'])for k in ['real','synthetic']};report['real_source_bytes_checked']=resources is not None
    return report


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resources',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
    report=run(read_json(a.resources)if a.resources else None)
    if a.report:
        target=a.report.resolve();assert target.is_relative_to((ROOT/'tmp').resolve()),'Detailed output only in ignored tmp'
        target.parent.mkdir(exist_ok=True,parents=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items()if k!='cases'},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
