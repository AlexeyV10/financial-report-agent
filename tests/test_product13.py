"""Own open dev tests. Counters below measure dedup, not model quality."""
from copy import deepcopy
from pathlib import Path
import json,sys,tempfile,unittest
import hashlib
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from test_service_b import fixture,source
from financial_assistant.product_history import RunStore,VERSION,validate_payload
from financial_assistant.product_service import financial,scenario,live_fingerprint,preflight,restore_registered
from financial_assistant.product_downloads import HistoryDownloads
from financial_assistant.scenario_service import load_own_context

class Product13Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name);self.ctx=fixture(self.dir);self.store=RunStore(self.dir/'history');self.src=source(self.ctx)
    def run_b(self,src=None,nonce=0):return financial(src or self.src,[],'B',self.ctx,self.store,nonce)
    def test_five_operations_keep_semantics(self):
        expected={'direct_fact_v1':'120','absolute_change_v1':'20','relative_change_v1':'20.00','scale_v1':'0.12','operating_margin_v1':'15.00'}
        for op,val in expected.items():
            r,_=self.run_b(source(self.ctx,op));self.assertEqual(r['payload']['result']['financial_result']['display_value'],val)
    def test_double_press_does_not_execute(self):
        first,_=self.run_b()
        with patch('financial_assistant.product_service.execute',side_effect=AssertionError('must not rerun')):
            second,reused=self.run_b()
        self.assertTrue(reused);self.assertEqual(first,second)
    def test_refresh_new_store_deduplicates(self):
        first,_=self.run_b();other=RunStore(self.store.path)
        with patch('financial_assistant.product_service.execute',side_effect=AssertionError('must not rerun')):second,reused=financial(self.src,[],'B',self.ctx,other)
        self.assertTrue(reused);self.assertEqual(first,second)
    def test_explicit_new_run_keeps_old(self):
        a,_=self.run_b();b,_=self.run_b(nonce=1);self.assertNotEqual(a['payload']['result']['run_id'],b['payload']['result']['run_id']);self.assertEqual(len(self.store.listing()),2)
    def test_changed_operation_separates_runs(self):
        a,_=self.run_b();b,_=self.run_b(source(self.ctx,'relative_change_v1'));self.assertNotEqual(a['record_id'],b['record_id'])
    def test_changed_unit_separates_runs(self):
        src=source(self.ctx,'scale_v1');a,_=self.run_b(src);src['form']['fields']['result_unit']['scale']=1000000;b,_=self.run_b(src);self.assertNotEqual(a['record_id'],b['record_id'])
    def test_missing_pdf_cannot_revive_answer(self):
        a,_=self.run_b();did=a['payload']['result']['financial_result']['inputs'][0]['document_id'];d=next(d for d in self.ctx.calculation.catalog['documents']if d['document_id']==did);p=Path(self.ctx.calculation.resources[d['availability']['local_resource_id']]);p.unlink();b,reused=self.run_b();self.assertFalse(reused);self.assertIsNone(b['payload']['result']['financial_result']);self.assertNotEqual(a['record_id'],b['record_id'])
    def test_changed_index_cannot_revive_answer(self):
        a,_=self.run_b();self.ctx.retrieval['db_path'].write_bytes(b'changed');b,reused=self.run_b();self.assertFalse(reused);self.assertEqual(b['payload']['result']['execution_status'],'error')
    def test_preflight_is_not_a_search(self):
        p=preflight(self.ctx);self.assertTrue(p['ready']);self.assertFalse(p['retrieval_performed']);self.assertEqual(p['model_calls'],0)
    def test_preflight_changed_index(self):
        self.ctx.retrieval['db_path'].write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'index_hash_mismatch'):preflight(self.ctx)
    def test_history_reopen_never_calls_controller(self):
        a,_=self.run_b()
        with patch('financial_assistant.product_service.execute',side_effect=AssertionError):b=self.store.load(a['record_id'])
        self.assertEqual(a,b)
    def test_json_roundtrip_own_minimal_sources(self):
        a,_=self.run_b();b=json.loads(self.store.export(a['record_id'],'json'));self.assertEqual(a,b);self.assertEqual(b['schema_version'],VERSION);self.assertNotIn('pdf_bytes',str(b))
    def test_markdown_injection_is_inert(self):
        s=deepcopy(self.src);s['form']['original_question']='```\n<script>alert(1)</script> [click](https://evil.invalid)';a,_=self.run_b(s);md=self.store.export(a['record_id'],'markdown').decode();self.assertNotIn('<script>',md);self.assertNotIn('[click](https',md.split('```json')[0]);self.assertEqual(md.count('```'),2);self.assertIn('\\u0060',md);self.assertEqual(json.loads(md.split('```json')[1].rsplit('```',1)[0]),a['payload'])
    def test_hash_damage_rejected(self):
        a,_=self.run_b();p=self.store.path/(a['record_id']+'.json');data=json.loads(p.read_text());data['payload']['result']['reason_code']='forged';p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'history_hash_mismatch'):self.store.load(a['record_id'])
    def test_duplicate_json_keys_rejected(self):
        k='a'*64;(self.store.path/(k+'.json')).write_text('{"schema_version":1,"schema_version":2}')
        with self.assertRaisesRegex(ValueError,'duplicate_json_key'):self.store.load(k)
    def test_safe_ids(self):
        for key in ['../source','http://a','a'*63,'A'*64]:
            with self.assertRaises(ValueError):self.store.load(key)
    def test_private_path_only(self):
        with self.assertRaises(ValueError):RunStore(ROOT/'data')
    def test_payload_allowlist_and_kind(self):
        a,_=self.run_b();p=deepcopy(a['payload']);p['expected']=999
        with self.assertRaises(ValueError):validate_payload(p)
        p=deepcopy(a['payload']);p['kind']='scenario'
        with self.assertRaises(ValueError):validate_payload(p)
    def test_pending_claim_never_retries(self):
        key=self.store.key({},'context');(self.store.path/(key+'.claim')).write_text('{}')
        with self.assertRaisesRegex(ValueError,'run_in_progress_or_interrupted'):self.store.run({},'context',lambda _:self.fail('producer called'))
    def test_failed_producer_requires_explicit_new_attempt(self):
        def fail(_):raise ValueError('interrupted')
        with self.assertRaisesRegex(ValueError,'interrupted'):self.store.run({},'context',fail)
        with self.assertRaisesRegex(ValueError,'run_in_progress_or_interrupted'):self.store.run({},'context',lambda _:self.fail())
    def test_atomic_write_cannot_overwrite(self):
        p=self.store.path/('b'*64+'.json');p.write_bytes(b'original')
        with self.assertRaises(FileExistsError):self.store._atomic(p,{})
        self.assertEqual(p.read_bytes(),b'original');self.assertFalse(list(self.store.path.glob('*.tmp')))
    def test_technical_error_has_no_number_and_is_saved(self):
        self.ctx.retrieval['db_path'].unlink();a,_=self.run_b();r=a['payload']['result'];self.assertEqual(r['execution_status'],'error');self.assertIsNone(r['financial_result']);self.assertEqual(self.store.load(a['record_id']),a)
    def test_clarification_is_saved_without_calculation(self):
        src=dict(kind='text',input_id='p13',question='Какая выручка за 2024 год?');a,_=self.run_b(src);r=a['payload']['result'];self.assertEqual(r['execution_status'],'awaiting_clarification');self.assertIsNone(r['financial_result']);self.assertEqual(r['original_question'],src['question'])
    def test_scenario_history_and_dedup(self):
        ctx=load_own_context(self.dir/'scenario');req=json.loads((ROOT/'data/scenarios/kp3_scenario_v1/request_example.json').read_text());src=dict(request=req,financial=None);a,reused=scenario(src,ctx,self.store);self.assertFalse(reused);self.assertEqual(a['payload']['result']['scenario']['final_equity'],'10098.00');b,reused=scenario(src,ctx,self.store);self.assertTrue(reused);self.assertEqual(a,b)
    def test_synthetic_label_exported(self):
        ctx=load_own_context(self.dir/'scenario');req=json.loads((ROOT/'data/scenarios/kp3_scenario_v1/request_example.json').read_text());a,_=scenario(dict(request=req,financial=None),ctx,self.store);md=self.store.export(a['record_id'],'markdown').decode();self.assertIn('ИСКУССТВЕННЫЕ ДАННЫЕ',md)
    def test_method_never_silently_falls_back(self):
        with self.assertRaisesRegex(ValueError,'product_method_unsupported'):financial(self.src,[],'replay',self.ctx,self.store)
    def test_bad_export_type_rejected(self):
        a,_=self.run_b()
        with self.assertRaises(ValueError):self.store.export(a['record_id'],'pdf')
    def test_nonce_is_explicit_integer(self):
        for nonce in [True,-1,1.0,'1']:
            with self.assertRaises(ValueError):self.store.key({},'ctx',nonce)
    def test_attachment_bytes_and_revoke(self):
        a,_=self.run_b();server=HistoryDownloads(self.store).start();self.addCleanup(server.close)
        for kind,export in [('json','json'),('md','markdown')]:
            with urlopen(server.url(a['record_id'],kind),timeout=3)as response:
                self.assertEqual(response.read(),self.store.export(a['record_id'],export));self.assertIn('attachment',response.headers['Content-Disposition'])
        url=server.url(a['record_id'],'json');server.revoke()
        with self.assertRaises(HTTPError):urlopen(url,timeout=3)
    def test_attachment_path_injection_rejected(self):
        server=HistoryDownloads(self.store).start();self.addCleanup(server.close)
        for path in ['/export/../source.pdf','/export/a.json?path=README.md','/source/README.md']:
            with self.assertRaises(HTTPError):urlopen('http://127.0.0.1:'+str(server.server.server_port)+path,timeout=3)
    def test_two_stores_do_not_collide_financial_run_ids(self):
        a,_=self.run_b();b,_=financial(self.src,[],'B',self.ctx,RunStore(self.dir/'second'))
        self.assertNotEqual(a['payload']['result']['run_id'],b['payload']['result']['run_id']);self.assertEqual(b['payload']['result']['financial_status'],'answered')
    def test_restore_exact_already_present_without_copy(self):
        d=self.ctx.calculation.catalog['documents'][0];p=Path(self.ctx.calculation.resources[d['availability']['local_resource_id']]);data=p.read_bytes();self.assertEqual(restore_registered(self.ctx,d['document_id'],data),'already_present');self.assertEqual(p.read_bytes(),data)
    def test_restore_missing_exact_version(self):
        d=self.ctx.calculation.catalog['documents'][0];p=Path(self.ctx.calculation.resources[d['availability']['local_resource_id']]);data=p.read_bytes();p.unlink();self.assertEqual(restore_registered(self.ctx,d['document_id'],data),'restored_exact_version');self.assertEqual(p.read_bytes(),data)
    def test_restore_changed_or_unknown_never_overwrites(self):
        d=self.ctx.calculation.catalog['documents'][0];p=Path(self.ctx.calculation.resources[d['availability']['local_resource_id']]);data=p.read_bytes();p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'existing_source_conflict'):restore_registered(self.ctx,d['document_id'],data)
        self.assertEqual(p.read_bytes(),b'changed')
        with self.assertRaisesRegex(ValueError,'source_version_mismatch'):restore_registered(self.ctx,d['document_id'],b'%PDF-evil')
        with self.assertRaisesRegex(ValueError,'unknown_document_id'):restore_registered(self.ctx,'unknown',data)
    def test_mutated_catalog_does_not_revive_history(self):
        a,_=self.run_b();self.ctx.calculation.catalog['facts'][0]['value']='999';b,reused=self.run_b();self.assertFalse(reused);self.assertNotEqual(a['record_id'],b['record_id']);self.assertEqual(b['payload']['result']['execution_status'],'error');self.assertIsNone(b['payload']['result']['financial_result'])
    def test_changed_guarded_file_does_not_revive_history(self):
        p=self.dir/'own-guard.json';p.write_bytes(b'own guard');self.ctx.calculation.file_guards[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();self.ctx.identity=self.ctx.current_identity();a,_=self.run_b();p.write_bytes(b'changed');b,reused=self.run_b();self.assertFalse(reused);self.assertIsNone(b['payload']['result']['financial_result']);self.assertNotEqual(a['record_id'],b['record_id'])
    def test_changed_service_setup_does_not_revive_history(self):
        p=self.dir/'own-service-setup.json';p.write_bytes(b'own setup');self.ctx.config_guard=(str(p),hashlib.sha256(p.read_bytes()).hexdigest());self.ctx.identity=self.ctx.current_identity();a,_=self.run_b();p.unlink();b,reused=self.run_b();self.assertFalse(reused);self.assertIsNone(b['payload']['result']['financial_result'])

if __name__=='__main__':unittest.main()
