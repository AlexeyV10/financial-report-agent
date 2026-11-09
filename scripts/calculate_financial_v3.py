"""Explicit calculator0.3 CLI; no language parser, model, source download or service."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.calculation_contracts import validate_outcome
from financial_assistant.contracts_v2 import ContractError,read_json
from financial_assistant.fact_admission import load_context
from financial_assistant.financial_calculator import calculate


def main():
    sys.stdout.reconfigure(encoding='utf8')
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['catalog','dictionary','admission','request']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['bindings','source-checks','resources','index','config','lexicon','exports']:p.add_argument('--'+name,type=Path)
    a=p.parse_args();request={}
    try:
        request=read_json(a.request)
        ctx=load_context(a.catalog,a.dictionary,a.admission,a.bindings,a.source_checks,a.resources)
        gate=None
        if any([a.index,a.config,a.lexicon,a.exports]):
            if not all([a.index,a.config,a.lexicon]):raise ContractError('incomplete_retrieval_setup')
            gate=dict(db_path=a.index,config=read_json(a.config),lexicon=read_json(a.lexicon),export_paths=read_json(a.exports)if a.exports else None)
        out=calculate(ctx,request,retrieval_gate=gate)
    except (ContractError,OSError,KeyError,ValueError,TypeError) as exc:
        out=dict(schema_version='0.3',run_id='calculation-run',request_id='invalid-request',execution_status='error',financial_status=None,reason_code='context_invalid',clarification_fields=[],technical_details=dict(subsystem='setup',code=getattr(exc,'code','setup_unavailable')),financial_result=None)
    validate_outcome(out);print(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False))
    return 2 if out['execution_status']=='error' else 3 if out['execution_status']=='awaiting_clarification' else 0


if __name__=='__main__':raise SystemExit(main())
