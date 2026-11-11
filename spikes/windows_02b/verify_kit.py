"""Local kit integrity/negative controls; does not run the installer."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
SHA='f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);a=p.parse_args();build=a.build.resolve();kit=build/'WIN02B-guest-kit';receipt=json.loads((build/'kit-receipt.json').read_text(encoding='utf8'))
    assert sha(kit/'ProjectPractice-WIN02-setup.exe')==SHA and (kit/'ProjectPractice-WIN02-setup.exe').stat().st_size==22434104
    assert sha(build/'WIN02B-guest-kit.zip')==receipt['zip_sha256']
    with zipfile.ZipFile(build/'WIN02B-guest-kit.zip') as z:
        assert z.testzip() is None
        assert hashlib.sha256(z.read('WIN02B-guest-kit/ProjectPractice-WIN02-setup.exe')).hexdigest()==SHA
        assert len(z.namelist())==6 and all(n.startswith('WIN02B-guest-kit/') for n in z.namelist())
    template=json.loads((kit/'provenance.json').read_text());assert template['clean_state_declared'] is False and template['kind']=='not_set'
    refusal=subprocess.run([str(kit/'GuestEvidence.exe'),'preflight'],capture_output=True);d=json.loads(refusal.stdout);assert refusal.returncode==21 and d['status']=='original_host_rejected' and not d['guest_environment_collected']
    invalid=subprocess.run([str(kit/'GuestEvidence.exe'),'install-and-pass'],capture_output=True);assert invalid.returncode==64 and not json.loads(invalid.stdout)['guest_accepted']
    modified=build/'deliberately-modified-own-installer.exe';assert not modified.exists();data=bytearray((kit/'ProjectPractice-WIN02-setup.exe').read_bytes());data[-1]^=1;modified.write_bytes(data)
    rejected=ROOT/'tmp/rejected-modified-kit';assert not rejected.exists()
    proc=subprocess.run([sys.executable,str(Path(__file__).parent/'prepare_kit.py'),'--installer',str(modified),'--out',str(rejected)],capture_output=True)
    assert proc.returncode!=0 and not rejected.exists();(build/'wrong-installer-refusal.txt').write_bytes(proc.stdout+proc.stderr)
    result=dict(kit_integrity_passed=True,installer_bytes_unchanged=True,zip_installer_sha_matches=True,provenance_template_unconfirmed=True,actual_original_host_refusal=True,invalid_command_rejected=True,modified_same_size_installer_rejected_before_output=True,synthetic_gate_controls=receipt['synthetic_controls']['synthetic_gate_controls_passed'],guest_acceptance_tested=False,installer_executed=False,model_calls=0)
    (build/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result))
if __name__=='__main__':main()
