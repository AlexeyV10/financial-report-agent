"""Host-only installer lifecycle/measurements. Never labels this host a clean VM."""
from pathlib import Path
import argparse,hashlib,json,os,stat,subprocess,sys,tempfile,time,winreg
import psutil
ROOT=Path(__file__).resolve().parents[2];LOCAL=Path(os.environ['LOCALAPPDATA']);DATA=LOCAL/'ProjectPractice/WIN02';INSTALL=LOCAL/'Programs/Проектная практика WIN02'
SHORTCUT=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Проектная практика WIN02/Финансовые документы.lnk';KEY='Software/Microsoft/Windows/CurrentVersion/Uninstall/ProjectPracticeWIN02'.replace('/','\\')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def key_exists():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY,0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY):return True
    except FileNotFoundError:return False
def path_hashes():
    out={}
    for label,hive,key in [('user',winreg.HKEY_CURRENT_USER,'Environment'),('machine',winreg.HKEY_LOCAL_MACHINE,'SYSTEM/CurrentControlSet/Control/Session Manager/Environment')]:
        with winreg.OpenKey(hive,key.replace('/','\\')) as k:
            try:value=winreg.QueryValueEx(k,'Path')[0]
            except FileNotFoundError:value=''
        out[label]=hashlib.sha256(value.encode('utf8')).hexdigest()
    return out
def env():
    e=dict(os.environ);e['PATH']=str(Path(os.environ['WINDIR'])/'System32');e['PYTHONHOME']='C:/WIN02-unused';e['PYTHONPATH']='C:/WIN02-unused';return e
def new_run(before):
    for _ in range(200):
        added=set((DATA/'runs').glob('*'))-before
        if len(added)==1 and (next(iter(added))/'host.json').exists():return next(iter(added))
        time.sleep(.02)
    raise RuntimeError('no unique own host receipt')
def install(build):
    assert not INSTALL.exists() and not key_exists() and not SHORTCUT.exists(),'Preserve pre-existing installation; inspect it first.'
    before=path_hashes();save(ROOT/'tmp/host-before.json',dict(path_hashes=before,install_existed=False,registry_existed=False,shortcut_existed=False))
    DATA.mkdir(parents=True,exist_ok=True);sentinel=DATA/'preservation-control.txt'
    if sentinel.exists():assert sentinel.read_text(encoding='utf8')=='Own WIN-02 uninstall preservation control.\n','Preserve unrelated data'
    else:sentinel.write_text('Own WIN-02 uninstall preservation control.\n',encoding='utf8')
    started=time.perf_counter();p=subprocess.run([str(build/'ProjectPractice-WIN02-setup.exe'),'/S'],cwd=os.environ['TEMP'],timeout=30);assert p.returncode==0,p.returncode
    assert INSTALL.is_dir() and key_exists() and SHORTCUT.is_file();manifest=json.loads((INSTALL/'payload.json').read_text(encoding='utf8'))
    for rel,h in manifest['files'].items():assert sha(INSTALL/rel)==h and (INSTALL/rel).stat().st_file_attributes&stat.FILE_ATTRIBUTE_READONLY,rel
    assert path_hashes()==before
    result=dict(environment='existing host, not clean VM',installation_s=time.perf_counter()-started,installer_exit=p.returncode,per_user=True,admin_used=False,unicode_space_path=True,outside_repository=True,shortcut_created=True,HKCU_uninstall_created=True,private_payload_files=len(manifest['files'])+1,readonly_payload=True,PATH_unchanged=True,sentinel_sha256=sha(sentinel))
    save(ROOT/'tmp/host-install.json',result);print(json.dumps(result))
def diagnose():
    before=set((DATA/'runs').glob('*'));p=subprocess.run([str(INSTALL/'ProjectPractice.exe'),'--diagnose'],cwd=os.environ['TEMP'],env=env(),timeout=20);run=new_run(before);assert p.returncode==0,(run/'host.json').read_text(encoding='utf8');d=json.loads((run/'runtime.json').read_text(encoding='utf8'))
    assert d['display']=='15.00' and Path(d['executable']).resolve()==(INSTALL/'runtime/python.exe').resolve();assert d['isolated']==1 and d['no_user_site']==1 and not d['qt_present'];assert all(Path(x).resolve().is_relative_to(INSTALL) for x in d['path'])
    summary={k:v for k,v in d.items() if k not in ['path','executable','prefix']};summary.update(environment='existing host, not clean VM',independent_cwd=True,hostile_python_environment_ignored=True,all_python_paths_inside_install=True)
    save(ROOT/'tmp/host-diagnostic.json',summary);print(json.dumps(dict(diagnostic='passed',display=d['display'],private_python=True)))
def one_run(probe):
    before=set((DATA/'runs').glob('*'));start=time.time();p=subprocess.Popen([str(INSTALL/'ProjectPractice.exe')]+(['--probe'] if probe else []),cwd=os.environ['TEMP'],env=env(),creationflags=subprocess.CREATE_NO_WINDOW);parent=psutil.Process(p.pid);samples=[];ready=None;run=new_run(before);events=[]
    while time.time()-start<15:
        try:
            procs=[parent]+parent.children(recursive=True);rss=private=0
            for child in procs:
                try:m=child.memory_info();rss+=m.rss;private+=m.private
                except psutil.Error:pass
            elapsed=time.time()-start;samples.append(dict(seconds=elapsed,rss=rss,private=private))
            try:events=json.loads((run/'ui.json').read_text(encoding='utf8'))
            except (FileNotFoundError,ValueError):pass
            if ready is None and any(e['event']=='ready' for e in events):ready=elapsed
            if not probe and ready and elapsed>ready+1.2:p.kill();p.wait(timeout=3);break
            if probe and any(e['event']=='closed' for e in events):p.wait(timeout=3);break
            if p.poll() is not None:break
        except psutil.Error:break
        time.sleep(.02)
    assert ready is not None,(run/'host.json').read_text(encoding='utf8')
    if probe:
        assert any(e['event']=='probe_complete' for e in events)
        assert len([e for e in events if e['event']=='calculation' and e['display']=='15.00'])==2
        assert len([e for e in events if e['event']=='render'])==5
        assert [e['exit'] for e in events if e['event']=='job_error']==[23]
        assert not next(e for e in events if e['event']=='cancel_exit_probe')['still_running']
    idle=[s['rss'] for s in samples if ready+.3<s['seconds']<ready+1.1] if not probe else []
    import statistics
    result=dict(run=run.name,probe=probe,external_ready_s=ready,peak_tree_RSS_bytes=max(s['rss'] for s in samples),peak_tree_private_bytes=max(s['private'] for s in samples),idle_tree_RSS_median=statistics.median(idle) if idle else None,idle_samples=len(idle),max_heartbeat_gap_ms=events[-1].get('max_heartbeat_gap_ms') if probe else None)
    save(ROOT/'tmp'/('samples-'+run.name+'.json'),dict(result=result,samples=samples,events=events));return result
def measures():
    results=[]
    for _ in range(3):results.append(one_run(False));results.append(one_run(True))
    save(ROOT/'tmp/host-measurements.json',dict(environment='existing host, not clean VM',protocol='3 idle and 3 full component runs, sequential. External ready polls20ms plus scheduling. No cache purge/reboot. Idle sampled ready+.3 through+1.1s, idle-only window terminated by harness; separate normal close observed manually. Tree RSS double-counts shared pages.',runs=results))
    print(json.dumps(results))
def parent_crash():
    before=set((DATA/'runs').glob('*'));p=subprocess.Popen([str(INSTALL/'ProjectPractice.exe'),'--probe'],cwd=os.environ['TEMP'],env=env(),creationflags=subprocess.CREATE_NO_WINDOW);run=new_run(before);parent=psutil.Process(p.pid);observed=[]
    for _ in range(500):
        try:e=json.loads((run/'ui.json').read_text(encoding='utf8'))
        except (FileNotFoundError,ValueError):e=[]
        if any(x['event']=='job_start' and x['operation']=='slow' for x in e):
            observed=[x for x in parent.children(recursive=True) if Path(x.exe()).resolve()==(INSTALL/'runtime/python.exe').resolve()]
            if observed:break
        time.sleep(.01)
    assert observed,'No actual own slow worker observed';ids=[dict(pid=x.pid,created=x.create_time()) for x in observed];p.kill();p.wait(timeout=3);time.sleep(.5)
    for item in ids:
        try:assert psutil.Process(item['pid']).create_time()!=item['created'],'orphan worker survived'
        except psutil.NoSuchProcess:pass
    result=dict(environment='existing host, not clean VM',actual_slow_worker_count=len(ids),parent_hard_killed=True,worker_absent_at_500ms=True,kill_on_job_close=True)
    save(ROOT/'tmp/host-parent-crash.json',result);print(json.dumps(result))
def uninstall():
    assert (INSTALL/'install.ini').is_file() and key_exists();before=json.loads((ROOT/'tmp/host-before.json').read_text());sentinel=DATA/'preservation-control.txt';before_data={p.relative_to(DATA).as_posix():sha(p) for p in DATA.rglob('*') if p.is_file()}
    marker=INSTALL/'user-preserved-control.txt';assert not marker.exists();marker.write_text('Own unknown-file preservation control.\n',encoding='utf8');marker_sha=sha(marker)
    proc=subprocess.run([str(INSTALL/'Uninstall.exe'),'/S'],cwd=os.environ['TEMP'],timeout=20)
    for _ in range(500):
        if not (INSTALL/'ProjectPractice.exe').exists() and not key_exists() and not SHORTCUT.exists():break
        time.sleep(.02)
    assert not (INSTALL/'ProjectPractice.exe').exists() and not (INSTALL/'runtime/python.exe').exists() and not key_exists() and not SHORTCUT.exists()
    assert marker.is_file() and sha(marker)==marker_sha
    assert all((DATA/name).is_file() and sha(DATA/name)==h for name,h in before_data.items())
    assert path_hashes()==before['path_hashes']
    for p in psutil.process_iter(['exe']):
        try:assert p.info['exe'] is None or not Path(p.info['exe']).is_relative_to(INSTALL),('own installed process survived',p.pid)
        except psutil.Error:pass
    result=dict(environment='existing host, not clean VM',uninstaller_launcher_exit=proc.returncode,owned_program_removed=True,shortcut_removed=True,HKCU_uninstall_removed=True,user_data_preserved_files=len(before_data),unknown_install_file_preserved=True,no_recursive_delete=True,PATH_unchanged=True,no_own_orphan_process=True,install_folder_left_for_unknown_file=True)
    save(ROOT/'tmp/host-uninstall.json',result);print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['install','diagnose','measures','parent-crash','uninstall']);p.add_argument('--build',type=Path);a=p.parse_args()
    if a.phase=='install':install(a.build.resolve())
    else:{'diagnose':diagnose,'measures':measures,'parent-crash':parent_crash,'uninstall':uninstall}[a.phase]()
