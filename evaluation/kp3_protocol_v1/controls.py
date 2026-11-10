"""Prior actual13 envelopes reused ONLY to test evaluator, never new14 method responses."""
from copy import deepcopy
from .common import read

def prior_controls(root,inputs,gold):
    rows=read(root/'evaluation/kp3_13_2026-11-10/ui-runs.json')['records'];cs={c['case_id']:c for c in inputs['cases']};gs={g['case_id']:g for g in gold['cases']};out=[]
    for record in rows:
        p=record['payload'];a=p['result']
        if p['kind']!='financial'or a['financial_status']!='answered':continue
        if a['method']=='B'and a['financial_result']['operation_id']=='direct_fact_v1'and p['source']['kind']=='form':cid='cmp-02'
        elif a['financial_result']['operation_id']=='absolute_change_v1'and a['assumption_checks']:cid='cmp-29'
        else:continue
        case=deepcopy(cs[cid]);g=deepcopy(gs[cid]);case['case_id']=g['case_id']='prior13-'+a['run_id'];case['source']=deepcopy(p['source']);case['answers']=deepcopy(p['answers'])
        # Input08 text grammar retains the ENTIRE question as the premise fragment;
        # explicit form assumptions in the new suite retain the supplied word fragment.
        if case['source']['kind']=='text':
            for check in g['assumption_checks']:check['assumption']['text_fragment']=case['source']['question']
        out.append(dict(case=case,gold=g,answer=deepcopy(a),record=deepcopy(record),origin='prior_actual13_evaluator_control_not_new14_answer'))
    return out
