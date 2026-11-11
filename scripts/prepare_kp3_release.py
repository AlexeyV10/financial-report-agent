"""Developer only: create a NEW private RC manifest draft, not a routine repair/verification."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'evaluation'),str(ROOT/'src')]
from kp3_release_v1.build import build
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--base-commit',required=True);a=p.parse_args();m=build(ROOT,a.output,a.base_commit);print(json.dumps(dict(release_id=m['release_id'],files=len(m['file_sha256']),scope=m['scope']),ensure_ascii=False))
