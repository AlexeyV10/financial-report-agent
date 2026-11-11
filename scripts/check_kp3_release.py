"""Verify declared RC/code/resources. Optional known B smoke; no automatic model start/chat."""
from pathlib import Path
import argparse,json,os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'evaluation'),str(ROOT/'src')]
from kp3_release_v1.verify import check


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,default=ROOT/'data/releases/kp3_rc1/manifest.json');p.add_argument('--profile',choices=['code','B','A','C','UI'],default='code');p.add_argument('--resources',type=Path);p.add_argument('--context',type=Path);p.add_argument('--report',type=Path,required=True);p.add_argument('--smoke',action='store_true');p.add_argument('--work-dir',type=Path);a=p.parse_args()
    target=a.report.resolve();private=(ROOT/'tmp').resolve()
    if not target.is_relative_to(private)or target==private or target.exists():p.error('Report must be a NEW file under this checkout tmp/')
    out=check(ROOT,a.manifest,a.profile,a.resources,a.context)
    if a.smoke:
        if a.profile!='B':out.update(execution_status='error',reason_code='smoke_requires_explicit_B',runtime_ready=False)
        elif out['runtime_ready']:
            try:
                from kp3_release_v1.smoke import run
                out['smoke']=run(ROOT,a.context,a.work_dir);out['execution_status']='completed'if out['smoke']['passed']else'error';out['reason_code']='ready_and_known_smoke_passed'if out['smoke']['passed']else'release_smoke_failed'
            except Exception as e:out.update(execution_status='error',reason_code=getattr(e,'code','release_smoke_failed'),error_type=type(e).__name__)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf8',newline='\n')as f:json.dump(out,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps({k:out[k]for k in ['schema_version','release_id','profile','execution_status','reason_code','runtime_ready','model_chat_requests']},ensure_ascii=False));return 0 if out['execution_status']=='completed'else 2


if __name__=='__main__':raise SystemExit(main())
