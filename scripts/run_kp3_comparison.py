"""Prepare an immutable measurement manifest or run/resume exact frozen138 native attempts."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_run_v1.runtime import prepare,run


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--context',type=Path);p.add_argument('--resources',type=Path);p.add_argument('--private',type=Path);p.add_argument('--raw',type=Path);p.add_argument('--progress',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if not all([a.context,a.resources,a.private]):p.error('context/resources/private required')
        m=prepare(a.context.resolve(),a.resources.resolve(),a.private,a.manifest);print(json.dumps(dict(planned=len(m['order']),budget=m['budget'],actual_attempts=0)))
    else:
        if not all([a.raw,a.progress]):p.error('raw/progress required')
        print(json.dumps(run(a.manifest,a.raw,a.progress)))
    return 0


if __name__=='__main__':raise SystemExit(main())
