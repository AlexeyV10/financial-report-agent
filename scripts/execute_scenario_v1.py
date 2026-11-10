"""Scenario12: own virtual simulation or real readiness only. No broker/model/source download."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import read_json,need
from financial_assistant.service_b import load_service_context
from financial_assistant.scenario_service import ScenarioContext,load_own_context,own_financial,execute_scenario


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__);p.add_argument('--request',type=Path,required=True);p.add_argument('--financial',type=Path);p.add_argument('--context',type=Path);p.add_argument('--run-id');args=p.parse_args()
    try:
        req=read_json(args.request)
        if req['data_mode']=='own_synthetic':
            need(args.context is None,'real_synthetic_mixing_forbidden')
            ctx=load_own_context();fin=read_json(args.financial)if args.financial else own_financial(ctx,req['financial_run_id'])
        else:
            if args.context is None or args.financial is None:raise ValueError('explicit_real_context_and_financial_required')
            ctx=ScenarioContext(load_service_context(args.context),ROOT/'tmp/scenario-runs');fin=read_json(args.financial)
        out=execute_scenario(fin,req,ctx,args.run_id);code=2 if out['status']=='error'else 0
    except Exception as e:out=dict(schema_version='kp3-scenario-setup-error-0.1',status='error',reason_code=getattr(e,'code','invalid_scenario_setup'),scenario=None,comparisons=None,model_calls=0);code=2
    print(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False));return code


if __name__=='__main__':raise SystemExit(main())
