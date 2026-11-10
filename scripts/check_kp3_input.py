"""Compare open parser cases to separately hand-specified expected semantics; not a model benchmark."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import read_json
from financial_assistant.input_contracts import clarification
from financial_assistant.russian_input import parse_form,parse_text
from financial_assistant.input_binding import resolve_input


def run():
    manifest=read_json(ROOT/'data/input/kp3_ru_v1/manifest.json')
    assert manifest['scope']=='open_dev_preparation_not_final_eval'and manifest['runtime_reads_expected']is False
    for name,h in manifest['file_sha256'].items():
        p=(ROOT/name).resolve();assert p.is_relative_to(ROOT)and hashlib.sha256(p.read_bytes()).hexdigest()==h,'input dev manifest mismatch: '+name
    cat=read_json(ROOT/'data/catalogs/kp3_corpus_v1/runtime_catalog.json');dictionary=read_json(ROOT/'data/dictionaries/kp3_finance_v1/definitions.json')
    cases=read_json(ROOT/'data/dev_cases/kp3_input_v1/cases.json')['cases'];expected={e['case_id']:e for e in read_json(ROOT/'evaluation/fixtures/kp3_input_v1/expected.json')['cases']};rows=[]
    assert len(expected)==len(cases)
    for c in cases:
        source=c['source'];t=parse_text(source['question'],cat,source['input_id'])if source['kind']=='text'else parse_form(source['form'],cat)
        out=resolve_input(t,cat,dictionary)
        for answer in c['answers']:out=resolve_input(clarification(out['normalized_input'],answer),cat,dictionary)
        e=expected[c['case_id']];assert out['status']==e['status'],(c['case_id'],out['status'],e,out['reason_code'])
        f=out['normalized_input']['fields']
        for k in ['operation_id','metric_ids','periods','as_of','organization']:
            if k in e:assert f[k]==e[k],(c['case_id'],k,f[k],e[k])
        if 'reason_code'in e:assert out['reason_code']==e['reason_code'],(c['case_id'],out['reason_code'],e)
        if 'clarification_field'in e:assert e['clarification_field']in [x['field']for x in out['clarifications']],(c['case_id'],out,e)
        if 'assumption_direction'in e:assert out['assumptions'][0]['asserted_direction']==e['assumption_direction']
        question=source['question']if source['kind']=='text'else source['form']['original_question']
        assert out['normalized_input']['original_question']==question and out['financial_status']is None and out['calculations_performed']is False
        if out['status']!='resolved':assert out['request']is None
        rows.append(dict(case_id=c['case_id'],family=c['family'],status=out['status'],reason_code=out['reason_code'],matched=True))
    return dict(cases=rows,total=len(rows),matched=len(rows),known_to_developer=True,model_calls=0,new_real_facts=0,final_eval_freeze=False)


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser();p.add_argument('--report',type=Path);a=p.parse_args();r=run()
    if a.report:
        target=a.report.resolve();assert target.is_relative_to((ROOT/'tmp').resolve());target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in r.items()if k!='cases'}));return 0


if __name__=='__main__':raise SystemExit(main())
