"""Reference/schema/integrity checks; no question-set answering/model runs."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from financial_assistant.question_set import QuestionSetError, encoded, fixed, read_json, validate_claim_context, validate_dataset, validate_frozen


class QuestionSetTests(unittest.TestCase):
    def setUp(self):
        self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json")

    def case(self,cid):
        return next(c for c in self.d["cases"] if c["case_id"]==cid)

    def reject(self):
        with self.assertRaises(QuestionSetError):validate_dataset(self.d,ROOT)

    def claim(self):
        c=self.case("QA03");out=next(o for o in c["expected"]["outputs"] if o["measure"]=="growth_pct")
        keys="measure value currency scale periods evidence_ids".split()
        result={k:deepcopy(out[k]) for k in keys}
        result.update({k:c["context"][k] for k in ("entity_id","consolidation","accounting_standard","document_version","asset_sha256","analysis_mode","as_of")})
        return result,c

    def test_valid_coverage_and_separate_groups_not_quality_metrics(self):
        s=validate_dataset(self.d,ROOT)
        self.assertEqual(s["total"],13)
        self.assertEqual(s["by_suite"],{"financial_qa":10,"interface":1,"scenario":2})
        self.assertEqual(s["by_split"],{"dev_open":9,"evaluation_reserved":4})
        self.assertEqual(s["by_origin"],{"real":9,"self_created_synthetic":4})
        self.assertEqual(s["by_route"]["user_query"],4)
        self.assertEqual(s["prototype_answers_run"],0);self.assertEqual(s["model_calls"],0)

    def test_valid_frozen_manifest_pins_data_and_unchanged_prototype(self):
        d,s,m=validate_frozen(ROOT)
        self.assertEqual(s["total"],13)
        self.assertEqual(m["reserved_ids"],["QA04","QA05","QA08","SC02"])
        self.assertEqual(d,self.d)

    def test_reference_validation_does_not_run_answering_components(self):
        with patch("financial_assistant.finance.calculate_metric",side_effect=AssertionError("No production oracle")),patch("financial_assistant.simulation.simulate",side_effect=AssertionError("Reserved scenario not run")),patch("financial_assistant.agent.run_agent",side_effect=AssertionError("No agent")),patch("financial_assistant.local_model.local_json",side_effect=AssertionError("No local model HTTP")):
            self.assertEqual(validate_dataset(self.d,ROOT)["total"],13)

    def test_independent_fraction_reference_and_cost_rounding(self):
        self.assertEqual(fixed(Fraction(1684625,110076),2),"15.30")
        self.assertEqual(self.case("QA04")["expected"]["outputs"][0]["value"],"507.689")
        self.assertEqual(fixed(Fraction(147,200),2),"0.74")
        self.assertEqual(self.case("SC02")["expected"]["outputs"][0]["value"],"10073.50")

    def test_duplicate_id_rejected(self):
        self.d["cases"][1]["case_id"]="QA01";self.reject()

    def test_rephrased_duplicate_task_not_extra_example(self):
        c=deepcopy(self.d["cases"][0]);c["case_id"]="QA99";c["question"]+=" Покажи ответ."
        self.d["cases"].append(c);self.reject()

    def test_duplicate_question_wording_rejected(self):
        self.d["cases"][1]["question"]=self.d["cases"][0]["question"];self.reject()

    def test_missing_category_or_known_failure_case_rejected(self):
        self.d["cases"]=[c for c in self.d["cases"] if c["case_id"]!="QA07"];self.reject()

    def test_synthetic_conflict_not_attributed_to_issuer(self):
        self.case("QA10")["origin"]="real";self.reject()

    def test_unsafe_asset_path_and_pdf_copy_rejected(self):
        for p in ("../../secrets.json","tmp/pdfs/phosagro-2024-ru.pdf","data/question_sets/kp2_v1/assets/../../../../.env"):
            self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.d["assets"][0]["path"]=p;self.reject()

    def test_source_hash_change_rejected(self):
        self.d["assets"][0]["sha256"]="0"*64;self.reject()

    def test_unknown_asset_lineage_rejected(self):
        self.d["assets"][0]["parent_asset_id"]="scenario_costs";self.reject()

    def test_wrong_numeric_answer_or_type_rejected(self):
        for value in ("507689","440.304",440304,True,"NaN"):
            self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA01")["expected"]["outputs"][0]["value"]=value;self.reject()

    def test_correct_number_wrong_scale_or_currency_rejected(self):
        self.case("QA04")["expected"]["outputs"][0]["scale"]=1000000;self.reject()
        self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA01")["expected"]["outputs"][0]["currency"]="USD";self.reject()

    def test_full_period_company_and_version_required(self):
        for key,value in (("entity_id","another_group"),("document_version","earlier_version"),("periods",[])):
            self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA03")["context"][key]=value;self.reject()

    def test_row_column_page_and_both_evidence_required(self):
        self.case("QA03")["locators"][0].pop("row_label");self.reject()
        self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA03")["expected"]["required_evidence_ids"].pop();self.reject()

    def test_refusal_must_not_smuggle_numeric_answer(self):
        self.case("QA06")["expected"]["outputs"]=deepcopy(self.case("QA03")["expected"]["outputs"]);self.reject()

    def test_unknown_publication_not_changed_to_snapshot(self):
        self.case("QA06")["context"]["analysis_mode"]="document_snapshot";self.reject()

    def test_initial_2023_not_substituted_with_comparative_column(self):
        self.case("QA05")["context"]["requested_version"]="selected_version";self.reject()

    def test_absence_is_inventory_gap_not_absence_in_issuer_report(self):
        self.case("QA05")["expected"]["absence_scope"]="entire_issuer_report";self.reject()

    def test_agent_call_limit_is_not_gold_financial_missing(self):
        self.case("QA07")["expected"].update(layer="agent",status="limit_exceeded",reason_code="call_limit");self.reject()

    def test_interface_clarification_not_financial_unsupported(self):
        self.case("UI01")["expected"].update(layer="financial",status="unsupported");self.reject()

    def test_direct_fact_not_claimed_as_existing_free_text_qa(self):
        self.case("QA01")["capability"]["B"]="supported_template";self.reject()

    def test_lossy_default_growth_projection_and_unvalidated_arguments_rejected(self):
        self.case("QA07")["reproduction"]["top_k"]=5;self.reject()
        self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA03")["reproduction"]["code"]="shell";self.reject()

    def test_prior_development_case_cannot_be_reserved(self):
        self.case("QA03")["split"]="evaluation_reserved";self.reject()

    def test_fake_blindness_or_model_execution_claim_rejected(self):
        self.case("QA04")["history"]["underlying_data_used_in_development"]=False;self.reject()
        self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA04")["history"]["model_executed_after_freeze"]=True;self.reject()

    def test_human_review_and_missing_methods_rejected(self):
        self.case("QA01")["verification"]["human_reviewed"]=True;self.reject()
        self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA01")["verification"]["methods"]=[];self.reject()

    def test_known_failure_and_limitations_cannot_be_hidden(self):
        self.case("QA07")["history"]["known_observation"]=None;self.reject()
        self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA03")["expected"]["mandatory_warnings"]=[];self.reject()

    def test_correct_scalar_alone_is_not_a_complete_claim(self):
        with self.assertRaises(QuestionSetError):validate_claim_context({"value":"15.30"},self.case("QA03"),"growth_pct")

    def test_complete_normalized_claim_requires_exact_context(self):
        claim,c=self.claim();validate_claim_context(claim,c,"growth_pct")
        for key,value in (("entity_id","other"),("scale",1000),("currency","RUB"),("periods",[]),("evidence_ids",[]),("analysis_mode","historical_as_of"),("as_of","2025-02-14T10:00:00+03:00")):
            modified=deepcopy(claim);modified[key]=value
            with self.assertRaises(QuestionSetError):validate_claim_context(modified,c,"growth_pct")

    def test_numeric_claim_cannot_be_used_for_refusal(self):
        claim,_=self.claim()
        with self.assertRaises(QuestionSetError):validate_claim_context(claim,self.case("QA06"),"growth_pct")

    def test_manifest_cannot_omit_files_or_change_reserved_membership(self):
        m=read_json(ROOT/"data/question_sets/kp2_v1/manifest.json")
        m["files"].pop("data/examples/reference_bundle.json")
        with self.assertRaises(QuestionSetError):validate_frozen(ROOT,m)
        m=read_json(ROOT/"data/question_sets/kp2_v1/manifest.json");m["reserved_ids"].remove("QA04")
        with self.assertRaises(QuestionSetError):validate_frozen(ROOT,m)

    def test_unknown_schema_and_extra_fields_rejected(self):
        self.d["question_set_schema_version"]="9";self.reject()
        self.d=read_json(ROOT/"data/question_sets/kp2_v1/questions.json");self.case("QA03")["expected"]["skip_verification"]=True;self.reject()


if __name__=="__main__":
    unittest.main()
