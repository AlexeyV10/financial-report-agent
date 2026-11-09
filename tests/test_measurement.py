"""Grader development tests on old open fixtures, not new LLM measurements."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from financial_assistant.measurement import (claim_ok, grade_financial, normalized_claims, ratio, read, sha, summarize)
from financial_assistant.finance import calculate_metric, tool_request
from financial_assistant.user_path import UserQuery, render_financial


class MeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases={c["case_id"]:c for c in read(ROOT/"data/question_sets/kp2_v1/questions.json")["cases"]}
        cls.bundle=read(ROOT/"data/examples/reference_bundle.json")
        # Old open manual calculation used only as a unit-test fixture, not a saved experiment.
        req=tool_request("phosagro-revenue-2023","phosagro-revenue-2024")
        fin=calculate_metric(cls.bundle,req)
        cls.fixture={"variant":"B","availability":"executed","origin_notices":[],
            "input":{"asset_sha256":sha(ROOT/"data/examples/reference_bundle.json"),
                     "reproduction":cls.cases["QA03"]["reproduction"],"document":cls.bundle["document"]},
            "output":{"status":fin["status"],"reason_code":fin["reason_code"],"financial_result":fin,
                      "text":render_financial(UserQuery(),cls.bundle,req,fin)}}

    def setUp(self):
        self.r=deepcopy(self.fixture)

    def grade(self):
        return grade_financial(self.r,self.cases["QA03"])

    def test_valid_open_structured_fixture(self):
        g=self.grade()
        self.assertTrue(g["passed"],g)
        self.assertEqual((g["confirmed"],g["checked"]),(4,4))

    def test_no_production_solver_during_grading(self):
        with patch("financial_assistant.finance.calculate_metric",side_effect=AssertionError("solver")),patch("financial_assistant.contracts.answer",side_effect=AssertionError("solver")):
            self.assertTrue(self.grade()["passed"])

    def test_scalar_without_context(self):
        self.r["output"]["financial_result"]["inputs"][0].pop("entity_id")
        self.assertFalse(self.grade()["passed"])

    def test_wrong_units(self):
        self.r["output"]["financial_result"]["inputs"][0]["scale"]=1000000000
        self.assertFalse(self.grade()["passed"])

    def test_wrong_period(self):
        self.r["output"]["financial_result"]["inputs"][0]["period"]["start"]="2023-04-01"
        self.assertFalse(self.grade()["passed"])

    def test_wrong_version(self):
        self.r["output"]["financial_result"]["answer"]["document_version"]="sha256:"+"0"*64
        self.assertFalse(self.grade()["passed"])

    def test_wrong_evidence_locator(self):
        self.r["output"]["financial_result"]["sources"][0]["column_label"]="2024"
        self.assertFalse(self.grade()["passed"])

    def test_missing_evidence(self):
        self.r["output"]["financial_result"]["sources"].pop()
        self.assertFalse(self.grade()["passed"])

    def test_wrong_formula(self):
        self.r["output"]["financial_result"]["answer"]["calculation"]["formula_id"]="new"
        self.assertFalse(self.grade()["passed"])

    def test_context_not_filled_from_gold(self):
        fin=self.r["output"]["financial_result"]
        fin["inputs"][1].pop("evidence_id")
        self.assertFalse(self.grade()["passed"])
        self.assertNotIn("evidence_id",fin["inputs"][1])

    def test_missing_warning_code(self):
        self.r["output"]["financial_result"]["warnings"].remove("manual_annotation")
        self.assertFalse(self.grade()["passed"])

    def test_missing_warning_in_text(self):
        self.r["output"]["text"]=self.r["output"]["text"].replace("Аудиторское мнение с оговоркой","")
        self.assertFalse(self.grade()["passed"])

    def test_extra_numeric_claim_in_text(self):
        self.r["output"]["text"]+="Ещё доходность 99%.\n"
        self.assertFalse(self.grade()["passed"])

    def test_edited_numeric_text(self):
        self.r["output"]["text"]=self.r["output"]["text"].replace("+15,30%","+15,31%")
        self.assertFalse(self.grade()["passed"])

    def test_empty_denominator(self):
        self.assertEqual(ratio(0,0)["status"],"not_measured")
        self.assertIsNone(ratio(0,0)["fraction"])

    def test_call_limit_is_not_refusal(self):
        raw={"variant":"C/LLM","availability":"executed","output":{"status":"limit_exceeded","reason_code":"call_limit",
             "user_response":{"status":"error","reason_code":"call_limit","financial_result":None}}}
        g=grade_financial(raw,self.cases["QA07"])
        self.assertFalse(g["passed"])
        self.assertIn("no_financial_payload",g["issues"])

    def test_not_run_is_not_success(self):
        self.r["availability"]="not_run"
        self.assertFalse(self.grade()["passed"])

    def test_correct_scalar_wrong_mode(self):
        claim=normalized_claims(self.r["output"]["financial_result"],self.r["input"]["asset_sha256"])[-1]
        claim["analysis_mode"]="historical_as_of"
        target=self.cases["QA03"]["expected"]["outputs"][-1]
        self.assertFalse(claim_ok(claim,target,self.cases["QA03"]["context"]))

    def test_failures_retained_in_numeric_denominator(self):
        rows=[{"case_id":"QA03","variant":"C/LLM","suite":"financial_qa","passed":False,"confirmed":0,"checked":0}]
        m=summarize(rows)["C/LLM"]
        self.assertEqual(m["numeric_accuracy"]["fraction"],"0/1")
        self.assertEqual(m["claim_confirmation"]["status"],"not_measured")

    def test_bool_not_integer_scale(self):
        claim=normalized_claims(self.r["output"]["financial_result"],self.r["input"]["asset_sha256"])[-1]
        claim["scale"]=True
        self.assertFalse(claim_ok(claim,self.cases["QA03"]["expected"]["outputs"][-1],self.cases["QA03"]["context"]))

    def test_valid_historical_refusal_fixture(self):
        req=tool_request("phosagro-revenue-2023","phosagro-revenue-2024",mode="historical_as_of",as_of="2025-02-14T10:00:00+03:00")
        fin=calculate_metric(self.bundle,req)
        self.r["input"]["reproduction"]=self.cases["QA06"]["reproduction"]
        self.r["output"]={"status":fin["status"],"reason_code":fin["reason_code"],"financial_result":fin,
                          "text":render_financial(UserQuery(mode="historical",as_of=req["as_of"]),self.bundle,req,fin)}
        self.assertTrue(grade_financial(self.r,self.cases["QA06"])["passed"])
        self.r["output"]["financial_result"]["reason_code"]="value_missing"
        self.assertFalse(grade_financial(self.r,self.cases["QA06"])["passed"])

    def test_normalizer_has_no_gold_argument(self):
        import inspect
        self.assertEqual(list(inspect.signature(normalized_claims).parameters),["fin","asset_sha"])

    def test_request_counter_excludes_probes_and_omits_content(self):
        from financial_assistant.measurement_collect import MeasuredAdapter
        from financial_assistant import local_model
        import json,tempfile
        class Stub:
            metadata={"kind":"unit_test_stub_not_llm"}
            def decide(self,observation,timeout):
                local_model.local_json("/api/version")
                local_model.local_json("/api/chat",{"messages":["PRIVATE_UNIT_TEST_CONTENT"]})
                return {"action":None,"usage":None}
        with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as tmp:
            path=Path(tmp)/"calls.jsonl"
            with patch.object(local_model,"local_json",return_value={"prompt_eval_count":12,"eval_count":3}):
                MeasuredAdapter(Stub(),str(path)).decide({},1)
            events=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([e["event"] for e in events],["chat_request_started","chat_response_received"])
            self.assertEqual(events[-1]["output_tokens"],3)
            self.assertNotIn("PRIVATE_UNIT_TEST_CONTENT",path.read_text(encoding="utf-8"))

    def test_missing_result_is_not_confirmation(self):
        self.r["output"]["financial_result"]=None
        self.assertEqual(self.grade()["checked"],0)
        self.assertFalse(self.grade()["passed"])


if __name__=="__main__":
    unittest.main()
