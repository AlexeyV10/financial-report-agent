"""Actual one-shot A CLI. No alternative adapter, retry or B/C fallback."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import read_json
from financial_assistant.service_b import load_service_context
from financial_assistant.one_shot_a import execute_a
from financial_assistant.one_shot_model import load_one_shot_model
from financial_assistant.one_shot_contracts import SelectionLimits


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__);p.add_argument('--context',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--answers',type=Path);p.add_argument('--run-id');p.add_argument('--top-k',type=int,default=32);args=p.parse_args()
    try:
        a=execute_a(read_json(args.input),load_service_context(args.context),load_one_shot_model(ROOT/'data/config/local_model.json'),read_json(args.answers)if args.answers else None,args.run_id,SelectionLimits(top_k=args.top_k));code=2 if a['execution_status']in {'error','limit'}else 3 if a['execution_status']=='awaiting_clarification'else 4 if a['request_status']in {'unsupported','missing','conflict'}else 0
    except Exception as e:a=dict(schema_version='kp3-a-setup-error-0.1',execution_status='error',financial_status=None,financial_result=None,reason_code=getattr(e,'code','setup_unavailable'),model_calls=0);code=2
    print(json.dumps(a,ensure_ascii=False,indent=2,allow_nan=False));return code


if __name__=='__main__':raise SystemExit(main())
