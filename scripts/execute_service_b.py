"""One fixed service B entry point; same execute() is used by the minimal UI."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import read_json
from financial_assistant.service_b import execute,load_service_context


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--context',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--answers',type=Path);p.add_argument('--method',default='B');p.add_argument('--run-id');a=p.parse_args()
    try:
        result=execute(read_json(a.input),a.method,load_service_context(a.context),read_json(a.answers)if a.answers else None,a.run_id)
        code=2 if result['execution_status']in {'error','limit'}else 3 if result['execution_status']=='awaiting_clarification'else 4 if result['request_status']in {'unsupported','missing','conflict'}else 0
    except Exception as e:result=dict(schema_version='kp3-service-setup-error-0.1',execution_status='error',financial_status=None,financial_result=None,reason_code=getattr(e,'code','setup_unavailable'),model_calls=0);code=2
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));return code


if __name__=='__main__':raise SystemExit(main())
