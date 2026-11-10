"""Evaluator negatives on prior actual controls/own isolated files; no model or comparison run."""
from copy import deepcopy as cp
from pathlib import Path
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_protocol_v1.common import read,write_new,digest,file_sha,ProtocolError
from kp3_protocol_v1.suite import validate_suite
from kp3_protocol_v1.controls import prior_controls
from kp3_protocol_v1.evaluator import evaluate_financial,evaluate_scenario,usage
from kp3_protocol_v1.presentation import audit_markdown
from kp3_protocol_v1.metrics import summarize,rate,evaluate_retrieval,retrieval_metrics
from kp3_protocol_v1.freeze import create_freeze,verify_freeze,seal_raw,read_raw,runtime_isolation

class Evaluation14Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=read(ROOT/'data/evaluation/kp3_eval_v1/inputs.json');cls.gold=read(ROOT/'evaluation/fixtures/kp3_eval_v1/gold.json');cls.protocol=read(ROOT/'evaluation/protocols/kp3_eval_v1/protocol.json');cls.retrieval=read(ROOT/'evaluation/fixtures/kp3_eval_v1/retrieval_gold.json');cls.controls=prior_controls(ROOT,cls.inputs,cls.gold)
    def setUp(self):
        self.control=cp(next(x for x in self.controls if x['answer']['method']=='B'and not x['answer']['assumption_checks']));self.case=self.control['case'];self.g=self.control['gold'];self.a=self.control['answer']
    def score(self,a=None):return evaluate_financial(self.case,self.g,a or self.a)
    def reject(self):self.assertFalse(self.score()['matched'])
    def test_all_four_prior_controls(self):
        self.assertEqual(len(self.controls),4)
        for r in self.controls:self.assertTrue(evaluate_financial(r['case'],r['gold'],r['answer'])['matched'])
    def test_denominators_and_known_overlap(self):
        a=validate_suite(self.inputs,self.gold,self.protocol);self.assertEqual(a['suite_cases'],92);self.assertEqual(a['financial_numeric']['comparison_known'],32);self.assertEqual(len(a['historical_dev_overlap_comparison']),40);self.assertEqual(len(a['financial_lineage_clusters']['comparison_known']),2)
    def test_duplicate_case_id(self):
        i=cp(self.inputs);i['cases'][1]['case_id']=i['cases'][0]['case_id'];g=cp(self.gold);g['suite_digest']=digest(i);p=cp(self.protocol);p['suite_digest']=digest(i)
        with self.assertRaises(ProtocolError):validate_suite(i,g,p)
    def test_wrong_gold_number_rejected_before_grading(self):
        g=cp(self.gold);next(x for x in g['cases']if x['result'])['result']['display_value']='999'
        with self.assertRaisesRegex(ProtocolError,'gold_display_mismatch'):validate_suite(self.inputs,g,self.protocol)
    def test_unknown_gold_case_id(self):
        g=cp(self.gold);g['cases'][0]['case_id']='unknown'
        with self.assertRaises(ProtocolError):validate_suite(self.inputs,g,self.protocol)
    def test_family_split_overlap_rejected(self):
        i=cp(self.inputs);i['cases'][20]['family']=i['cases'][0]['family'];g=cp(self.gold);g['suite_digest']=digest(i);p=cp(self.protocol);p['suite_digest']=digest(i)
        with self.assertRaisesRegex(ProtocolError,'family_split_leakage'):validate_suite(i,g,p)
    def test_wrong_exact_numerator(self):self.a['financial_result']['exact_result']['numerator']='999';self.reject()
    def test_wrong_display_unit(self):self.a['financial_result']['result_unit']['scale']=1000;self.reject()
    def test_swapped_role(self):self.a['financial_result']['inputs'][0]['role']='current';self.reject()
    def test_wrong_organization(self):self.a['financial_result']['inputs'][0]['organization_id']='other';self.reject()
    def test_wrong_definition(self):self.a['financial_result']['inputs'][0]['definition_id']='other';self.reject()
    def test_wrong_full_period(self):self.a['financial_result']['inputs'][0]['period']['duration_type']='year_to_date';self.reject()
    def test_other_cell_evidence(self):self.a['financial_result']['sources'][0]['evidence']['evidence_id']='other';self.reject()
    def test_wrong_sha_and_page(self):
        self.a['financial_result']['sources'][0]['document_sha256']='f'*64;self.a['financial_result']['sources'][0]['evidence']['locator']['pdf_page']=1;self.reject()
    def test_lost_header(self):self.a['financial_result']['sources'][0]['evidence']['locator'].pop('unit_header');self.reject()
    def test_unverified_candidate_not_checked(self):self.a['financial_result']['inputs'][0]['provenance']['status']='candidate';self.reject()
    def test_human_upgrade_rejected(self):self.a['financial_result']['inputs'][0]['provenance']['status']='human_reviewed';self.reject()
    def test_extra_narrative_999_is_not_ignored(self):self.a['financial_result']['summary']='Прибыль999';self.reject()
    def test_missing_required_claim_is_failure(self):self.a['financial_result']['inputs']=[];self.assertFalse(self.score()['complete_claims'])
    def test_technical_limit_never_numeric_success(self):self.a['execution_status']='limit';self.reject()
    def test_trace_cannot_skip_search(self):self.a['trace']=[r for r in self.a['trace']if r['stage']!='search'];self.reject()
    def test_question_and_raw_fields_preserved(self):self.a['normalized_input']['raw_fields']['organization']='other';self.reject()
    def test_why_and_asserted_direction_not_lost(self):
        r=cp(next(x for x in self.controls if x['answer']['assumption_checks']));r['answer']['assumption_checks'][0]['status']='supported';self.assertFalse(evaluate_financial(r['case'],r['gold'],r['answer'])['matched'])
    def test_mock_cannot_be_actual_C(self):
        r=cp(next(x for x in self.controls if x['answer']['method']=='C'));r['answer']['agent']['adapter']['kind']='mock';self.assertIn('mock_or_replay_not_actual',evaluate_financial(r['case'],r['gold'],r['answer'])['errors'])
    def test_wrong_model_digest(self):
        r=cp(next(x for x in self.controls if x['answer']['method']=='A'));r['answer']['selection']['adapter']['model_digest']='f'*64;self.assertIn('wrong_model_pin',evaluate_financial(r['case'],r['gold'],r['answer'])['errors'])
    def test_unknown_usage_is_not_zero(self):
        r=cp(next(x for x in self.controls if x['answer']['method']=='A'))['answer'];choice=next(e for e in r['selection']['events']if e['kind']=='choice');choice['chat_requests']=None;r['model_calls']=None;r['selection']['usage'].update(known_chat_requests=0,unknown_requests=1);u=usage(r);self.assertIsNone(u['chat_requests']);self.assertEqual(u['unknown_requests'],1)
    def test_empty_denominator_not_measured(self):self.assertEqual(rate(0,0,0)['status'],'not_measured')
    def test_no_attempts_keeps_planned_denominators(self):
        r=summarize(self.inputs,self.gold,self.protocol,[]);a=r['method_metrics']['A:primary'];self.assertEqual(a['numeric_correct'],dict(x=0,n=32,status='not_measured'));self.assertEqual(a['missing_attempts'],40)
    def row(self,method='B'):
        s=next(x for x in self.protocol['order']if x['case_id']=='cmp-02'and x['method']==method and x['phase']=='primary');a=cp(self.a);c=next(c for c in self.inputs['cases']if c['case_id']=='cmp-02');a['original_question']=c['source']['form']['original_question'];a['normalized_input'].update(original_question=a['original_question'],raw_fields=cp(c['source']['form']['fields']));a['source_input_digest']=digest(dict(source=c['source'],answers=[]));a['financial_result']['request']['original_question']=a['original_question'];a['outcome']['financial_result']=cp(a['financial_result']);return dict(schema_version='kp3-observation-0.1',**s,source='evaluator_control',answer=a,measurement=dict(elapsed_ms=1,cold_warm='unknown'))
    def test_cached_B_cannot_count_as_C(self):
        r=summarize(self.inputs,self.gold,self.protocol,[self.row('C')],True);self.assertFalse(r['method_metrics']['C:primary']['scores'][0]['numeric_correct'])
    def test_duplicate_and_unknown_attempt_ids(self):
        row=self.row()
        with self.assertRaisesRegex(ProtocolError,'duplicate_attempt_id'):summarize(self.inputs,self.gold,self.protocol,[row,row],True)
        row['attempt_id']='unplanned'
        with self.assertRaisesRegex(ProtocolError,'unknown_attempt_id'):summarize(self.inputs,self.gold,self.protocol,[row],True)
    def test_control_not_accepted_as_actual(self):
        with self.assertRaisesRegex(ProtocolError,'nonactual_observation_forbidden'):summarize(self.inputs,self.gold,self.protocol,[self.row()])
    def test_duplicate_service_run_id_across_attempts(self):
        one=self.row();two=cp(one);warm=next(r for r in self.protocol['order']if r['case_id']=='cmp-02'and r['method']=='B'and r['phase']=='warm_repeat');two.update(warm)
        with self.assertRaisesRegex(ProtocolError,'duplicate_service_run_id'):summarize(self.inputs,self.gold,self.protocol,[one,two],True)
    def test_failure_stays_in_numeric_denominator(self):
        row=self.row();row['answer']['execution_status']='error';row['answer']['financial_result']=None;row['answer']['outcome']=None;r=summarize(self.inputs,self.gold,self.protocol,[row],True);self.assertEqual(r['method_metrics']['B:primary']['numeric_correct']['n'],32);self.assertEqual(r['method_metrics']['B:primary']['numeric_correct']['x'],0)
    def test_partial_retrieval_has_all_cells_denominator(self):
        q=cp(next(q for q in self.retrieval['queries']if len(q['required_evidence'])==2));e=q['required_evidence'][0];row=dict(e,source_kind='prepared_evidence',verification_status='assistant_checked',evidence_digest=digest(e));r=evaluate_retrieval(q,dict(status='found',source_kind='prepared',results=[row]));self.assertEqual((r['matched_evidence'],r['required_evidence'],r['complete']),(1,2,False))
    def test_retrieval_wrong_header_or_automatic_not_matched(self):
        q=self.retrieval['queries'][0];e=cp(q['required_evidence'][0]);row=dict(e,source_kind='prepared_evidence',verification_status='assistant_checked',evidence_digest=digest(e));row['locator']=dict(e['locator'],unit_header='USD');r=evaluate_retrieval(q,dict(status='found',source_kind='prepared',results=[row]));self.assertEqual(r['matched_evidence'],0)
        row['locator']=e['locator'];r=evaluate_retrieval(q,dict(status='found',source_kind='automatic',results=[row]));self.assertFalse(r['complete'])
    def test_queries_not_duplicated_by_operations(self):self.assertEqual(len(self.retrieval['queries']),29);self.assertEqual(len(self.retrieval['case_to_query']),32)
    def test_isolation_no_production_gold_imports(self):self.assertEqual(runtime_isolation(ROOT)['new_gold_imports'],0)
    def test_technical_error_not_correct_refusal(self):
        c=next(c for c in self.inputs['cases']if c['case_id']=='cmp-33');g=next(g for g in self.gold['cases']if g['case_id']=='cmp-33');self.a.update(execution_status='error',request_status='error',financial_status=None,financial_result=None,outcome=None,reason_code='adapter_unavailable');r=evaluate_financial(c,g,self.a);self.assertTrue(r['refusal_expected']);self.assertFalse(r['refusal_correct'])
    def test_unknown_or_duplicate_fact_id_not_accepted(self):
        self.a['financial_result']['inputs'][0]['fact_id']='unknown';self.reject();self.a['financial_result']['inputs'].append(cp(self.a['financial_result']['inputs'][0]));self.reject()
    def test_automatic_calculation_receipt_rejected(self):self.a['financial_result']['retrieval_resolution']['kind']='automatic';self.reject()
    def test_completed_answer_cannot_claim_skipped_search(self):next(t for t in self.a['trace']if t['stage']=='search')['status']='skipped';self.reject()
    def scenario_control(self):
        a=cp(next(r['payload']['result']for r in read(ROOT/'evaluation/kp3_13_2026-11-10/ui-runs.json')['records']if r['payload']['kind']=='scenario'and r['payload']['result']['signal']is True));c=next(c for c in self.inputs['cases']if c['case_id']=='scenario-01');g=next(g for g in self.gold['cases']if g['case_id']=='scenario-01');return c,g,a
    def test_prior_own_scenario_reference(self):
        c,g,a=self.scenario_control();self.assertTrue(evaluate_scenario(c,g,a)['matched'])
    def test_forged_final_equity_not_ignored(self):
        c,g,a=self.scenario_control();a['scenario']['final_equity']='99999.00';self.assertFalse(evaluate_scenario(c,g,a)['matched'])
    def test_changed_scenario_parameters_not_ignored(self):
        c,g,a=self.scenario_control();a['request']['parameters']['threshold_pct']='50';self.assertFalse(evaluate_scenario(c,g,a)['matched'])
    def test_real_origin_cannot_be_own_scenario(self):
        c,g,a=self.scenario_control();a['financial']['financial_result']['sources'][0]['data_origin']='real';self.assertFalse(evaluate_scenario(c,g,a)['matched'])

class Freeze14Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.tmp.cleanup);self.r=Path(self.tmp.name)
        for name in ['inputs','gold','protocol']:write_new(self.r/(name+'.json'),{})
        self.files=['inputs.json','gold.json','protocol.json'];self.m=self.r/'manifest.json'
    def freeze(self):return create_freeze(self.r,self.m,self.files,{},'protocol.json','inputs.json','gold.json')
    def test_freeze_verifies_and_cannot_overwrite(self):
        self.freeze();verify_freeze(self.r,self.m)
        with self.assertRaises(ProtocolError):self.freeze()
    def test_changed_frozen_gold_rejected(self):
        self.freeze();(self.r/'gold.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ProtocolError,'frozen_file_changed'):verify_freeze(self.r,self.m)
    def test_circular_or_outside_paths_rejected(self):
        self.files.append('manifest.json')
        with self.assertRaisesRegex(ProtocolError,'circular_manifest'):self.freeze()
        self.files[-1]='../outside'
        with self.assertRaisesRegex(ProtocolError,'unsafe_manifest_path'):self.freeze()
    def test_raw_hash_and_scope_guard(self):
        self.freeze();raw=self.r/'raw';raw.mkdir();write_new(raw/'one.json',dict(source='evaluator_control'));receipt=raw/'receipt.json';seal_raw(raw,self.m,['one.json'],receipt,'evaluator_control')
        with self.assertRaisesRegex(ProtocolError,'control_raw_not_actual'):read_raw(raw,self.m,receipt)
        self.assertEqual(len(read_raw(raw,self.m,receipt,True)),1);(raw/'one.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ProtocolError,'raw_hash_mismatch'):read_raw(raw,self.m,receipt,True)
    def test_duplicate_json_and_size_limit(self):
        p=self.r/'bad.json';p.write_text('{"x":1,"x":2}')
        with self.assertRaisesRegex(ProtocolError,'duplicate_json_key'):read(p)
        with self.assertRaisesRegex(ProtocolError,'missing_or_oversized_file'):read(p,1)

class Presentation14Tests(unittest.TestCase):
    def setUp(self):
        self.text=(ROOT/'evaluation/kp3_14_2026-11-10/control-export13.md').read_text(encoding='utf8');self.record=next(r for r in read(ROOT/'evaluation/kp3_13_2026-11-10/ui-runs.json')['records']if r['record_id']=='e37986f8cbd5a9fd002ac8a683dda2246c2bac99d2f3d189fb029243d75c0872')
    def test_actual_prior_export_grammar(self):self.assertTrue(audit_markdown(self.text,self.record)['matched'])
    def test_extra_999_in_human_text_rejected(self):self.assertFalse(audit_markdown('Прибыль999\n'+self.text,self.record)['matched'])
    def test_lost_limit_and_changed_json_rejected(self):
        self.assertFalse(audit_markdown(self.text.replace('Снимок истории:','Скрытый снимок:'),self.record)['matched']);self.assertFalse(audit_markdown(self.text.replace('67385','67386'),self.record)['matched'])

if __name__=='__main__':unittest.main()
