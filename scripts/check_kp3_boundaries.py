"""Declare or execute developer-known isolated fault probes; never run comparison16."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'));sys.path.insert(0,str(ROOT/'src'))
from kp3_probes_v1.plan import build_plan
from kp3_probes_v1.campaign import read,write_new,run_campaign,private_child


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--declare',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--report',type=Path);p.add_argument('--private',type=Path);a=p.parse_args()
    if a.declare:
        if a.plan or a.report or a.private:p.error('declare is separate from execution')
        plan=build_plan();write_new(a.declare,plan);print(json.dumps(dict(planned=len(plan['rows']),denominators=plan['denominators'])));return 0
    if not(a.plan and a.report and a.private):p.error('plan, report, private required')
    plan=read(a.plan)
    if plan!=build_plan():raise ValueError('predeclared_plan_drift')
    private_child(a.private);report=run_campaign(plan,a.report,a.private);print(json.dumps({k:v for k,v in report.items()if k!='observations'}));return 0 if report['total']==report['passed']else 1


if __name__=='__main__':raise SystemExit(main())
