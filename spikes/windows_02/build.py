"""Explicit local-only, pinned-input WIN-02 packaging recipe. No pip/global installs."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
PY_SHA='4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
NSIS_SHA='ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'
CORE=['__init__','fact_admission','financial_calculator','calculation_contracts','catalog','document_extraction','retrieval_v2','contracts_v2','contracts']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def copy(source,dest):dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
def extract(archive,target):
    with zipfile.ZipFile(archive) as z:
        for n in z.namelist():
            p=Path(n);assert not p.is_absolute() and '..' not in p.parts and ':' not in n,n
        z.extractall(target)
def main():
    p=argparse.ArgumentParser();p.add_argument('--downloads',type=Path,required=True);p.add_argument('--wheels',type=Path,required=True);p.add_argument('--demo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();assert out.is_relative_to(ROOT/'tmp') and not out.exists(),'Use new own tmp output directory';out.mkdir(parents=True)
    payload=out/'payload';payload.mkdir();runtime=payload/'runtime';runtime.mkdir()
    py=a.downloads/'python-3.12.10-embed-amd64.zip';nsiszip=a.downloads/'nsis-3.13.zip';assert sha(py)==PY_SHA and sha(nsiszip)==NSIS_SHA
    extract(py,runtime);tool=out/'tools';tool.mkdir();extract(nsiszip,tool)
    wheel_info=json.loads((ROOT/'evaluation/windows_01_2026-11-11/wheels.json').read_text(encoding='utf8'))['files'];wheels=[]
    for prefix in ['pypdfium2-5.15.2-','pillow-13.0.0-']:
        item=next(x for x in wheel_info if x['file'].startswith(prefix));wheel=a.wheels/item['file'];assert sha(wheel)==item['sha256'];extract(wheel,runtime/'packages');wheels.append(item)
    (runtime/'python312._pth').write_text('python312.zip\n.\npackages\n../app/src\n../app/spikes/windows_01\n../app/spikes/windows_02\n',encoding='ascii')
    for name in CORE:copy(ROOT/'src/financial_assistant'/(name+'.py'),payload/'app/src/financial_assistant'/(name+'.py'))
    for name in ['adapter.py','common.py','renderer.py','worker.py']:copy(ROOT/'spikes/windows_01'/name,payload/'app/spikes/windows_01'/name)
    copy(ROOT/'spikes/windows_02/runtime_probe.py',payload/'app/spikes/windows_02/runtime_probe.py')
    for name in ['catalog.json','dictionary.json','admission.json','manifest.json','own-demo-v1.pdf']:copy(a.demo/name,payload/'app/assets/demo'/name)
    assert sha(payload/'app/assets/demo/own-demo-v1.pdf')=='c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451'
    notices=payload/'licenses';notices.mkdir();copy(runtime/'LICENSE.txt',notices/'CPython-LICENSE.txt');copy(a.downloads/'python-3.12.10-embed-amd64.zip.spdx.json',notices/'CPython-SBOM.spdx.json');copy(tool/'nsis-3.13/COPYING',notices/'NSIS-COPYING.txt')
    (notices/'OWN-CODE-STATUS.txt').write_text('Own project code license has not been selected. This is a local feasibility artifact, not a signed public release. The own fictional demo is permitted for redistribution by the project owner. Upstream notices are preserved in runtime/packages/*dist-info/licenses and the CPython LICENSE. Microsoft .NET Framework is an OS prerequisite, not bundled here.\n',encoding='utf8')
    framework=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319';csc=framework/'csc.exe'
    cmd=[str(csc),'/nologo','/target:winexe','/platform:x64','/optimize+','/codepage:65001','/main:RuntimeHost','/out:'+str(payload/'ProjectPractice.exe'),'/win32manifest:'+str(ROOT/'spikes/windows_01/wpf.manifest')]
    for name in ['PresentationFramework','PresentationCore','WindowsBase','UIAutomationTypes']:cmd.append('/reference:'+str(framework/'WPF'/(name+'.dll')))
    original_wpf=(ROOT/'spikes/windows_01/WpfSpike.cs').read_text(encoding='utf8')
    needle='ProcessStartInfo(python,"-u "+Quote'
    assert original_wpf.count(needle)==1
    packaged_wpf=out/'WpfPackaged.cs';packaged_wpf.write_text(original_wpf.replace(needle,'ProcessStartInfo(python,"-I -B -u "+Quote'),encoding='utf8')
    cmd+=['/reference:System.Xaml.dll','/reference:System.Web.Extensions.dll',str(packaged_wpf),str(ROOT/'spikes/windows_02/RuntimeHost.cs')]
    built=subprocess.run(cmd,capture_output=True);(out/'csc.log').write_bytes(built.stdout+built.stderr);assert built.returncode==0,(built.stdout+built.stderr).decode('utf8',errors='replace')
    (payload/'ProjectPractice.exe.config').write_text('<?xml version="1.0" encoding="utf-8"?><configuration><startup><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8"/></startup><runtime><AppContextSwitchOverrides value="Switch.System.Windows.DoNotScaleForDpiChanges=false;Switch.System.Windows.DoNotUsePresentationDpiCapabilityTier2OrGreater=false"/></runtime></configuration>\n',encoding='utf8')
    files={p.relative_to(payload).as_posix():sha(p) for p in sorted(payload.rglob('*')) if p.is_file()};assert not any('qt6' in n.lower() or 'pyside' in n.lower() for n in files)
    save(payload/'payload.json',dict(schema='win02-payload-1',files=files,authentication='unsigned corruption detection only'))
    allfiles=sorted(p for p in payload.rglob('*') if p.is_file());uninstall=out/'uninstall-files.nsh'
    lines=[]
    for p in allfiles:
        path='$INSTDIR\\'+p.relative_to(payload).as_posix().replace('/','\\')
        lines+=['SetFileAttributes "'+path+'" NORMAL','Delete "'+path+'"']
    dirs=sorted([p for p in payload.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True)
    lines+=['RMDir "$INSTDIR\\'+p.relative_to(payload).as_posix().replace('/','\\')+'"' for p in dirs];uninstall.write_text('\n'.join(lines)+'\n',encoding='utf8')
    readonly=out/'readonly-files.nsh';readonly.write_text('\n'.join('SetFileAttributes "$INSTDIR\\'+p.relative_to(payload).as_posix().replace('/','\\')+'" READONLY' for p in allfiles)+'\n',encoding='utf8')
    installer=out/'ProjectPractice-WIN02-setup.exe';nsis=tool/'nsis-3.13/makensis.exe'
    nsis_cmd=[str(nsis),'/V4','/INPUTCHARSET','UTF8','/DPAYLOAD='+str(payload),'/DOUTPUT='+str(installer),'/DUNINSTALL_LIST='+str(uninstall),'/DREADONLY_LIST='+str(readonly),str(ROOT/'spikes/windows_02/installer.nsi')]
    built=subprocess.run(nsis_cmd,capture_output=True);(out/'nsis.log').write_bytes(built.stdout+built.stderr);assert built.returncode==0,(built.stdout+built.stderr).decode('utf8',errors='replace')
    inventory=[dict(path=p.relative_to(payload).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in allfiles]
    save(out/'build-receipt.json',dict(schema='win02-build-1',python=dict(version='3.12.10',source='official CPython embeddable x64',archive_sha256=PY_SHA,maintained_runtime_release_gate_open=True),nsis=dict(version='3.13',sha256=NSIS_SHA,compression='zlib'),framework=dict(minimum='4.8',release_minimum=528040,bundled=False,actual_host_release=533509),wheel_inputs=wheels,core_source_sha256={name+'.py':sha(ROOT/'src/financial_assistant'/(name+'.py')) for name in CORE},wpf_packaging_delta=dict(original_sha=sha(ROOT/'spikes/windows_01/WpfSpike.cs'),generated_sha=sha(packaged_wpf),change='Only trusted Python invocation gains -I -B; original stage01 file unchanged.'),csc_command=cmd,nsis_command=nsis_cmd,payload_files=inventory,payload_bytes=sum(p.stat().st_size for p in allfiles),installer_bytes=installer.stat().st_size,installer_sha256=sha(installer),no_qt=True,clean_vm_tested=False,signed=False,bit_identical_rebuild_claimed=False))
    print(json.dumps(dict(installer=str(installer),bytes=installer.stat().st_size,sha256=sha(installer),payload_files=len(allfiles))))
if __name__=='__main__':main()
