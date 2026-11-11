"""Prepare a local-only guest kit, preserving the already tested installer bytes."""
from pathlib import Path
import argparse,hashlib,json,os,secrets,shutil,subprocess,winreg,zipfile
ROOT=Path(__file__).resolve().parents[2]
SHA='f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf';SIZE=22434104
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def fingerprint(salt):
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,'SOFTWARE/Microsoft/Cryptography'.replace('/','\\'),0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as k:identity=winreg.QueryValueEx(k,'MachineGuid')[0]
    return hashlib.sha256((salt+'\n'+identity).encode('utf8')).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installer',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);a=parser.parse_args()
    assert a.installer.stat().st_size==SIZE and sha(a.installer)==SHA,'Different installer: do not relabel it with the old receipt'
    out=a.out.resolve();assert out.is_relative_to(ROOT/'tmp') and not out.exists();out.mkdir(parents=True)
    kit=out/'WIN02B-guest-kit';kit.mkdir();shutil.copyfile(a.installer,kit/'ProjectPractice-WIN02-setup.exe')
    framework=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319';csc=framework/'csc.exe';source=ROOT/'spikes/windows_02b'
    common=[str(csc),'/nologo','/target:exe','/platform:x64','/codepage:65001','/reference:System.Web.Extensions.dll','/reference:System.Management.dll']
    for name,entry,extra in [('GuestEvidence.exe','GuestEvidence',[]),('CollectorTests.exe','CollectorTests',[str(source/'CollectorTests.cs')])]:
        target=kit/name if name=='GuestEvidence.exe' else out/name
        cmd=common+['/main:'+entry,'/out:'+str(target),str(source/'GuestEvidence.cs')]+extra
        p=subprocess.run(cmd,capture_output=True);(out/(name+'.compile.log')).write_bytes(p.stdout+p.stderr);assert p.returncode==0,(p.stdout+p.stderr).decode('utf8',errors='replace')
    salt=secrets.token_hex(24)
    payload=ROOT.parents[0]/'windows-02-worktree/tmp/build-v4/payload/payload.json';assert payload.is_file()
    save(kit/'host-guard.private.json',dict(schema='win02b-host-guard-1',salt=salt,host_hash=fingerprint(salt),payload_manifest_sha256=sha(payload),note='Private accidental-host guard; not authentication of clean VM. Do not publish device-derived guard.'))
    save(kit/'provenance.json',dict(schema='win02b-provenance-1',session_id='guest_run_01',kind='not_set',os_source='',clean_state_note='',clean_state_declared=False))
    shutil.copyfile(source/'RUNBOOK_RU.md',kit/'RUNBOOK_RU.md')
    save(kit/'artifact.json',dict(installer_sha256=SHA,installer_bytes=SIZE,unchanged_WIN02_v4=True,signed=False,collector_sha256=sha(kit/'GuestEvidence.exe'),guest_tested=False,own_code_license='not_selected'))
    controls=subprocess.run([str(out/'CollectorTests.exe')],capture_output=True,check=True);(out/'synthetic-controls.json').write_bytes(controls.stdout)
    refusal=subprocess.run([str(kit/'GuestEvidence.exe'),'preflight'],cwd=kit,capture_output=True);(out/'actual-host-refusal.json').write_bytes(refusal.stdout)
    assert refusal.returncode==21 and json.loads(refusal.stdout)['status']=='original_host_rejected'
    assert not json.loads(refusal.stdout)['guest_accepted']
    archive=out/'WIN02B-guest-kit.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(kit.iterdir()):z.write(p,'WIN02B-guest-kit/'+p.name)
    with zipfile.ZipFile(archive) as z:
        embedded=z.read('WIN02B-guest-kit/ProjectPractice-WIN02-setup.exe');assert len(embedded)==SIZE and hashlib.sha256(embedded).hexdigest()==SHA
    result=dict(schema='win02b-kit-1',installer_sha256=SHA,installer_bytes=SIZE,installer_rebuilt=False,kit_files=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(kit.iterdir()) if p.name!='host-guard.private.json'],private_host_guard_included=True,zip_bytes=archive.stat().st_size,zip_sha256=sha(archive),collector_sha256=sha(kit/'GuestEvidence.exe'),synthetic_controls=json.loads(controls.stdout),actual_host_refusal=json.loads(refusal.stdout),guest_acceptance_tested=False,private_guard_not_for_public_git=True)
    save(out/'kit-receipt.json',result);print(json.dumps(result))
if __name__=='__main__':main()
