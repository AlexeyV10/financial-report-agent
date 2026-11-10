"""Substantive real SQLite/service boundary regression, no simulated issuer source."""
from pathlib import Path
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_probes_v1.plan import build_plan
from kp3_probes_v1.campaign import run_probe,private_child,write_new


class Boundary15Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.tmp.cleanup);self.directory=Path(self.tmp.name)
    def probe(self,ident):
        row=next(x for x in build_plan()['rows']if x['probe_id']==ident);return run_probe(row,self.directory/ident)
    def test_actual_fts_empty_does_not_fall_back_to_checked_fact(self):self.probe('search-empty')
    def test_actual_fts_partial_pair_never_calculates(self):self.probe('search-partial')
    def test_valid_hash_wrong_cell_is_rejected(self):self.probe('cell-wrong_cell')
    def test_valid_hash_wrong_value_is_rejected(self):self.probe('cell-wrong_value')
    def test_valid_hash_duplicate_evidence_is_rejected(self):self.probe('cell-duplicate_evidence')
    def test_valid_hash_missing_header_is_rejected(self):self.probe('cell-lost_unit_header')
    def test_candidate_cannot_become_checked_input(self):self.probe('cell-candidate')
    def test_structure_checked_cannot_become_checked_input(self):self.probe('cell-structure_checked')
    def test_own_negative_cfo_sign_is_preserved(self):self.probe('positive-signed_cfo')
    def test_negative_margin_half_up_independent_expected(self):self.probe('positive-negative_profit')
    def test_explicit_decrease_is_contradicted_and_why_unfulfilled(self):self.probe('premise-decrease')
    def test_source_failure_does_not_confirm_premise(self):self.probe('premise-failure')
    def test_clarification_preserves_question_raw_history_why(self):self.probe('premise-preserve_history')
    def test_injected_code_signature_technical_failure(self):self.probe('artifact-code_signature')
    def test_isolated_safe_path_required(self):
        for p in [ROOT/'src',ROOT/'tmp',ROOT/'tmp/../../data']:
            with self.assertRaises(AssertionError):private_child(p)
    def test_reports_never_overwrite_existing_artifact(self):
        p=self.directory/'record.json';write_new(p,dict(first=True));before=p.read_bytes()
        with self.assertRaises(FileExistsError):write_new(p,dict(first=False))
        self.assertEqual(p.read_bytes(),before)
    def test_plan_has_unique_ids_and_all_frozen_registry_families(self):
        p=build_plan();ids=[r['probe_id']for r in p['rows']];self.assertEqual(len(ids),len(set(ids)));registry=json.loads((ROOT/'evaluation/protocols/kp3_eval_v1/protocol.json').read_text(encoding='utf8'))['fault_registry'];self.assertEqual(set(registry),{x for r in p['rows']for x in r['registry_ids']});self.assertEqual(len(ids),sum(p['denominators'].values()))
    def test_plan_never_claims_real_model_or_comparison(self):
        p=build_plan();self.assertEqual(p['final_comparison_attempts'],0);self.assertEqual(p['model_policy']['real_chat_budget'],0);self.assertTrue(all(r['known_to_developer']for r in p['rows']))


if __name__=='__main__':unittest.main()
