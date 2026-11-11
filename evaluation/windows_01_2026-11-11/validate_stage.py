"""Read-only artifact/preservation audit for this spike, not old financial regression."""
from pathlib import Path
import argparse,hashlib,json,subprocess
W=Path(__file__).resolve().parents[2];E=Path(__file__).parent
ALLOWED={'README.md','STATUS.md','docs/decisions.md','ПЛАН_РАЗВИТИЯ_WINDOWS.md','docs/windows/backlog.md','docs/windows/roadmap.json'}
PREFIX={'README.md','STATUS.md','docs/decisions.md','ПЛАН_РАЗВИТИЯ_WINDOWS.md'}
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha(p):return sha_bytes(p.read_bytes())
def snapshot_check(folder,name,allowed):
    snap=json.loads((E/name).read_text(encoding='utf8'));changes=[];same=0
    for rel,expected in snap['files'].items():
        p=folder/rel
        assert p.is_file(),(name,'missing',rel)
        if sha(p)==expected:same+=1
        else:
            assert rel in allowed,(name,'unexpected modification',rel)
            changes.append(rel)
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=folder,text=True).strip();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=folder,text=True).strip()
    assert branch==snap['branch'],(name,'branch changed',branch)
    if name!='before.json':assert head==snap['head'],(name,'head changed',head)
    return dict(old_files=len(snap['files']),unchanged=same,allowed_changed=sorted(changes),old_branch=snap['branch'],old_head=snap['head'],checked_branch=branch,checked_head=head)
def run(root=None,parent=None):
    before=json.loads((E/'before.json').read_text(encoding='utf8'));out=dict(worktree=snapshot_check(W,'before.json',ALLOWED))
    for rel in PREFIX:
        old=subprocess.check_output(['git','show',before['head']+':'+rel],cwd=W)
        assert sha_bytes(old)==before['files'][rel],('original git bytes',rel)
        assert (W/rel).read_bytes().endswith(old),('prefix destroyed old suffix',rel)
    manifest=json.loads((W/'data/releases/kp3_rc1/manifest.json').read_text(encoding='utf8'))
    pins=manifest['file_sha256'];assert len(pins)==329
    for rel,expected in pins.items():assert sha(W/rel)==expected,('rc pin',rel)
    out['RC329pins_unchanged']=True;out['old_manifest_sha_unchanged']=sha(W/'data/releases/kp3_rc1/manifest.json')==before['files']['data/releases/kp3_rc1/manifest.json']
    roadmap=json.loads((W/'docs/windows/roadmap.json').read_text(encoding='utf8'));old=json.loads(subprocess.check_output(['git','show',before['head']+':docs/windows/roadmap.json'],cwd=W))
    assert len(roadmap['tasks'])==61 and roadmap['implemented_tasks']==[]
    for a,b in zip(roadmap['tasks'],old['tasks']):
        if a['id']!='WIN-01':assert a==b,('unrelated roadmap task',a['id'])
    assert next(x for x in roadmap['tasks'] if x['id']=='WIN-01')['status']=='feasibility_complete_with_limits'
    assert next(x for x in roadmap['tasks'] if x['id']=='WIN-02')['status']=='proposed_not_implemented'
    assert json.loads((E/'tests.json').read_text())['new_slice_tests']['passed']==12
    assert json.loads((E/'tests.json').read_text())['new_qt_tests']['passed']==3
    for f in E.glob('*.json'):json.loads(f.read_text(encoding='utf-8-sig'))
    assert all(x['passed'] for x in json.loads((E/'component-runs.json').read_text()))
    if parent:
        out['parent']=snapshot_check(parent,'parent-before.json',set())
        assert not subprocess.check_output(['git','status','--porcelain'],cwd=parent).strip(),'parent dirty'
    if root:
        out['dirty_root']=snapshot_check(root,'root-before.json',ALLOWED)
        for rel in PREFIX:
            original=root/'tmp/windows-01-bootstrap/root'/rel
            assert original.is_file() and (root/rel).read_bytes().endswith(original.read_bytes()),('root suffix',rel)
        out['root_historical_suffixes_preserved']=True
    out['old_ignored_venv']='No package/config changes targeted it; no pre-spike full ignored-venv byte inventory, so full before/after venv identity not asserted.'
    out['status']='passed';return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path);p.add_argument('--parent',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();result=run(a.root,a.parent)
    if a.output:a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=True,indent=2))
