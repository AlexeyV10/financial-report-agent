"""Sequential same-machine process measurements; first run is not OS cold boot."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time,statistics
import psutil
ROOT=Path(__file__).resolve().parents[2]
def run(candidate,label,scale=1):
    subprocess.run([sys.executable,str(Path(__file__).parent/'launch.py'),candidate,'--label',label,'--scale',str(scale),'--probe'],check=True,capture_output=True)
    out=ROOT/'tmp/runs'/label;launch=json.loads((out/'launch.json').read_text(encoding='utf8'));pid=launch['pid'];process=psutil.Process(pid);started=process.create_time();begin=time.time();samples=[];ready=None;events=[]
    while time.time()-begin<25:
        try:
            procs=[process]+process.children(recursive=True);rss=private=0;ids=[]
            for p in procs:
                try:
                    m=p.memory_info();rss+=m.rss;private+=getattr(m,'private',0);ids.append(p.pid)
                except psutil.Error:pass
            samples.append(dict(elapsed_s=time.time()-started,rss_bytes=rss,private_bytes=private,pids=ids))
            try:events=json.loads((out/'ui.json').read_text(encoding='utf8'))
            except (OSError,ValueError):pass
            if ready is None and any(e['event']=='ready' for e in events):ready=time.time()-started
            if any(e['event']=='closed' for e in events):break
            if not process.is_running():break
        except psutil.Error:break
        time.sleep(.03)
    (out/'samples.json').write_text(json.dumps(samples,indent=2)+'\n',encoding='utf8')
    assert any(e['event']=='probe_complete' for e in events),(label,events[-3:])
    first=next(e for e in events if e['event']=='ready');table=next(e for e in events if e['event']=='table_probe');cancel=next(e for e in events if e['event']=='cancel_probe');closed=next(e for e in events if e['event']=='closed')
    idle=[s for s in samples if ready is not None and ready<=s['elapsed_s']<ready+.08]
    return dict(candidate=candidate,label=label,external_ready_s=ready,internal_ready_s=first['seconds'],effective_dpi_scale=first['dpi'],peak_tree_rss_bytes=max(s['rss_bytes'] for s in samples),peak_tree_private_bytes=max(s['private_bytes'] for s in samples),idle_tree_rss_bytes=statistics.median(s['rss_bytes'] for s in idle) if idle else None,idle_sample_count=len(idle),table_s=table['seconds'],table_rows=table['rows'],selected_value=table['selected'],cancel_signal_ms=cancel['signal_ms'],cancel_process_gone_at_300ms=not next(e for e in events if e['event']=='cancel_exit_probe')['still_running'],max_heartbeat_gap_ms=closed['max_heartbeat_gap_ms'],probe_completed=True,sample_count=len(samples))
def main():
    p=argparse.ArgumentParser();p.add_argument('--prefix',required=True);p.add_argument('--count',type=int,default=3);a=p.parse_args();results=[]
    # Alternating candidates, no concurrent GUI/load measurement.
    for i in range(a.count):
        for c in ['qt','wpf']:results.append(run(c,a.prefix+'-'+c+'-'+str(i+1)))
    for scale,label in [(1.2,'150'),(1.6,'200')]:results.append(run('qt',a.prefix+'-qt-'+label,scale))
    path=ROOT/'tmp'/('measurements-'+a.prefix+'.json');path.write_text(json.dumps(dict(protocol='same machine, no OS cache purge, external ready file polling <=30ms, tree RSS double counts shared pages, no model',runs=results),indent=2)+'\n',encoding='utf8');print(json.dumps(results))
if __name__=='__main__':main()
