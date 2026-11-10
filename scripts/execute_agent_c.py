"""Actual bounded C over trusted local context. No B/replay/mock fallback."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import read_json
from financial_assistant.service_b import load_service_context
from financial_assistant.agent_model_v2 import load_agent_model
from financial_assistant.agent_c import execute_c
from financial_assistant.agent_contracts_v2 import AgentLimits


def main():
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser(description=__doc__);p.add_argument('--context',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--answers',type=Path);p.add_argument('--run-id');p.add_argument('--max-search-results',type=int,default=32);p.add_argument('--max-calls',type=int,default=8);args=p.parse_args()
    try:
        a=execute_c(read_json(args.input),load_service_context(args.context),load_agent_model(ROOT/'data/config/local_model.json'),read_json(args.answers)if args.answers else None,args.run_id,AgentLimits(max_calls=args.max_calls,max_search_results=args.max_search_results))
        code=2 if a['execution_status']in {'error','limit'}else 3 if a['execution_status']=='awaiting_clarification'else 4 if a['request_status']in {'unsupported','missing','conflict'}else 0
    except Exception as e:a=dict(schema_version='kp3-agent-setup-error-0.1',execution_status='error',financial_result=None,financial_status=None,reason_code=getattr(e,'code','setup_unavailable'),model_calls=0);code=2
    print(json.dumps(a,ensure_ascii=False,indent=2,allow_nan=False));return code


if __name__=='__main__':raise SystemExit(main())
