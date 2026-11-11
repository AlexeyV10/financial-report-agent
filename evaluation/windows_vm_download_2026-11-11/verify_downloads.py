"""Offline integrity check; reads downloads, never executes an installer or ISO."""
from pathlib import Path
import hashlib,json,sys

EXPECTED={
 'VirtualBox-7.2.22-175245-Win.exe':(178101352,'afd0ff1656cbe04ed88ce619594ae021419d97cce89fa9bdc443e9a963f1713f'),
 'Windows11_Enterprise_Eval_26H2_x64_en-us.iso':(8225329152,'bc3f24086ebadc94489066b5ad78089e2cf5c3491e90e790bb81a2b199c10e38'),
}

def verify(directory):
 directory=Path(directory);files=[]
 for name,(size,expected_sha) in EXPECTED.items():
  path=directory/name
  assert path.is_file() and path.stat().st_size==size,name+' size'
  with path.open('rb') as stream:
   actual=hashlib.file_digest(stream,'sha256').hexdigest()
  assert actual==expected_sha,name+' SHA256'
  with path.open('rb') as stream:
   if path.suffix=='.exe':assert stream.read(2)==b'MZ','PE header'
   else:
    stream.seek(16*2048+1);assert stream.read(5)==b'CD001','ISO9660 descriptor'
  files.append(dict(name=name,bytes=size,sha256=actual,official_sha256_matches=True))
 signature=json.loads((directory/'virtualbox-signature.json').read_text(encoding='utf-8-sig'))
 assert signature['Status']=='Valid' and 'Oracle America' in signature['SignerSubject']
 sums=(directory/'VirtualBox-SHA256SUMS.txt').read_text(encoding='utf8')
 expected_exe=EXPECTED['VirtualBox-7.2.22-175245-Win.exe'][1]
 assert expected_exe+' *VirtualBox-7.2.22-175245-Win.exe' in sums
 return dict(integrity_passed=True,files=files,oracle_authenticode=signature,installer_executed=False,iso_mounted=False,guest_started=False,guest_acceptance=False)

if __name__=='__main__':
 directory=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'tmp/downloads'
 print(json.dumps(verify(directory),ensure_ascii=False,indent=2))
