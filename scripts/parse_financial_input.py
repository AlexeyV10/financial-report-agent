"""Limited Russian/form adapter CLI; optional explicit integration probe of existing07, no service/UI."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import ContractError,need,read_json,shape
from financial_assistant.input_contracts import clarification
from financial_assistant.russian_input import parse_text,parse_form
from financial_assistant.input_binding import resolve_input,probe_adapter,syntax_status
from financial_assistant.fact_admission import load_context


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__)
    for key in ['catalog','dictionary','input']:p.add_argument('--'+key,type=Path,required=True)
    for key in ['answers','admission','bindings','source-checks','resources','index','config','lexicon','exports']:p.add_argument('--'+key,type=Path)
    p.add_argument('--probe',action='store_true',help='Explicit narrow integration check, not general service')
    a=p.parse_args();result=dict(schema_version='kp3-input-cli-0.1',parse_status='error',binding=None,probe=None,technical_details=None,model_calls=0)
    try:
        cat=read_json(a.catalog);dictionary=read_json(a.dictionary);source=read_json(a.input)
        if source.get('kind')=='text':
            shape(source,'kind input_id question');task=parse_text(source['question'],cat,source['input_id'])
        else:
            shape(source,'kind form');need(source['kind']=='form','invalid_input_kind');task=parse_form(source['form'],cat)
        binding=resolve_input(task,cat,dictionary)
        if a.answers:
            answers=read_json(a.answers);need(type(answers)is list and len(answers)<=16,'invalid_answers')
            for answer in answers:
                task=clarification(binding['normalized_input'],answer);binding=resolve_input(task,cat,dictionary)
        result.update(parse_status=syntax_status(binding['normalized_input']),binding=binding)
        if a.probe and binding['status']=='resolved':
            need(a.admission is not None,'admission_required')
            ctx=load_context(a.catalog,a.dictionary,a.admission,a.bindings,a.source_checks,a.resources)
            gate=None
            if any([a.index,a.config,a.lexicon,a.exports]):
                need(all([a.index,a.config,a.lexicon]),'incomplete_retrieval_setup')
                gate=dict(db_path=a.index,config=read_json(a.config),lexicon=read_json(a.lexicon),export_paths=read_json(a.exports)if a.exports else None)
            result['probe']=probe_adapter(ctx,binding,gate)
        if binding['status']=='error':return_code=2
        elif binding['status']=='awaiting_clarification':return_code=3
        elif binding['status']!='resolved':return_code=4
        elif result['probe']and result['probe']['outcome']['execution_status']=='error':return_code=2
        else:return_code=0
    except (ContractError,OSError,ValueError,KeyError,TypeError,AttributeError)as e:
        result.update(parse_status='error',binding=None,probe=None,technical_details=dict(code=getattr(e,'code','invalid_input_or_setup')));return_code=2
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));return return_code


if __name__=='__main__':raise SystemExit(main())
