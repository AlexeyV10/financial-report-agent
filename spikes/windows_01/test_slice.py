"""Own known-dev checks, independent oracle; no model, issuer corpus or frozen gold."""
from pathlib import Path
from copy import deepcopy
import base64,hashlib,io,json,os,subprocess,sys,tempfile,time,unittest
sys.path.insert(0,str(Path(__file__).parent))
from common import request,validate,decode,CurrentJob,pixel_rect,MAX_REQUEST
from adapter import DemoAdapter
from renderer import PdfiumRenderer
ROOT=Path(__file__).resolve().parents[2];DEMO=ROOT/'tmp/demo'
EXPECTED=json.loads((Path(__file__).parent/'expected.json').read_text(encoding='utf8'))
class SliceTests(unittest.TestCase):
    def test_registered07_exact_independent_expected(self):
        r=DemoAdapter(DEMO).run('test');f=r['financial_result'];self.assertEqual(f['operation_id'],EXPECTED['operation']);self.assertEqual(f['display_value'],EXPECTED['display']);self.assertEqual(f['exact_result'],EXPECTED['exact_percent']);self.assertEqual(len(f['sources']),2);self.assertTrue(all(x['data_origin']=='synthetic' for x in f['sources']));self.assertTrue(all(x['provenance']['human_reviewer'] is None for x in f['inputs']))
    def test_rejects_changed_pdf_without_rehash_admission(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as td:
            dest=Path(td)
            for p in DEMO.glob('*'):
                if p.suffix in {'.json','.pdf'}:(dest/p.name).write_bytes(p.read_bytes())
            a=DemoAdapter(dest);(dest/'own-demo-v1.pdf').write_bytes(b'%PDF-broken')
            with self.assertRaisesRegex(Exception,'source_changed'):a.run('bad')
    def test_context_and_manifest_mutation_are_rejected(self):
        a=DemoAdapter(DEMO);a.ctx.catalog['facts'][0]['value']='999'
        with self.assertRaises(Exception):a.run('bad')
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as td:
            dest=Path(td)
            for p in DEMO.glob('*.json'):(dest/p.name).write_bytes(p.read_bytes())
            (dest/'own-demo-v1.pdf').write_bytes((DEMO/'own-demo-v1.pdf').read_bytes());a=DemoAdapter(dest)
            (dest/'manifest.json').write_text('{}',encoding='utf8')
            with self.assertRaisesRegex(Exception,'manifest_changed'):a.run('bad')
    def test_pdf_cell_and_headers_independent_oracle(self):
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(str(DEMO/'own-demo-v1.pdf')) as doc:
            p=doc[0];t=p.get_textpage();self.assertEqual(list(p.get_size()),EXPECTED['page_size']);self.assertEqual(t.get_text_bounded(300,150,340,174).strip(),EXPECTED['raw_operating_profit']);self.assertEqual(t.get_text_bounded(300,174,340,198).strip(),EXPECTED['raw_revenue']);t.close();p.close()
    def test_rotation_zoom_dpi_and_actual_green_pixels(self):
        from PIL import Image
        a=DemoAdapter(DEMO)
        for rotation in [0,90,180,270]:
            for zoom in [1,1.25,1.5,2]:
                for dpi in [1,1.25,1.5,2]:
                    with self.subTest(rotation=rotation,zoom=zoom,dpi=dpi):
                        event=PdfiumRenderer().render(a,zoom,rotation,dpi);scale=zoom*dpi
                        target=[x*scale for x in EXPECTED['profit_pixel_rect_at_scale1'][str(rotation)]];self.assertEqual(event['rect'],target)
                        img=Image.open(io.BytesIO(base64.b64decode(event['png'])));self.assertEqual(img.getpixel((round(target[0]),round(target[1]))),(0,140,65));self.assertLessEqual(img.width*img.height,2_419_200)
    def test_closed_schema_no_paths_code_urls_or_unknown_ops(self):
        for key,value in [('path','C:/x'),('url','https://example.com'),('code','__import__("os")'),('sql','SELECT 1')]:
            q=request('x','calculate');q[key]=value
            with self.assertRaises(ValueError):validate(q)
        for key,value in [('operation','eval'),('rotation',91),('zoom',float('nan')),('dpi',99),('job','../x')]:
            q=request('x','calculate');q[key]=value
            with self.assertRaises(ValueError):validate(q)
    def test_wire_duplicate_nonfinite_utf8_and_bounds(self):
        for raw in [b'{"a":1,"a":2}',b'{"a":NaN}',b'\xff',b' '* (MAX_REQUEST+1)]:
            with self.assertRaises((ValueError,UnicodeError)):decode(raw,MAX_REQUEST)
    def test_stale_cancel_and_duplicate_terminal(self):
        g=CurrentJob();g.start('old');g.cancel();self.assertFalse(g.accept(dict(protocol='windows01-1',job='old',type='done')));g.start('new');self.assertFalse(g.accept(dict(protocol='windows01-1',job='old',type='done')));e=dict(protocol='windows01-1',job='new',type='done');self.assertTrue(g.accept(e));self.assertFalse(g.accept(e))
    def worker(self,q):
        p=subprocess.run([sys.executable,'-u',str(Path(__file__).parent/'worker.py'),'--workspace',str(DEMO)],input=json.dumps(q).encode()+b'\n',capture_output=True,timeout=10)
        return p,[decode(x) for x in p.stdout.splitlines()]
    def test_real_ipc_utf8_and_calculator(self):
        p,events=self.worker(request('actual','calculate'));self.assertEqual(p.returncode,0);self.assertIn('Проверка',events[0]['text']);self.assertEqual(events[-1]['outcome']['financial_result']['display_value'],'15.00')
    def test_actual_crash_has_no_success(self):
        p,events=self.worker(request('crash','crash'));self.assertEqual(p.returncode,23);self.assertFalse(any(e['type']=='done' for e in events))
    def test_actual_cancel_terminates_before_done(self):
        p=subprocess.Popen([sys.executable,'-u',str(Path(__file__).parent/'worker.py'),'--workspace',str(DEMO)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        p.stdin.write(json.dumps(request('cancel','slow')).encode()+b'\n');p.stdin.flush();first=p.stdout.readline();self.assertEqual(decode(first)['type'],'progress');start=time.perf_counter();p.kill();out,err=p.communicate(timeout=2);self.assertLess(time.perf_counter()-start,2);self.assertNotIn(b'"type": "done"',out)
    def test_actual_ipc_rejects_path(self):
        q=request('bad','calculate');q['path']='C:/arbitrary';p,events=self.worker(q);self.assertNotEqual(p.returncode,0);self.assertFalse(any(e['type']=='done' for e in events))
if __name__=='__main__':unittest.main(verbosity=2)
