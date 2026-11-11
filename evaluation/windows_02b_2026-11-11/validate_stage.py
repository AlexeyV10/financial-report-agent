"""Preservation and preparation-only audit. Never produces guest acceptance."""
from pathlib import Path
import argparse,hashlib,json,subprocess
W=Path(__file__).resolve().parents[2];E=Path(__file__).parent
ALLOWED={'README.md','STATUS.md','docs/decisions.md','ПЛАН_РАЗВИТИЯ_WINDOWS.md','docs/windows/backlog.md','docs/windows/roadmap.json'}
PREFIX=ALLOWED-{'docs/windows/backlog.md','docs/windows/roadmap.json'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(folder,name,allowed):
    old=json.loads((E/name).read_text(encoding='utf8'));same=0;changed=[]
    for n,h in old['files'].items():
        assert (folder/n).is_file(),('missing',name,n)
        if sha(folder/n)==h:same+=1
        else:assert n in allowed,('changed',name,n);changed.append(n)
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=folder,text=True).strip();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=folder,text=True).strip();assert branch==old['branch']
    if name!='before.json':assert head==old['head']
    return dict(old_files=len(old['files']),unchanged=same,allowed_changed=sorted(changed),branch=branch,head_before=old['head'],checked_head=head)
def run(root=None,parent=None):
    before=json.loads((E/'before.json').read_text(encoding='utf8'));out=dict(worktree=snapshot(W,'before.json',ALLOWED))
    for n in PREFIX:
        old=subprocess.check_output(['git','show',before['head']+':'+n],cwd=W);assert hashlib.sha256(old).hexdigest()==before['files'][n];assert (W/n).read_bytes().endswith(old),('suffix',n)
    pins=json.loads((W/'data/releases/kp3_rc1/manifest.json').read_text())['file_sha256'];assert len(pins)==329
    for n,h in pins.items():assert sha(W/n)==h,('329pin',n)
    out['RC329pins_unchanged']=True
    roadmap=json.loads((W/'docs/windows/roadmap.json').read_text(encoding='utf8'));old=json.loads(subprocess.check_output(['git','show',before['head']+':docs/windows/roadmap.json'],cwd=W));assert len(roadmap['tasks'])==61 and roadmap['implemented_tasks']==[]
    for a,b in zip(roadmap['tasks'],old['tasks']):
        if a['id']!='WIN-02':assert a==b
    task=next(t for t in roadmap['tasks'] if t['id']=='WIN-02');assert task['status']=='host_validated_clean_vm_pending';assert task['acceptance_preparation']['status']=='resource_blocked_kit_prepared' and not task['acceptance_preparation']['guest_tested']
    for p in E.glob('*.json'):json.loads(p.read_text(encoding='utf-8-sig'))
    report=json.loads((E/'report.json').read_text());tests=json.loads((E/'tests.json').read_text());assert report['status']=='resource_blocked_kit_prepared' and not report['guest_accepted'] and not report['installer_executed']
    assert tests['synthetic_gate_controls']==17 and tests['actual_original_host_refusal'] and not tests['guest_acceptance_tested']
    kit=json.loads((E/'kit.json').read_text());assert kit['installer_sha256']=='f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf'
    if parent:
        out['parent']=snapshot(parent,'parent-before.json',set());assert not subprocess.check_output(['git','status','--porcelain'],cwd=parent).strip()
        installer=parent/'tmp/build-v4/ProjectPractice-WIN02-setup.exe';assert sha(installer)==kit['installer_sha256'] and installer.stat().st_size==22434104;out['original_installer_unchanged']=True
    if root:
        out['root']=snapshot(root,'root-before.json',ALLOWED)
        for n in PREFIX:assert (root/n).read_bytes().endswith((root/'tmp/windows-02b-bootstrap/root'/n).read_bytes())
        baseline=root/'tmp/windows-02b-bootstrap/old-ui-env-hashes.json';oldenv=json.loads(baseline.read_text(encoding='utf8'));envroot=root/'tmp/kp3-ui-cpython312';current={p.relative_to(envroot).as_posix():sha(p) for p in envroot.rglob('*') if p.is_file()};assert current==oldenv;out['old_UI_env']=dict(files=len(current),file_set_and_bytes_unchanged=True,baseline_sha256=sha(baseline))
    guard=W/'tmp/kit-v2/WIN02B-guest-kit/host-guard.private.json'
    if guard.exists():
        private=json.loads(guard.read_text());paths=ALLOWED|{p.decode('utf8') for p in subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=W).split(b'\0') if p}
        for n in paths:
            if (W/n).is_file():
                data=(W/n).read_text(encoding='utf-8-sig');assert private['host_hash'] not in data and private['salt'] not in data,('private comparison leak',n)
        out['private_guard_not_in_public_changes']=True
    out.update(status='passed',guest_acceptance_tested=False);return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path);p.add_argument('--parent',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();result=run(a.root,a.parent)
    if a.output:a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=True,indent=2))
