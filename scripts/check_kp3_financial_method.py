"""Validate method/dev fixtures and reproduce independent gold, not model answers."""
from pathlib import Path
import argparse
import importlib.util
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.catalog import validate_catalog
from financial_assistant.contracts_v2 import digest,read_json


def load_oracle():
    spec=importlib.util.spec_from_file_location('kp3_method_reference',ROOT/'evaluation/reference/kp3_finance_v1/oracle.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def check(generate=False):
    dictionary=read_json(ROOT/'data/dictionaries/kp3_finance_v1/definitions.json')
    catalog=read_json(ROOT/'data/catalogs/kp3_finance_dev_v1/runtime_catalog.json')
    cases=read_json(ROOT/'data/dev_cases/kp3_finance_v1/cases.json')
    if set(dictionary)!={'dictionary_version','scope','definitions','operations','excluded'} or dictionary['dictionary_version']!='1.0':raise ValueError('dictionary_schema')
    definitions=dictionary['definitions'];ids=[d['definition_id'] for d in definitions]
    if len(ids)!=len(set(ids)) or len(definitions)!=3:raise ValueError('duplicate_or_missing_definitions')
    if any(d['accounting_standard']!='IFRS' or d['consolidation']!='group' or d['organization_type']!='nonfinancial' for d in definitions):raise ValueError('definition_scope')
    if len({o['operation_id'] for o in dictionary['operations']})!=len(dictionary['operations']):raise ValueError('duplicate_operation')
    validate_catalog(catalog)
    if {m['definition_id'] for m in catalog['metrics']}!=set(ids) or any(d['data_origin']!='synthetic' for d in catalog['documents']):raise ValueError('runtime_scope')
    expected=load_oracle().make_gold(catalog,cases,dictionary)
    expected['input_digests']={'dictionary':digest(dictionary),'runtime_catalog':digest(catalog),'dev_cases':digest(cases)}
    target=ROOT/'evaluation/fixtures/kp3_finance_v1/gold.json'
    if generate:
        if target.exists():raise ValueError('refusing_gold_overwrite')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if read_json(target)!=expected:raise ValueError('reference_gold_mismatch')
    counts={}
    for row in expected['cases']:
        key=row['execution_status']+'/'+str(row['financial_status']);counts[key]=counts.get(key,0)+1
        if row['execution_status']!='completed' and (row['financial_status'] is not None or row['calculation'] is not None):raise ValueError('mixed_execution_and_financial_status')
        if row['financial_status']!='answered' and row['calculation'] is not None:raise ValueError('refusal_has_calculation')
    return {'dictionary_version':'1.0','definitions':len(definitions),'method_operations':len(dictionary['operations']),
            'synthetic_runtime_facts':len(catalog['facts']),'open_dev_cases':len(expected['cases']),'outcome_counts':counts,
            'independent_gold_matches':True,'production_answer_calls':0,'new_real_financial_facts':0,'quality_metric':False}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate-gold',action='store_true',help='write gold only if absent; development preparation only')
    args=parser.parse_args()
    print(json.dumps(check(args.generate_gold),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
