"""Observe actual process termination and absence of late writes, without any model."""
from pathlib import Path
from time import perf_counter,sleep
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
for p in ['src','evaluation']:sys.path.insert(0,str(ROOT/p))
from kp3_probes_v1.campaign import read,write_new,private_child,require
from kp3_probes_v1.workers import late_writer
from financial_assistant.agent import bounded,RunFailure


PLAN=dict(schema_version='kp3-worker-probe-plan-0.1',variants=['responsive_control','entered_worker_terminated_before_late_write'],trusted_code='evaluation/kp3_probes_v1/workers.py',operation='existing_agent.bounded',delay_s=1.5,deadline_s=.8,observe_after_return_s=1.7,expected='control completes; slow worker actually entered then timeout; no late file/result after wait',model_calls=0,comparison16_attempts=0)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--declare',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--report',type=Path);p.add_argument('--private',type=Path);a=p.parse_args()
    if a.declare:write_new(a.declare,PLAN);return 0
    require(read(a.plan)==PLAN,'worker_plan_drift');d=private_child(a.private);d.mkdir();rows=[]
    for variant in PLAN['variants']:
        folder=d/variant;folder.mkdir();t=perf_counter();timeout=False;result=None
        try:result=bounded(late_writer,(str(folder),0 if variant=='responsive_control'else PLAN['delay_s']),2 if variant=='responsive_control'else PLAN['deadline_s'])
        except RunFailure as e:require(e.code=='timeout','wrong worker failure');timeout=True
        elapsed=round((perf_counter()-t)*1000,3);require((folder/'started').is_file(),'worker never entered; not a late-response test')
        if variant=='responsive_control':require(not timeout and result==dict(completed=True)and(folder/'late').is_file(),'responsive worker failed')
        else:sleep(PLAN['observe_after_return_s']);require(timeout and result is None and not(folder/'late').exists(),'late response survived stop')
        rows.append(dict(variant=variant,passed=True,worker_entered=True,timeout=timeout,returned_result=result,late_file_present=(folder/'late').exists(),elapsed_ms=elapsed))
    report=dict(stage='KP3-15',planned=2,executed=2,passed=2,rows=rows,model_calls=0,scope='Actual trusted subprocess boundary; not actual model quality or comparison16');write_new(a.report,report);print(json.dumps(report));return 0


if __name__=='__main__':raise SystemExit(main())
