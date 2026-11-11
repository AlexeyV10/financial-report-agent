"""Developer-only trusted launcher. Separate cwd/runtime; no installer claim."""
from pathlib import Path
import argparse,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate',choices=['qt','wpf','qt-build']);p.add_argument('--scale',type=float,default=1);p.add_argument('--label',default='manual');p.add_argument('--probe',action='store_true');a=p.parse_args()
    out=ROOT/'tmp/runs'/a.label;out.mkdir(parents=True,exist_ok=False)
    python=Path(sys.executable).resolve();demo=ROOT/'tmp/demo'
    common=[str(python),str(ROOT),str(demo),str(out/'ui.json')]
    if a.candidate=='wpf':cmd=[str(ROOT/'tmp/wpf-build/WpfSpike.exe'),*common]
    else:
        cmd=([str(ROOT/'tmp/qt-dist-v3/QtSpike/QtSpike.exe')] if a.candidate=='qt-build' else [str(python),str(ROOT/'spikes/windows_01/qt_app.py')])
        for name,value in zip(['python','root','workspace','metrics'],common):cmd+=['--'+name,value]
    if a.probe:cmd+=['--probe']
    env=dict(os.environ)
    if a.candidate!='wpf':env['QT_SCALE_FACTOR']=str(a.scale)
    with (out/'stdout.txt').open('wb') as stdout,(out/'stderr.txt').open('wb') as stderr:
        proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'launch.json').write_text(json.dumps(dict(pid=proc.pid,candidate=a.candidate,scale=a.scale,command=cmd),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(pid=proc.pid,run=str(out))))
if __name__=='__main__':main()
