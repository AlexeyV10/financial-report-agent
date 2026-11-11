"""Actual private-runtime/package checks. Does not call a model or change old gold."""
from pathlib import Path
import argparse,hashlib,json,os,stat,subprocess,sys,tempfile,time,unittest,uuid
ROOT=Path(__file__).resolve().parents[2]
ORACLE=json.loads((ROOT/'spikes/windows_01/expected.json').read_text())
PAYLOAD=None
def hostile_env():
    e=dict(os.environ);e['PATH']=str(Path(os.environ['WINDIR'])/'System32');e['PYTHONHOME']='C:/WIN02-must-not-be-used';e['PYTHONPATH']='C:/WIN02-must-not-be-used';return e
class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private=PAYLOAD/'runtime/python.exe';cls.worker=PAYLOAD/'app/spikes/windows_01/worker.py';cls.demo=PAYLOAD/'app/assets/demo'
        cls.cwd=Path(tempfile.mkdtemp(prefix='WIN02 independent cwd ')).resolve()
        assert cls.cwd.parent==Path(tempfile.gettempdir()).resolve() and cls.cwd.name.startswith('WIN02 independent cwd ')
    def invoke(self,raw,workspace=None):
        p=subprocess.run([str(self.private),'-I','-B','-u',str(self.worker),'--workspace',str(workspace or self.demo)],input=raw,capture_output=True,cwd=self.cwd,env=hostile_env(),timeout=10)
        return p,[json.loads(x) for x in p.stdout.decode('utf8').splitlines()]
    def request(self,op='calculate',**kw):return dict(protocol='windows01-1',job='package-test',operation=op,zoom=1,rotation=0,dpi=1,**kw)
    def test_private_isolation_and_utf8_diagnostic(self):
        p=subprocess.run([str(self.private),'-I','-B',str(PAYLOAD/'app/spikes/windows_02/runtime_probe.py')],capture_output=True,cwd=self.cwd,env=hostile_env(),timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);d=json.loads(p.stdout.decode('utf8'));self.assertEqual(d['display'],'15.00');self.assertEqual(Path(d['executable']).resolve(),self.private.resolve());self.assertEqual(d['isolated'],1);self.assertEqual(d['no_user_site'],1);self.assertFalse(d['qt_present']);self.assertTrue(all(Path(x).resolve().is_relative_to(PAYLOAD) for x in d['path']));self.assertIn('3.12.10',d['python'])
    def test_actual_registered_calculator_uses_pdf_context(self):
        p,events=self.invoke(json.dumps(self.request()).encode()+b'\n');self.assertEqual(p.returncode,0,p.stderr);f=events[-1]['outcome']['financial_result'];self.assertEqual(f['display_value'],'15.00');self.assertEqual(f['operation_id'],'operating_margin_v1');self.assertTrue(all(x['document_sha256']=='c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451' for x in f['inputs']));self.assertTrue(all(x['provenance']['human_reviewer'] is None for x in f['inputs']))
    def test_bad_ipc_and_arbitrary_paths_never_answer(self):
        bad=self.request(path='C:/not-a-trusted-document')
        for raw in [json.dumps(bad).encode()+b'\n',b'[]\n',b'\xff\n',b'{"job":"x","job":"y"}\n',b'x'*8193]:
            p,events=self.invoke(raw);self.assertNotEqual(p.returncode,0);self.assertFalse(any(e['type']=='done' for e in events))
    def test_actual_worker_crash_and_cancel(self):
        p,events=self.invoke(json.dumps(self.request('crash')).encode()+b'\n');self.assertEqual(p.returncode,23);self.assertFalse(any(e['type']=='done' for e in events))
        p=subprocess.Popen([str(self.private),'-I','-B','-u',str(self.worker),'--workspace',str(self.demo)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=self.cwd,env=hostile_env())
        p.stdin.write(json.dumps(self.request('slow')).encode()+b'\n');p.stdin.flush();self.assertEqual(json.loads(p.stdout.readline())['type'],'progress');p.kill();out,err=p.communicate(timeout=2);self.assertNotIn(b'"type": "done"',out)
    def test_pdf_mutation_does_not_gain_admission(self):
        target=ROOT/'tmp'/('mutated-own-source-'+uuid.uuid4().hex);target.mkdir()
        for name in ['catalog.json','dictionary.json','admission.json','manifest.json','own-demo-v1.pdf']:(target/name).write_bytes((self.demo/name).read_bytes())
        (target/'own-demo-v1.pdf').write_bytes(b'%PDF-broken-own-fixture')
        p,events=self.invoke(json.dumps(self.request()).encode()+b'\n',target);self.assertNotEqual(p.returncode,0);self.assertEqual(events[-1]['type'],'error');self.assertFalse(any(e['type']=='done' for e in events))
    def test_private_render_rotation_zoom_DPI_independent_oracle(self):
        for rotation in [0,90,180,270]:
            for dpi in [1.25,2]:
                q=self.request('render');q.update(rotation=rotation,zoom=2,dpi=dpi);p,events=self.invoke(json.dumps(q).encode()+b'\n');self.assertEqual(p.returncode,0,p.stderr);e=events[-1];self.assertEqual(e['rect'],[x*2*dpi for x in ORACLE['profit_pixel_rect_at_scale1'][str(rotation)]]);self.assertEqual(e['page'],1)
    def test_payload_and_no_package_cache_writes(self):
        manifest=json.loads((PAYLOAD/'payload.json').read_text(encoding='utf8'))
        for rel,expected in manifest['files'].items():self.assertEqual(hashlib.sha256((PAYLOAD/rel).read_bytes()).hexdigest(),expected,rel)
        self.assertFalse(list(PAYLOAD.rglob('__pycache__')));self.assertFalse(any('qt6' in str(x).lower() or 'pyside' in str(x).lower() for x in PAYLOAD.rglob('*')))
    def test_original_calculator_and_admission_files_are_byte_identical(self):
        for p in (PAYLOAD/'app/src/financial_assistant').glob('*.py'):self.assertEqual(p.read_bytes(),(ROOT/'src/financial_assistant'/p.name).read_bytes())
    def rejected_host_manifest(self,files):
        target=ROOT/'tmp'/('rejected-payload-'+uuid.uuid4().hex);target.mkdir()
        for name in ['ProjectPractice.exe','ProjectPractice.exe.config']:(target/name).write_bytes((PAYLOAD/name).read_bytes())
        (target/'payload.json').write_text(json.dumps(dict(schema='win02-payload-1',files=files)),encoding='utf8')
        data=Path(os.environ['LOCALAPPDATA'])/'ProjectPractice/WIN02/runs';before=set(data.glob('*'))
        p=subprocess.run([str(target/'ProjectPractice.exe'),'--diagnose'],cwd=self.cwd,env=hostile_env(),timeout=10);self.assertEqual(p.returncode,2)
        added=set(data.glob('*'))-before;self.assertEqual(len(added),1);run=next(iter(added));self.assertEqual(json.loads((run/'host.json').read_text(encoding='utf8'))['status'],'error');self.assertFalse((run/'runtime.json').exists())
    def test_installed_host_rejects_missing_or_corrupt_asset(self):
        self.rejected_host_manifest({'missing-owned-asset.dat':'0'*64})
    def test_installed_host_rejects_manifest_path_escape(self):
        self.rejected_host_manifest({'../outside-owned-package.dat':'0'*64})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--payload',type=Path,required=True);a,extra=p.parse_known_args();PAYLOAD=a.payload.resolve();unittest.main(argv=[sys.argv[0],*extra],verbosity=2)
