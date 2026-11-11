"""Read-only WIN-02 preservation/receipt audit; never a substitute for clean VM."""
from pathlib import Path
import argparse,hashlib,json,subprocess
W=Path(__file__).resolve().parents[2];E=Path(__file__).parent
ALLOWED={'README.md','STATUS.md','docs/decisions.md','ПЛАН_РАЗВИТИЯ_WINDOWS.md','docs/windows/backlog.md','docs/windows/roadmap.json'}
PREFIX={'README.md','STATUS.md','docs/decisions.md','ПЛАН_РАЗВИТИЯ_WINDOWS.md'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snap(folder,name,allowed):
    old=json.loads((E/name).read_text(encoding='utf8'));changes=[];same=0
    for rel,h in old['files'].items():
        p=folder/rel;assert p.is_file(),('missing',name,rel)
        if sha(p)==h:same+=1
        else:assert rel in allowed,('unexpected change',name,rel);changes.append(rel)
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=folder,text=True).strip();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=folder,text=True).strip()
    assert branch==old['branch'],('branch',name)
    if name!='before.json':assert head==old['head'],('head',name)
    return dict(old_files=len(old['files']),unchanged=same,allowed_changed=sorted(changes),head_before=old['head'],checked_head=head,branch=branch)
def run(root=None,parent=None):
    before=json.loads((E/'before.json').read_text(encoding='utf8'));out=dict(worktree=snap(W,'before.json',ALLOWED))
    for rel in PREFIX:
        old=subprocess.check_output(['git','show',before['head']+':'+rel],cwd=W);assert hashlib.sha256(old).hexdigest()==before['files'][rel];assert (W/rel).read_bytes().endswith(old),('historical suffix',rel)
    rc=json.loads((W/'data/releases/kp3_rc1/manifest.json').read_text())['file_sha256'];assert len(rc)==329
    for rel,h in rc.items():assert sha(W/rel)==h,('frozen329pin',rel)
    out['RC329pins_unchanged']=True
    r=json.loads((W/'docs/windows/roadmap.json').read_text(encoding='utf8'));old=json.loads(subprocess.check_output(['git','show',before['head']+':docs/windows/roadmap.json'],cwd=W))
    assert len(r['tasks'])==61 and r['implemented_tasks']==[]
    for a,b in zip(r['tasks'],old['tasks']):
        if a['id']!='WIN-02':assert a==b,('unrelated roadmap',a['id'])
    assert next(t for t in r['tasks'] if t['id']=='WIN-02')['status']=='host_validated_clean_vm_pending'
    assert next(t for t in r['tasks'] if t['id']=='WIN-03')['status']=='proposed_not_implemented'
    for p in E.glob('*.json'):json.loads(p.read_text(encoding='utf-8-sig'))
    tests=json.loads((E/'tests.json').read_text());assert tests['installed_package_tests']['passed']==10 and tests['private_original_root_regression']['passed']==69
    report=json.loads((E/'report.json').read_text());assert report['status']=='host_validated_clean_vm_pending' and report['new_model_calls']==0 and not report['public_binary_uploaded']
    if parent:
        out['parent']=snap(parent,'parent-before.json',set());assert not subprocess.check_output(['git','status','--porcelain'],cwd=parent).strip()
    if root:
        out['root']=snap(root,'root-before.json',ALLOWED)
        for rel in PREFIX:assert (root/rel).read_bytes().endswith((root/'tmp/windows-02-bootstrap/root'/rel).read_bytes()),('root suffix',rel)
        baseline=root/'tmp/windows-02-bootstrap/old-ui-env-hashes.json'
        if baseline.exists():
            old_env=json.loads(baseline.read_text(encoding='utf8'));envroot=root/'tmp/kp3-ui-cpython312';current={p.relative_to(envroot).as_posix():sha(p) for p in envroot.rglob('*') if p.is_file()};assert current==old_env,'old UI environment changed'
            out['old_UI_env']=dict(files=len(current),all_file_hashes_and_file_set_unchanged=True,baseline_sha256=sha(baseline))
        out['root_historical_suffixes_preserved']=True
    out['status']='passed';out['clean_VM_tested']=False;return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path);p.add_argument('--parent',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();out=run(a.root,a.parent)
    if a.output:a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(out,ensure_ascii=True,indent=2))
