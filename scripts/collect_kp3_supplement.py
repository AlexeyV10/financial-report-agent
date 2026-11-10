"""Collect separate known controls or replay them without feeding expected fields to runtime."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_run_v1.supplement import collect,replay


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['collect','replay']);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--observations',type=Path);a=p.parse_args()
    if a.action=='collect':r=collect(a.manifest,a.output);print(json.dumps(dict(financial_dev=len(r['financial_dev']),parser=len(r['parser']),scenario=len(r['scenario']),retrieval=len(r['retrieval']),model_calls=0)))
    else:
        if not a.observations:p.error('observations required')
        r=replay(a.manifest,a.observations,a.output);print(json.dumps({k:dict(x=r[k]['x'],n=r[k]['n'])for k in ['financial_dev','parser','scenario']}))
    return 0


if __name__=='__main__':raise SystemExit(main())
