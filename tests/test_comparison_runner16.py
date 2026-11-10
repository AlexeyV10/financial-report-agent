"""Runner durability/budget/order tests only; no real model or frozen comparison answers."""
from copy import deepcopy
from pathlib import Path
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_run_v1.ledger import atomic_new,run_lock,run_id,validate_order,validate_observation,budget_charge,budget_total,next_slot
from kp3_run_v1.runtime import rows_from,private,recover_saved


def slot(n=1,method='A'):return dict(attempt_id='primary-'+str(n),case_id='cmp-01',method=method,phase='primary')
def observation(method='A',calls=1,unknown=0,tokens=10):
    s=slot(method=method);usage=dict(known_chat_requests=calls,unknown_requests=unknown,input_tokens=20,output_tokens=tokens)if method=='A'else dict(known_chat_requests=calls,unknown_requests=unknown,known_input_tokens=20,known_output_tokens=tokens or 0,unknown_usage=int(tokens is None))
    a=dict(method=method,run_id=run_id('a'*64,s),model_calls=None if unknown else calls)
    if method!='B':a['selection'if method=='A'else'agent']=dict(usage=usage)
    return dict(schema_version='kp3-observation-0.1',**s,source='actual',answer=a,measurement=dict(run_manifest_sha256='a'*64,cold_warm='unknown',elapsed_ms=100))


class Runner16Tests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.t.cleanup);self.d=Path(self.t.name)
    def test_exclusive_atomic_publish(self):
        p=self.d/'raw.json';atomic_new(p,dict(first=True));b=p.read_bytes()
        with self.assertRaises(FileExistsError):atomic_new(p,dict(first=False))
        self.assertEqual(p.read_bytes(),b);self.assertFalse(list(self.d.glob('.pending-*')))
    def test_atomic_does_not_leave_partial_json_on_nan(self):
        with self.assertRaises(ValueError):atomic_new(self.d/'raw.json',dict(value=float('nan')))
        self.assertFalse((self.d/'raw.json').exists());self.assertFalse(list(self.d.glob('.pending-*')))
    def test_lock_released_after_exception(self):
        with self.assertRaisesRegex(ValueError,'own'):
            with run_lock(self.d/'lock'):raise ValueError('own')
        with run_lock(self.d/'lock'):pass
    def test_second_runner_is_excluded(self):
        with run_lock(self.d/'lock'):
            with self.assertRaises(OSError):
                with run_lock(self.d/'lock'):self.fail('concurrent runner admitted')
    def test_duplicate_plan_rejected(self):
        with self.assertRaises(ValueError):validate_order([slot(),slot()])
    def test_unknown_method_not_B_fallback(self):
        with self.assertRaises(ValueError):validate_order([slot(method='replay')])
    def test_unsafe_slot_id_rejected(self):
        s=slot();s['attempt_id']='../gold'
        with self.assertRaises(ValueError):validate_order([s])
    def test_ordered_resume_first_unfinished(self):self.assertEqual(next_slot([slot(),slot(2)],[observation()]),slot(2))
    def test_finished_plan_never_reexecutes(self):self.assertIsNone(next_slot([slot()],[observation()]))
    def test_gap_is_not_silently_reordered(self):
        r=observation();r['attempt_id']='primary-2'
        with self.assertRaisesRegex(ValueError,'noncontiguous'):next_slot([slot(),slot(2)],[r])
    def test_unknown_observation_rejected(self):
        with self.assertRaisesRegex(ValueError,'unknown_attempt'):next_slot([slot(2)],[observation()])
    def test_duplicate_raw_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate_observation'):next_slot([slot()],[observation(),observation()])
    def test_native_identity_matches_manifest(self):validate_observation(observation(),slot(),'a'*64)
    def test_method_swap_rejected(self):
        r=observation();r['answer']['method']='B'
        with self.assertRaisesRegex(ValueError,'answer_identity'):validate_observation(r,slot(),'a'*64)
    def test_run_id_swap_rejected(self):
        r=observation();r['answer']['run_id']='another'
        with self.assertRaisesRegex(ValueError,'answer_identity'):validate_observation(r,slot(),'a'*64)
    def test_manifest_swap_rejected(self):
        with self.assertRaisesRegex(ValueError,'run_manifest'):validate_observation(observation(),slot(),'b'*64)
    def test_mock_control_cannot_be_actual(self):
        r=observation();r['source']='evaluator_control'
        with self.assertRaisesRegex(ValueError,'nonactual'):validate_observation(r,slot(),'a'*64)
    def test_unknown_cold_warm_is_preserved(self):validate_observation(observation(),slot(),'a'*64)
    def test_unobserved_phase_label_is_not_model_state(self):
        r=observation();r['measurement']['cold_warm']='warm_repeat'
        with self.assertRaises(ValueError):validate_observation(r,slot(),'a'*64)
    def test_A_known_requests_and_tokens(self):
        c=budget_charge(observation());self.assertEqual((c['known_chat_requests'],c['reserved_chat_requests'],c['reserved_output_tokens']),(1,1,10))
    def test_C_unknown_sending_reserves_full_cap(self):
        c=budget_charge(observation('C',calls=2,unknown=1));self.assertEqual((c['unknown_requests'],c['reserved_chat_requests'],c['reserved_output_tokens']),(1,8,3072))
    def test_A_unknown_tokens_not_zero_cost(self):
        c=budget_charge(observation(tokens=None));self.assertEqual(c['known_output_tokens'],0);self.assertEqual(c['reserved_output_tokens'],384)
    def test_unknown_calls_never_reported_zero(self):
        r=observation('C',calls=0,unknown=1);r['answer']['model_calls']=0
        with self.assertRaisesRegex(ValueError,'unknown_request_lost'):budget_charge(r)
    def test_A_more_than_one_choice_rejected(self):
        with self.assertRaises(ValueError):budget_charge(observation(calls=2))
    def test_B_cannot_have_model_calls(self):
        with self.assertRaisesRegex(ValueError,'B_has_model_calls'):budget_charge(observation('B',calls=1))
    def test_unknown_interrupted_answer_is_conservative(self):
        r=observation('C');r['answer']=None;r['measurement']['elapsed_ms']=None;c=budget_charge(r);self.assertEqual((c['unknown_requests'],c['reserved_chat_requests'],c['serial_wall_s']),(1,8,180))
    def test_budget_sum_uses_actual_and_unknown_separately(self):
        c=budget_total([observation(),observation('C',calls=1,unknown=1)]);self.assertEqual(c['known_chat_requests'],2);self.assertEqual(c['unknown_requests'],1);self.assertEqual(c['reserved_chat_requests'],9)
    def test_rows_ignore_no_missing_slot(self):
        atomic_new(self.d/'primary-1.json',observation());self.assertEqual(rows_from(self.d,[slot()],'a'*64),[observation()])
    def test_foreign_file_is_not_a_completed_attempt(self):
        atomic_new(self.d/'unknown.json',observation())
        with self.assertRaises(ValueError):rows_from(self.d,[slot()],'a'*64)
    def test_private_paths_only(self):
        for p in [ROOT/'src',ROOT/'tmp',ROOT/'tmp/../../data']:
            with self.assertRaises(ValueError):private(p)
    def test_corrupt_saved_answer_not_a_retry(self):
        p=self.d/'partial.json';p.write_text('{');self.assertIsNone(recover_saved(p,slot(),dict(source={},answers=[]),'rid'));self.assertEqual(p.read_text(),'{')
    def test_no_runtime_evaluator_gold_or_target_imports(self):
        code=(ROOT/'evaluation/kp3_run_v1/runtime.py').read_text(encoding='utf8');self.assertNotIn('read(ROOT/freeze[\'gold_path\'])',code);self.assertNotIn('evaluate_financial',code);self.assertNotIn('fixture(',code)


if __name__=='__main__':unittest.main()
