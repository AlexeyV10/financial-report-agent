"""Reference-set validation, not an answering system or an LLM quality evaluator.

Arithmetic references use Fraction/literal controls, never contracts.answer,
calculate_metric, run_agent or simulate. Existing validators only check inputs.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

from .contracts import available_from, instant, validate_bundle
from .simulation import checked_inputs

VERSION = "0.1"
PREFIX = "data/question_sets/kp2_v1/"
ROUTES = {
    "fact_value": ("financial_qa", "direct_fact", "requires_adapter", "manual_registry_only"),
    "annual_growth": ("financial_qa", "calculation", "user_query", "user_path"),
    "scale_conversion": ("financial_qa", "different_scale", "requires_adapter", "reference_only"),
    "original_version_missing": ("financial_qa", "prepared_inventory_gap", "requires_adapter", "reference_only"),
    "historical_growth": ("financial_qa", "temporal_refusal", "user_query", "user_path"),
    "top1_growth": ("financial_qa", "retrieval_coverage", "user_query", "user_path"),
    "correct_direction": ("financial_qa", "false_premise", "requires_adapter", "calculator_only_not_premise_QA"),
    "synthetic_missing": ("financial_qa", "prepared_value_missing", "finance_tool", "finance_tool_supported"),
    "synthetic_conflict": ("financial_qa", "unit_conflict", "finance_tool", "finance_tool_supported"),
    "partial_year_input": ("interface", "request_clarification", "user_query", "user_path"),
    "scenario_final": ("scenario", "virtual_ledger", "synthetic_simulation", "synthetic_simulator_supported"),
}


class QuestionSetError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise QuestionSetError(message)


def shape(obj, names):
    need(isinstance(obj, dict) and set(obj) == set(names.split()), "Invalid fields")


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")


def digest(obj):
    return hashlib.sha256(encoded(obj)).hexdigest()


def _unique(pairs):
    obj = {}
    for k, v in pairs:
        need(k not in obj, "Duplicate JSON key")
        obj[k] = v
    return obj


def read_json(path):
    path = Path(path)
    need(path.is_file() and path.stat().st_size <= 1048576, "Missing or oversized JSON")
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)


def number(value):
    need(isinstance(value, str) and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is not None and len(value) <= 40, "Numeric reference must be a decimal string")
    return Fraction(value)


def fixed(value, places):
    """Exact rational HALF_UP; independent of production Decimal arithmetic."""
    sign = "-" if value < 0 else ""
    scaled = abs(value) * 10**places
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    if 2 * remainder >= scaled.denominator:
        quotient += 1
    if places == 0:
        return sign + str(quotient)
    whole, frac = divmod(quotient, 10**places)
    return f"{sign}{whole}.{frac:0{places}d}"


def load_assets(dataset, root):
    root = Path(root).resolve()
    assets, values = {}, {}
    need(isinstance(dataset["assets"], list) and 1 <= len(dataset["assets"]) <= 16, "Invalid asset catalog")
    for a in dataset["assets"]:
        shape(a, "asset_id path kind sha256 parent_asset_id source_asset_id")
        need(isinstance(a["asset_id"], str) and a["asset_id"] not in assets, "Duplicate asset ID")
        path = a["path"]
        need(isinstance(path, str) and (path in {"data/examples/reference_bundle.json", "data/synthetic/scenario_v1.json"} or path.startswith(PREFIX + "assets/")), "Asset path outside allowlist")
        resolved = (root / path).resolve()
        need(resolved.is_relative_to(root / "data") and ".." not in Path(path).parts and resolved.suffix in {".json", ".txt"}, "Unsafe source/asset path")
        need(resolved.is_file() and resolved.stat().st_size <= 262144, "Missing or oversized asset")
        raw = resolved.read_bytes()
        need(hashlib.sha256(raw).hexdigest() == a["sha256"], "Asset hash mismatch")
        assets[a["asset_id"]] = a
        if a["kind"] == "synthetic_text":
            need(resolved.suffix == ".txt" and raw.startswith(b"SELF-CREATED SYNTHETIC QA TABLE"), "Not own synthetic source")
            values[a["asset_id"]] = raw.decode("utf-8")
        else:
            need(a["kind"] in {"real_bundle", "synthetic_bundle", "synthetic_scenario"}, "Unknown asset kind")
            values[a["asset_id"]] = read_json(resolved)
    for aid, a in assets.items():
        if a["parent_asset_id"] is not None:
            need(a["parent_asset_id"] in assets and a["parent_asset_id"] != aid, "Invalid parent lineage")
        if a["kind"] == "synthetic_text": continue
        value = values[aid]
        b = value["financial_bundle"] if a["kind"] == "synthetic_scenario" else value
        validate_bundle(b)
        doc = b["document"]
        need(all(o["review"]["status"] != "human_reviewed" and o["review"]["human_reviewer"] is None for o in [doc] + b["facts"] + b["evidence"]), "Unestablished human verification")
        if a["kind"] == "real_bundle":
            need(a["path"] == "data/examples/reference_bundle.json" and doc["entity_id"] == "phosagro_group", "Real source identity mismatch")
            need(doc["publication"]["precision"] == "unknown" and doc["publication"]["version_binding"] == "unproven" and doc["rights"]["status"] == "unconfirmed", "Invented real publication/rights")
            proof=read_json(root / "evaluation/step11_2026-11-09/source-verification.json")
            need(proof["checked_by"]=="Codex" and proof["human_reviewed"] is False and doc["sha256"]==proof["pdf_sha256"] and doc["byte_length"]==proof["pdf_bytes"], "Source verification not bound")
            for ev in b["evidence"]:
                need(ev["raw_value"]==proof["verified"][ev["column_label"]+"_raw"] and ev["currency"]=="RUB" and ev["scale"]==1000000, "Reference differs from page verification")
                need(all(ev[k]==proof["verified"][k] for k in ("pdf_page","page_region","printed_page","statement_page")), "Primary locator changed")
        elif a["kind"] == "synthetic_bundle":
            source = values.get(a["source_asset_id"])
            need(isinstance(source, str) and a["parent_asset_id"] == "scenario_base", "Synthetic lineage/source missing")
            need(doc["document_id"].startswith("synthetic-qa-") and doc["entity_id"].startswith("synthetic-qa-") and doc["document_url"].startswith("https://example.invalid/qa/"), "Real/synthetic mixing")
            need(doc["sha256"] == hashlib.sha256(source.encode()).hexdigest() and doc["byte_length"] == len(source.encode()) and doc["version_id"] == "sha256:" + doc["sha256"], "Synthetic source version mismatch")
            need(all(f"{e['column_label']}|revenue|{e['raw_value']}|{e['currency']}|{e['scale']}" in source.splitlines() for e in b["evidence"]), "Synthetic row mismatch")
        else:
            checked_inputs(value)  # Schema/admission input checks only, no simulation.
    need(set(assets)=={"real","scenario_base","missing_text","missing","conflict_text","conflict","scenario_costs"}, "Asset coverage changed without version")
    for aid,a in assets.items():
        parent="scenario_base" if aid in {"missing","conflict","scenario_costs"} else None
        source=aid+"_text" if aid in {"missing","conflict"} else None
        need(a["parent_asset_id"]==parent and a["source_asset_id"]==source,"Invalid source lineage")
    return assets, values


def bound_context(c, obj, asset):
    b = obj["financial_bundle"] if c["suite"] == "scenario" else obj
    doc, fs = b["document"], {f["fact_id"]: f for f in b["facts"]}
    selected = [fs[fid] for fid in c["task"]["fact_ids"]]
    ctx = c["context"]
    shape(ctx, "entity_id entity_name consolidation accounting_standard document_id document_version document_sha256 document_url asset_sha256 metric_id periods input_units analysis_mode as_of source requested_version output_unit")
    for key, value in (("entity_id",doc["entity_id"]),("entity_name",doc["entity_name"]),("consolidation",doc["consolidation"]),("accounting_standard",doc["accounting_standard"]),("document_id",doc["document_id"]),("document_version",doc["version_id"]),("document_sha256",doc["sha256"]),("document_url",doc["document_url"]),("asset_sha256",asset["sha256"])):
        need(ctx[key] == value, "Reference context mismatch: " + key)
    periods = [f["period"] for f in selected]
    kind = c["task"]["kind"]
    if kind == "scenario_final": periods = [{"kind":"scenario_window", **obj["window"]}]
    if kind == "partial_year_input":
        periods = json.loads(json.dumps(periods)); periods[1]["end"] = "2024-09-30"
    need(ctx["periods"] == periods, "Full periods do not match task")
    need(ctx["input_units"] == [{"fact_id":f["fact_id"],"currency":f["currency"],"scale":f["scale"]} for f in selected], "Input units missing/wrong")
    mode = "historical_as_of" if kind in {"historical_growth","scenario_final"} else "document_snapshot"
    as_of = obj["decision_at"] if kind == "scenario_final" else "2025-02-14T10:00:00+03:00" if kind == "historical_growth" else None
    need(ctx["analysis_mode"] == mode and ctx["as_of"] == as_of, "Mode/as-of not bound")
    if as_of is not None: instant(as_of)
    policy = "original_2023" if kind == "original_version_missing" else "selected_version"
    need(ctx["requested_version"] == policy, "Version-policy substitution")
    source = "request_only" if kind=="partial_year_input" else "synthetic_fixture" if c["origin"] != "real" else "local_search" if kind in {"annual_growth","historical_growth","top1_growth"} else "prepared_registry"
    need(ctx["source"] == source, "Source mode substitution")
    need(ctx["metric_id"] == ("portfolio_final_value" if kind=="scenario_final" else "revenue"), "Metric mismatch")
    unit = {"currency":"RUB","scale":1000000000} if kind=="scale_conversion" else {"currency":"RUB","scale":1000000} if kind=="fact_value" else None
    need(ctx["output_unit"] == unit, "Requested output scale changed")
    evs = {e["evidence_id"]:e for e in b["evidence"]}
    expected_locators = [{k:evs[f["evidence_id"]][k] for k in ("evidence_id","document_id","version_id","document_sha256","pdf_page","printed_page","statement_page","page_region","row_label","column_label","period","currency","scale")} for f in selected]
    need(c["locators"] == expected_locators, "Incomplete/wrong source locators")
    return b, selected


def reference_values(c, obj, b, fs):
    """Independent checking oracle for the few declared reference types only."""
    kind = c["task"]["kind"]
    refs = [f["evidence_id"] for f in fs]
    if kind == "fact_value":
        need(len(fs)==1, "Fact task needs one fact")
        f=fs[0]; return [("revenue",f["value"],f["currency"],f["scale"],[f["period"]],[f["evidence_id"]],0,"exact_source_integer")]
    if kind == "scale_conversion":
        need(len(fs)==1, "Conversion needs one fact")
        value=number(fs[0]["value"])*fs[0]["scale"]/1000000000
        return [("revenue",fixed(value,3),"RUB",1000000000,[fs[0]["period"]],refs,3,"exact_scale_conversion")]
    if kind in {"annual_growth","correct_direction"}:
        need(len(fs)==2 and fs[0]["period"]["end"] < fs[1]["period"]["end"], "Reversed/missing formula inputs")
        previous,current=[number(f["value"]) for f in fs]
        values=[("previous_revenue",fs[0]["value"],"RUB",1000000,[fs[0]["period"]],[refs[0]],0,"exact_source_integer"),
                ("current_revenue",fs[1]["value"],"RUB",1000000,[fs[1]["period"]],[refs[1]],0,"exact_source_integer"),
                ("delta",fixed(current-previous,0),"RUB",1000000,c["context"]["periods"],refs,0,"exact_source_integer"),
                ("growth_pct",fixed((current-previous)*100/previous,2),None,1,c["context"]["periods"],refs,2,"ROUND_HALF_UP")]
        return values
    if kind=="scenario_final":
        # Same fixed fixture policy, different arithmetic implementation, no simulate().
        p=obj["portfolio"]; capital=number(p["initial_cash"]); fraction=number(p["max_notional_fraction"]); fee=number(p["fee_fixed"]); slip=number(p["slippage_bps"])/10000
        entry=next(s["open"] for s in obj["calendar"]["sessions"] if instant(s["open"]) > instant(obj["decision_at"]))
        prices={o["at"]:number(o["price"]) for o in obj["prices"]["observations"]}
        buy=prices[entry]*(1+slip); sell=prices[obj["window"]["end"]]*(1-slip); lot=p["lot_size"]
        budget=Fraction((capital*fraction*100).__floor__(),100); quantity=(budget/(buy*lot)).__floor__()*lot
        paid=number(fixed(quantity*buy,2)); received=number(fixed(quantity*sell,2)); final=capital-paid-fee+received-fee
        need(quantity>0 and paid+fee<=capital and final>=0, "Reference not feasible")
        span=c["context"]["periods"]
        return [("final_equity",fixed(final,2),"RUB",1,span,refs,2,"ROUND_HALF_UP"),("total_fees",fixed(2*fee,2),"RUB",1,span,refs,2,"ROUND_HALF_UP"),("return_pct",fixed((final-capital)*100/capital,2),None,1,span,refs,2,"ROUND_HALF_UP")]
    return []


def _validate_dataset(d, root):
    shape(d,"question_set_schema_version dataset_id version created_at scope assets cases")
    need(d["question_set_schema_version"]==VERSION and d["dataset_id"]=="kp2-question-set-v1" and d["version"]=="1.0.0", "Unsupported set/schema version")
    instant(d["created_at"]); need(isinstance(d["scope"],str) and "not blind" in d["scope"], "Scope/limitations missing")
    assets,objects=load_assets(d,root)
    need(isinstance(d["cases"],list) and 1<=len(d["cases"])<=32,"Invalid case list")
    ids, signatures, normalized_questions = set(),set(),set()
    numeric=0
    for c in d["cases"]:
        shape(c,"case_id question suite category tags task asset_id origin family context locators expected reproduction capability split history verification")
        need(isinstance(c["case_id"],str) and re.fullmatch(r"(?:QA|UI|SC)\d{2}",c["case_id"]) and c["case_id"] not in ids,"Duplicate/invalid case ID");ids.add(c["case_id"])
        q=c["question"];need(isinstance(q,str) and 20<=len(q)<=1200 and q.isprintable(),"Invalid question")
        normalized=" ".join(q.casefold().split());need(normalized not in normalized_questions,"Duplicate question wording");normalized_questions.add(normalized)
        shape(c["task"],"kind fact_ids premise");kind=c["task"]["kind"];need(kind in ROUTES,"Unknown task")
        need(isinstance(c["task"]["fact_ids"],list) and 1<=len(c["task"]["fact_ids"])<=2 and len(set(c["task"]["fact_ids"]))==len(c["task"]["fact_ids"]),"Invalid fact selection")
        need(c["task"]["premise"]==("decrease" if kind=="correct_direction" else None),"Premise lost/changed")
        need(c["asset_id"] in assets,"Unknown asset");a=assets[c["asset_id"]];obj=objects[c["asset_id"]]
        real=a["kind"]=="real_bundle";need(c["origin"]==("real" if real else "self_created_synthetic"),"Origin/issuer attribution mismatch")
        need(c["family"]==("phosagro-revenue-one-version" if real else "synthetic-fixtures-derived-from-step10"),"Missing data-dependence family")
        suite,category,route,component=ROUTES[kind]
        need((c["suite"],c["category"],c["tags"])==(suite,category,[kind]),"Suite/category substitution")
        b,fs=bound_context(c,obj,a)
        signature=digest({"asset":c["asset_id"],"task":c["task"],"context":c["context"]})
        need(signature not in signatures,"Duplicate semantic task");signatures.add(signature)
        e=c["expected"];shape(e,"layer status reason_code reason_namespace outputs formula_id correction absence_scope required_evidence_ids mandatory_warnings")
        values=reference_values(c,obj,b,fs)
        status,reason,namespace="answered","ok","financial_tool"
        if kind=="original_version_missing":status,reason,namespace="missing","prepared_original_version_missing","reference_inventory"
        elif kind=="historical_growth":
            need(available_from(b["document"]) is None,"Historical reference assumes unknown publication")
            status,reason="missing","publication_unknown"
        elif kind=="top1_growth":status,reason="missing","verified_evidence_not_retrieved"
        elif kind=="synthetic_missing":
            need(fs[0]["value"] is None and fs[1]["value"] is not None,"Missingness not established")
            status,reason="missing","value_missing"
        elif kind=="synthetic_conflict":
            need(fs[0]["currency"] != fs[1]["currency"],"Conflict not established")
            status,reason="conflict","incompatible_units"
        elif kind=="partial_year_input":status,reason,namespace="clarification","period_needs_clarification","user_path"
        elif kind=="scenario_final":status,reason,namespace="completed","signal_true","scenario"
        layer="scenario" if suite=="scenario" else "user" if suite=="interface" else "financial"
        need((e["layer"],e["status"],e["reason_code"],e["reason_namespace"])==(layer,status,reason,namespace),"Refusal/layer/reason mismatch")
        formula="annual_growth_v1" if kind in {"annual_growth","correct_direction"} else "million_to_billion_v1" if kind=="scale_conversion" else "synthetic_cash_ledger_v1" if suite=="scenario" else None
        need(e["formula_id"]==formula and e["correction"]==("increase_not_decrease" if kind=="correct_direction" else None),"Formula/premise correction changed")
        absence="prepared_source_inventory" if kind=="original_version_missing" else "prepared_registry_value" if kind=="synthetic_missing" else None
        need(e["absence_scope"]==absence,"Absence incorrectly attributed to entire report/world")
        need(isinstance(e["outputs"],list) and len(e["outputs"])==len(values),"Refusal contains numbers or answer lacks claims")
        refs=[]
        for actual,expected in zip(e["outputs"],values):
            shape(actual,"measure value currency scale periods precision rounding absolute_tolerance evidence_ids")
            name,value,currency,scale,periods,eids,precision,rounding=expected
            number(actual["value"])
            gold={"measure":name,"value":value,"currency":currency,"scale":scale,"periods":periods,"precision":precision,"rounding":rounding,"absolute_tolerance":"0","evidence_ids":eids}
            need(encoded(actual)==encoded(gold),"Number/unit/period/evidence/rounding reference mismatch")
            refs.extend(eids)
        need(e["required_evidence_ids"]==list(dict.fromkeys(refs)),"Required evidence incomplete or wrong for refusal")
        warnings=[] if suite=="interface" else ["synthetic_only_not_market_performance"] if suite=="scenario" else ["synthetic_data_not_issuer_facts"] if not real else ["manual_annotation","source_checked_by_assistant","rights_for_public_copy_unconfirmed","auditor_qualified_opinion_segment_disclosure"]+(["snapshot_only_publication_unknown","source_rounding_limits_precision"] if status=="answered" else [])
        need(e["mandatory_warnings"]==warnings,"Mandatory limits removed")
        numeric+=bool(values)
        repro=c["reproduction"];shape(repro,"entrypoint parameters top_k")
        need(repro["entrypoint"]==route,"Invented/lossy reproduction route")
        cap=c["capability"];shape(cap,"B C component note")
        support="supported_template" if route=="user_query" else "requires_adapter"
        need(cap["B"]==cap["C"]==support and cap["component"]==component and isinstance(cap["note"],str) and len(cap["note"])>20,"False prototype capability")
        if route=="user_query":
            params={"company":"ФосАгро","scope":"группа","standard":"МСФО","metric":"выручка","year":"9 месяцев 2024" if kind=="partial_year_input" else "2024","compare":"2023","mode":"historical" if kind=="historical_growth" else "snapshot","as_of":c["context"]["as_of"],"source":"search"}
            need(repro["parameters"]==params and type(repro["top_k"]) is int and repro["top_k"]==(1 if kind=="top1_growth" else 5),"Question projected to a different default request")
        elif route=="finance_tool":
            params={"operation_id":"annual_growth_v1","previous_fact_id":fs[0]["fact_id"],"current_fact_id":fs[1]["fact_id"],"mode":"document_snapshot","as_of":None}
            need(repro["parameters"]==params and repro["top_k"] is None,"Wrong component inputs")
        else:need(repro["parameters"] is None and repro["top_k"] is None,"No executable arbitrary command allowed")
        h=c["history"];shape(h,"underlying_data_used_in_development prior_artifacts question_status model_executed_after_freeze known_observation")
        need(h["underlying_data_used_in_development"] is True and h["model_executed_after_freeze"] is False,"False novelty/execution claim")
        need(isinstance(h["prior_artifacts"],list) and h["prior_artifacts"],"Prior use not documented")
        for p in h["prior_artifacts"]:
            need(isinstance(p,str) and p.startswith(("docs/","tests/","evaluation/")) and ".." not in Path(p).parts and (Path(root)/p).resolve().is_relative_to(Path(root).resolve()) and (Path(root)/p).is_file(),"Unsafe/missing prior artifact")
        reserved=kind in {"scale_conversion","original_version_missing","correct_direction"} or c["asset_id"]=="scenario_costs"
        need(c["split"]==("evaluation_reserved" if reserved else "dev_open") and h["question_status"]==("new_formulation_existing_data" if reserved else "development_case_reused"),"Development data relabeled as reserved")
        need((h["known_observation"] is not None)==(kind=="top1_growth"),"Known agent failure omitted/misplaced")
        if kind=="top1_growth":need("call_limit" in h["known_observation"] and e["status"]=="missing","Observed failure replaced gold refusal")
        v=c["verification"];shape(v,"status checked_by human_reviewed methods proof")
        need(v["status"]=="assistant_checked" and v["checked_by"]=="Codex" and v["human_reviewed"] is False,"Invented person/human acceptance")
        need(isinstance(v["methods"],list) and "manual_semantic_review" in v["methods"] and "independent_fraction_or_literal_control" in v["methods"],"Missing reference verification")
        need(v["proof"] in {"evaluation/step11_2026-11-09/source-verification.json","evaluation/step11_2026-11-09/reference-checks.json"},"Unknown proof record")
        need((Path(root)/v["proof"]).is_file(),"Verification proof missing")
    counts=Counter(c["task"]["kind"] for c in d["cases"])
    need(counts==Counter({k:(2 if k in {"fact_value","scenario_final"} else 1) for k in ROUTES}),"Required task coverage changed")
    need(ids=={f"QA{i:02d}" for i in range(1,11)}|{"UI01","SC01","SC02"},"Stable case identities changed")
    proof=read_json(Path(root)/"evaluation/step11_2026-11-09/reference-checks.json")
    need(proof["dataset_canonical_sha256"]==digest(d) and proof["human_reviewed"] is False and proof["model_calls"]==0 and proof["prototype_answers_run"]==0,"Reference proof not bound to frozen preparation")
    return {"total":len(d["cases"]),"by_suite":dict(Counter(c["suite"] for c in d["cases"])),"by_origin":dict(Counter(c["origin"] for c in d["cases"])),
            "by_split":dict(Counter(c["split"] for c in d["cases"])),"by_route":dict(Counter(c["reproduction"]["entrypoint"] for c in d["cases"])),
            "categories":dict(Counter(c["category"] for c in d["cases"])),"numeric_reference_cases":numeric,"prototype_answers_run":0,"model_calls":0}


def validate_dataset(d, root):
    try:
        return _validate_dataset(d, root)
    except QuestionSetError:
        raise
    except (KeyError, TypeError, ValueError, OSError, ArithmeticError):
        raise QuestionSetError("Malformed reference input or source") from None


def validate_claim_context(claim, case, measure):
    """Contract for a future normalized assertion, not a free-text/LLM grader."""
    shape(claim,"measure value currency scale periods entity_id consolidation accounting_standard document_version evidence_ids asset_sha256 analysis_mode as_of")
    targets=[o for o in case["expected"]["outputs"] if o["measure"]==measure]
    need(len(targets)==1,"No eligible numeric target")
    target=targets[0];ctx=case["context"]
    for k in ("entity_id","consolidation","accounting_standard","document_version","asset_sha256","analysis_mode","as_of"):need(claim[k]==ctx[k],"Claim lacks correct context")
    for k in ("measure","currency","scale","periods","evidence_ids"):need(encoded(claim[k])==encoded(target[k]),"Claim unit/period/source mismatch")
    need(number(claim["value"])==number(target["value"]),"Incorrect numeric claim")


def validate_frozen(root, manifest=None):
    root=Path(root).resolve();path=root/PREFIX
    if manifest is None:manifest=read_json(path/"manifest.json")
    shape(manifest,"freeze_schema_version dataset_id version frozen_at dataset_canonical_sha256 files reserved_ids prototype_source_sha256 scope")
    need(manifest["freeze_schema_version"]==VERSION and manifest["dataset_id"]=="kp2-question-set-v1" and manifest["version"]=="1.0.0","Invalid freeze version")
    instant(manifest["frozen_at"])
    need(manifest["reserved_ids"]==["QA04","QA05","QA08","SC02"],"Reserved membership changed")
    need(isinstance(manifest["files"],dict) and len(manifest["files"])>=10,"Incomplete frozen file set")
    for name,sha in manifest["files"].items():
        allowed=name.startswith(PREFIX) or name in {"data/examples/reference_bundle.json","data/synthetic/scenario_v1.json","evaluation/step11_2026-11-09/source-verification.json","evaluation/step11_2026-11-09/reference-checks.json"}
        p=(root/name).resolve()
        need(allowed and ".." not in Path(name).parts and p.is_relative_to(root) and p.suffix in {".json",".txt",".md"},"Unsafe frozen file path")
        need(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha,"Frozen file changed: "+name)
    d=read_json(path/"questions.json")
    required={PREFIX+"questions.json",PREFIX+"REGISTER.md","evaluation/step11_2026-11-09/source-verification.json","evaluation/step11_2026-11-09/reference-checks.json"}|{a["path"] for a in d["assets"]}
    need(set(manifest["files"])==required,"Frozen source inventory incomplete")
    need(manifest["dataset_canonical_sha256"]==digest(d),"Frozen question set changed")
    before=read_json(root/"evaluation/step11_2026-11-09/before.json")["protected_sha256"]
    need(manifest["prototype_source_sha256"]==before,"Prototype version pin changed")
    for name,sha in before.items():
        need(hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,"Prototype changed since set preparation: "+name)
    return d,validate_dataset(d,root),manifest
