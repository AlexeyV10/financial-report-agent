"""Author references without invoking an answering model or production calculator."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/question_sets/kp2_v1"


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    if DEST.exists():
        raise SystemExit("Question set exists. Preserve frozen files; create a new version for changes.")
    DEST.mkdir(parents=True)
    real, scenario = read("data/examples/reference_bundle.json"), read("data/synthetic/scenario_v1.json")
    assets = []
    def asset(aid, path, kind, parent=None, source=None):
        assets.append({"asset_id": aid, "path": path, "kind": kind, "sha256": sha(path), "parent_asset_id": parent, "source_asset_id": source})
    asset("real", "data/examples/reference_bundle.json", "real_bundle")
    asset("scenario_base", "data/synthetic/scenario_v1.json", "synthetic_scenario")
    synthetic = {}
    for kind in ("missing", "conflict"):
        b = deepcopy(scenario["financial_bundle"])
        prefix = "synthetic-qa-" + kind
        doc = b["document"]
        doc.update(document_id=prefix + "-v1", entity_id=prefix + "-group", entity_name="Вымышленная группа «" + kind + "»", fetched_at=datetime.now(timezone.utc).isoformat())
        doc["document_url"] = doc["source_page_url"] = "https://example.invalid/qa/" + kind + "-v1"
        doc["publication"]["source_url"] = doc["related_release"]["url"] = doc["document_url"]
        b["request"].update(entity_id=doc["entity_id"], request_id=prefix + "-request", question="Проверка собственного искусственного реестра")
        for i, year in enumerate((2023, 2024)):
            f, e = b["facts"][i], b["evidence"][i]
            f.update(fact_id=f"{prefix}-{year}", evidence_id=f"{prefix}-e{year}", entity_id=doc["entity_id"])
            e.update(evidence_id=f["evidence_id"], document_id=doc["document_id"])
        if kind == "missing":
            b["facts"][0]["value"] = b["evidence"][0]["raw_value"] = None
        else:
            b["facts"][0]["currency"] = b["evidence"][0]["currency"] = "USD"
        text = "SELF-CREATED SYNTHETIC QA TABLE; NO ISSUER/PDF\n" + "\n".join(f"{e['column_label']}|revenue|{e['raw_value']}|{e['currency']}|{e['scale']}" for e in b["evidence"]) + "\n"
        doc.update(sha256=hashlib.sha256(text.encode()).hexdigest(), byte_length=len(text.encode()))
        doc["version_id"] = "sha256:" + doc["sha256"]
        for obj in [doc] + b["facts"] + b["evidence"]:
            obj["review"] = {"status": "assistant_checked", "method": "Self-created synthetic QA fixture; technical/semantic reference check, not a real PDF or human review.", "human_reviewer": None}
        for f in b["facts"]: f["version_id"] = doc["version_id"]
        for e in b["evidence"]: e.update(version_id=doc["version_id"], document_sha256=doc["sha256"])
        folder = "data/question_sets/kp2_v1/assets/"
        txt, path = folder + kind + "-source.txt", folder + kind + "-bundle.json"
        (ROOT / txt).parent.mkdir(parents=True, exist_ok=True); (ROOT / txt).write_bytes(text.encode("utf-8"))
        write(ROOT / path, b)
        asset(kind + "_text", txt, "synthetic_text")
        asset(kind, path, "synthetic_bundle", "scenario_base", kind + "_text")
        synthetic[kind] = b
    costs = deepcopy(scenario)
    costs["portfolio"].update(fee_fixed="3", slippage_bps="50", max_notional_fraction="0.205")
    costs["provenance"]["note"] += " Reserved question-set cost variant: fee3, slippage50bps, allocation0.205; not run on the prototype at step11. Base data already used in development."
    path = "data/question_sets/kp2_v1/assets/reserved-costs-scenario.json"
    write(ROOT / path, costs); asset("scenario_costs", path, "synthetic_scenario", "scenario_base")
    catalog = {a["asset_id"]: a for a in assets}
    cases = []
    def case(cid, question, task, category, aid="real", suite="financial_qa", reserved=False, indexes=(0, 1), unit=None, historical=False, version_policy="selected_version", premise=None):
        obj = real if aid == "real" else synthetic.get(aid, costs if aid == "scenario_costs" else scenario)
        b = obj["financial_bundle"] if suite == "scenario" else obj
        doc = b["document"]
        fs = [b["facts"][i] for i in indexes]
        periods = [deepcopy(f["period"]) for f in fs]
        if suite == "scenario": periods = [{"kind": "scenario_window", **obj["window"]}]
        ctx = {"entity_id": doc["entity_id"], "entity_name": doc["entity_name"], "consolidation": doc["consolidation"], "accounting_standard": doc["accounting_standard"],
               "document_id": doc["document_id"], "document_version": doc["version_id"], "document_sha256": doc["sha256"], "document_url": doc["document_url"],
               "asset_sha256": catalog[aid]["sha256"], "metric_id": "portfolio_final_value" if suite == "scenario" else "revenue", "periods": periods,
               "input_units": [{"fact_id": f["fact_id"], "currency": f["currency"], "scale": f["scale"]} for f in fs],
               "analysis_mode": "historical_as_of" if historical or suite == "scenario" else "document_snapshot",
               "as_of": obj["decision_at"] if suite == "scenario" else "2025-02-14T10:00:00+03:00" if historical else None,
               "source": "synthetic_fixture" if aid != "real" else "local_search" if task in {"annual_growth", "historical_growth", "top1_growth"} else "prepared_registry",
               "requested_version": version_policy, "output_unit": unit}
        refs = [f["evidence_id"] for f in fs]
        locators = [{k: deepcopy(e[k]) for k in ("evidence_id", "document_id", "version_id", "document_sha256", "pdf_page", "printed_page", "statement_page", "page_region", "row_label", "column_label", "period", "currency", "scale")}
                    for e in b["evidence"] if e["evidence_id"] in refs]
        c = {"case_id": cid, "question": question, "suite": suite, "category": category, "tags": [task],
             "task": {"kind": task, "fact_ids": [f["fact_id"] for f in fs], "premise": premise}, "asset_id": aid,
             "origin": "real" if aid == "real" else "self_created_synthetic", "family": "phosagro-revenue-one-version" if aid == "real" else "synthetic-fixtures-derived-from-step10",
             "context": ctx, "locators": locators,
             "expected": {"layer": "scenario" if suite == "scenario" else "user" if suite == "interface" else "financial", "status": "completed" if suite == "scenario" else "answered", "reason_code": "signal_true" if suite == "scenario" else "ok", "reason_namespace": "scenario" if suite == "scenario" else "financial_tool",
                          "outputs": [], "formula_id": None, "correction": None, "absence_scope": None, "required_evidence_ids": refs,
                          "mandatory_warnings": ["synthetic_data_not_issuer_facts"] if aid != "real" else ["manual_annotation", "source_checked_by_assistant", "rights_for_public_copy_unconfirmed", "auditor_qualified_opinion_segment_disclosure"]},
             "reproduction": {"entrypoint": "requires_adapter", "parameters": None, "top_k": None},
             "capability": {"B": "requires_adapter", "C": "requires_adapter", "component": "reference_only", "note": "Current B/C accept a growth template, not this arbitrary task text."},
             "split": "evaluation_reserved" if reserved else "dev_open",
             "history": {"underlying_data_used_in_development": True, "prior_artifacts": ["docs/first_scenario.md", "evaluation/step9_2026-11-09/report.json"] if aid == "real" else ["tests/test_simulation.py", "evaluation/step10_2026-11-09/report.json"],
                         "question_status": "new_formulation_existing_data" if reserved else "development_case_reused", "model_executed_after_freeze": False,
                         "known_observation": "Step9 C/LLM hit call_limit, not a correct financial refusal; expected remains missing." if task == "top1_growth" else None},
             "verification": {"status": "assistant_checked", "checked_by": "Codex", "human_reviewed": False,
                              "methods": ["manual_semantic_review", "source_page4_visual_recheck" if aid == "real" else "self_created_fixture_consistency", "independent_fraction_or_literal_control"],
                              "proof": "evaluation/step11_2026-11-09/source-verification.json" if aid == "real" else "evaluation/step11_2026-11-09/reference-checks.json"}}
        cases.append(c); return c, b, fs
    def output(c, name, value, currency, scale, periods, refs, precision=0, rounding="exact_source_integer"):
        c["expected"]["outputs"].append({"measure": name, "value": value, "currency": currency, "scale": scale, "periods": deepcopy(periods), "precision": precision, "rounding": rounding, "absolute_tolerance": "0", "evidence_ids": list(refs)})
    def growth(c, b):
        fs = b["facts"]; refs = [f["evidence_id"] for f in fs]
        for i, value in enumerate(("440304", "507689")):
            output(c, "previous_revenue" if i == 0 else "current_revenue", value, "RUB", 1000000, [fs[i]["period"]], [refs[i]])
        output(c, "delta", "67385", "RUB", 1000000, c["context"]["periods"], refs)
        output(c, "growth_pct", "15.30", None, 1, c["context"]["periods"], refs, 2, "ROUND_HALF_UP")
        c["expected"]["formula_id"] = "annual_growth_v1"
    def user_route(c, historical=False, top_k=5, partial=False):
        c["reproduction"] = {"entrypoint": "user_query", "parameters": {"company": "ФосАгро", "scope": "группа", "standard": "МСФО", "metric": "выручка", "year": "9 месяцев 2024" if partial else "2024", "compare": "2023", "mode": "historical" if historical else "snapshot", "as_of": c["context"]["as_of"], "source": "search"}, "top_k": top_k}
        c["capability"] = {"B": "supported_template", "C": "supported_template", "component": "user_path", "note": "Lossless structured projection of this bounded task; no general Russian NLP is claimed. No run at step11."}
    for cid, year, index, value in (("QA01", 2023, 0, "440304"), ("QA02", 2024, 1, "507689")):
        c,b,fs = case(cid, f"Какова выручка группы «ФосАгро» по МСФО за полный {year} год в выбранной версии 2024? Укажи млн рублей и точное место источника.", "fact_value", "direct_fact", indexes=(index,), unit={"currency":"RUB","scale":1000000})
        output(c,"revenue",value,"RUB",1000000,c["context"]["periods"],[fs[0]["evidence_id"]])
        c["capability"]["component"] = "manual_registry_only"
    c,b,_ = case("QA03", "Как изменилась выручка группы «ФосАгро» по МСФО за полный 2024 к полному 2023 в выбранной версии? Покажи обе суммы, изменение в млн RUB, процент до двух знаков и обе ссылки.", "annual_growth", "calculation")
    growth(c,b); user_route(c)
    c,b,fs = case("QA04", "Вырази выручку группы «ФосАгро» по МСФО за полный 2024 из выбранной версии в млрд RUB, сохранив три знака и источник. Не меняй валюту или период.", "scale_conversion", "different_scale", reserved=True,indexes=(1,),unit={"currency":"RUB","scale":1000000000})
    output(c,"revenue","507.689","RUB",1000000000,c["context"]["periods"],[fs[0]["evidence_id"]],3,"exact_scale_conversion")
    c["expected"]["formula_id"] = "million_to_billion_v1"
    c,_,_ = case("QA05", "Позволяет ли именно подготовленный набор подтвердить выручку 2023 в первоначальной публикации отчёта 2023, а не сравнительный столбец версии 2024? Не подменяй версии.", "original_version_missing", "prepared_inventory_gap", reserved=True,indexes=(0,),version_policy="original_2023")
    c["expected"].update(status="missing",reason_code="prepared_original_version_missing",reason_namespace="reference_inventory",absence_scope="prepared_source_inventory",required_evidence_ids=[])
    c,_,_ = case("QA06", "Рассчитай годовое изменение выручки группы «ФосАгро» 2024/2023 по этой PDF-версии на момент 14.02.2025 10:00 +03:00. Если её публикация не подтверждена, объясни запрет.", "historical_growth", "temporal_refusal",historical=True)
    c["expected"].update(status="missing",reason_code="publication_unknown"); user_route(c,True)
    c,_,_ = case("QA07", "Проверь рост выручки группы «ФосАгро» 2024/2023 по выбранной версии, ограничив локальный поиск одним результатом. Нужны оба прежних Evidence; прямой ручной расчёт вместо поиска не допускается.", "top1_growth", "retrieval_coverage")
    c["expected"].update(status="missing",reason_code="verified_evidence_not_retrieved"); user_route(c,top_k=1)
    c,b,_ = case("QA08", "Проверь утверждение: в выбранной версии МСФО выручка группы «ФосАгро» за полный 2024 снизилась к полному 2023. Исправь неверное направление, покажи обе суммы, изменение и источники.", "correct_direction", "false_premise",reserved=True,premise="decrease")
    growth(c,b); c["expected"]["correction"] = "increase_not_decrease"; c["capability"]["component"] = "calculator_only_not_premise_QA"
    for cid, aid, status, reason in (("QA09","missing","missing","value_missing"),("QA10","conflict","conflict","incompatible_units")):
        question = "В собственном искусственном реестре нет предыдущего значения выручки. Можно ли вычислить годовой рост? Не считай отсутствие нулём." if aid == "missing" else "В собственной вымышленной группе предыдущая выручка размечена в USD, текущая в RUB. Можно ли считать годовой рост без конвертации?"
        c,b,fs = case(cid,question,"synthetic_"+aid,"prepared_value_missing" if aid=="missing" else "unit_conflict",aid=aid)
        c["expected"].update(status=status,reason_code=reason,absence_scope="prepared_registry_value" if aid=="missing" else None)
        c["reproduction"]={"entrypoint":"finance_tool","parameters":{"operation_id":"annual_growth_v1","previous_fact_id":fs[0]["fact_id"],"current_fact_id":fs[1]["fact_id"],"mode":"document_snapshot","as_of":None},"top_k":None}
        c["capability"]["component"]="finance_tool_supported"; c["capability"]["note"]="Existing finance API accepts this synthetic bundle; B/C UserQuery do not support this group."
    c,_,_ = case("UI01","Запусти сравнение выручки группы «ФосАгро» по МСФО за девять месяцев 2024 с полным 2023. Не считай девять месяцев полным годом.","partial_year_input","request_clarification",suite="interface")
    c["context"]["periods"][1]["end"]="2024-09-30";c["context"]["source"]="request_only"
    c["expected"].update(status="clarification",reason_code="period_needs_clarification",reason_namespace="user_path",required_evidence_ids=[],mandatory_warnings=[]);user_route(c,partial=True)
    for cid, aid, final, fees, ret in (("SC01","scenario_base","10098.00","2.00","0.98"),("SC02","scenario_costs","10073.50","6.00","0.74")):
        question="В искусственном сценарии с капиталом 10000 RUB, долей номинала 20%, комиссией1 RUB на сторону и нулевым проскальзыванием определи конечные деньги, комиссии и изменение после закрытия. Это не результат рынка." if cid=="SC01" else "В новом искусственном варианте прежних цен капитал10000 RUB, номинальная доля20,5%, комиссия3 RUB на сторону, проскальзывание50 б.п. в неблагоприятную сторону. Определи конечные деньги, комиссии и процент после закрытия; результат не рыночный."
        c,b,_=case(cid,question,"scenario_final","virtual_ledger",aid=aid,suite="scenario",reserved=cid=="SC02")
        for name,value,currency in (("final_equity",final,"RUB"),("total_fees",fees,"RUB"),("return_pct",ret,None)):
            output(c,name,value,currency,1,c["context"]["periods"],c["expected"]["required_evidence_ids"],2,"ROUND_HALF_UP")
        c["expected"]["formula_id"]="synthetic_cash_ledger_v1"
        c["reproduction"]={"entrypoint":"synthetic_simulation","parameters":None,"top_k":None}
        c["capability"]["component"]="synthetic_simulator_supported";c["capability"]["note"]="Separate simulator, not B/C financial QA; never include in QA accuracy denominator."
    for c in cases:
        if not c["expected"]["outputs"]:
            c["expected"]["required_evidence_ids"]=[]
        if c["origin"]=="real" and c["expected"]["status"]=="answered":
            c["expected"]["mandatory_warnings"] += ["snapshot_only_publication_unknown","source_rounding_limits_precision"]
        if c["suite"]=="scenario":
            c["expected"]["mandatory_warnings"]=["synthetic_only_not_market_performance"]
    dataset={"question_set_schema_version":"0.1","dataset_id":"kp2-question-set-v1","version":"1.0.0","created_at":datetime.now(timezone.utc).isoformat(),
             "scope":"One real PDF version/two real revenue facts; self-created synthetic cases. Reserved means no subsequent tuning, not blind/independent or a new issuer.",
             "assets":assets,"cases":cases}
    write(DEST/"questions.json",dataset)
    print(json.dumps({"authored_cases":len(cases),"financial_qa":10,"interface":1,"scenario":2,"model_calls":0}))


if __name__=="__main__":
    main()
