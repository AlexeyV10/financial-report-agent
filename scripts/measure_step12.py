"""prepare -> collect once -> grade/replay offline. No expected data enters collect."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from financial_assistant.measurement import (VERSION, FINANCIAL_IDS, UNSUPPORTED_IDS, grade_record,
                                           read, sha, summarize, write_new)


def utc():
    return datetime.now(timezone.utc).isoformat()


def controls():
    """Literal controls independently verified at step11; never simulate() for gold."""
    entry, exit = "2025-06-05T10:00:00+03:00", "2025-06-09T18:00:00+03:00"
    out = {}
    for cid, buy, sell, nominal_buy, nominal_sell, fee, cash_buy, cash_end in (
        ("SC01","100","105","2000","2100","1","7999","10098"),
        ("SC02","100.5","104.475","2010","2089.50","3","7987","10073.50")):
        out[cid] = {"entry_at":entry,"exit_at":exit,"final_quantity":0,"trades":[
            {"event":"buy","at":entry,"traded_quantity":20,"execution_price":buy,"notional":nominal_buy,"fee":fee,"cash":cash_buy,"quantity":20},
            {"event":"sell","at":exit,"traded_quantity":20,"execution_price":sell,"notional":nominal_sell,"fee":fee,"cash":cash_end,"quantity":0}]}
    return out


def prepare(folder):
    from financial_assistant.question_set import validate_frozen
    from financial_assistant.agent import Limits, SYSTEM_PROMPT, TOOLS, digest
    from dataclasses import asdict
    d, coverage, frozen = validate_frozen(ROOT)
    if folder.exists():
        raise ValueError("run_directory_exists")
    folder.mkdir(parents=True)
    cases = {c["case_id"]:c for c in d["cases"]}
    assets = {a["asset_id"]:a for a in d["assets"]}
    plan=[]
    def add(cid, variant):
        c=cases[cid]
        plan.append({"key":cid+"-"+variant.replace("/","_"),"case_id":cid,"variant":variant,"suite":c["suite"],
                     "origin":c["origin"],"split":c["split"],"asset_path":assets[c["asset_id"]]["path"],
                     "reproduction":c["reproduction"]})
    for cid in FINANCIAL_IDS+["UI01"]:
        add(cid,"B")
    add("UI01","C/LLM")
    for cid in ["QA09","QA10"]:
        add(cid,"finance_component")
    for cid in ["SC01","SC02"]:
        add(cid,"simulator")
    for key,k in [("R1",1),("R5",5)]:
        plan.append({"key":key,"case_id":key,"variant":"retrieval_component","suite":"retrieval_control",
                     "origin":"real","split":"dev_open","asset_path":assets["real"]["path"],
                     "reproduction":{"entrypoint":"retrieval_component","parameters":None,"top_k":k}})
    plan.append({"key":"SAFE01","case_id":"SAFE01","variant":"real_safety","suite":"scenario_safety_control",
                 "origin":"real","split":"dev_open","asset_path":assets["real"]["path"],
                 "reproduction":{"entrypoint":"real_safety","parameters":{"as_of":"2025-06-04T19:30:00+03:00"},"top_k":None}})
    for cid in FINANCIAL_IDS:
        add(cid,"C/LLM")
    write_new(folder/"execution-plan.json", plan)
    policy={"version":VERSION,"prepared_at":utc(),"scope":"One real PDF/two facts; dev templates, not blind or general QA",
            "financial_ids":FINANCIAL_IDS,"unsupported_financial_ids":UNSUPPORTED_IDS,"repetitions":1,
            "numeric_denominator_per_B_C":1,"refusal_denominator_per_B_C":2,"reserved_financial_B_C":0,
            "maximum_chat_requests":18,"max_decisions_per_case":6,"timeout_s":180,"per_call_s":90,
            "num_predict":256,"num_ctx":8192,"temperature":0,"think":False,
            "limits_defaults":asdict(Limits()),"per_case_max_search_results":"frozen reproduction.top_k",
            "cold_load":"No chat warmup; first measured chat includes load; per-case end-to-end includes tools",
            "time_boundaries":"B includes native validation/render; C includes native validation/render and spawned processes; simulator elapsed_s includes validation/render repeats, elapsed_to_result_s isolates simulate",
            "grading":"Actual structured payload + narrow existing-renderer text grammar; no free-text LLM grader. Gold used only after raw saved.",
            "claims":"4 numeric claims on answered growth; source facts + delta + displayed growth. Formula substitution is repetition; unexpected numeric lines fail.",
            "refusal":"Expected financial status/reason, no numeric payload; agent must complete. call_limit/timeout/error fail.",
            "empty_denominator":"not_measured, never 100%","tokens":"Actual /api/chat counters; missing responses/counters unknown, no estimates",
            "cost":"No API payments; total monetary cost/electricity/hardware not measured",
            "scenario_controls":controls(),"scenario_control_provenance":"Step11 independent-controls/reference-checks; literal frozen controls, not production output",
            "known_prior_failure":"Step9 C top1 call_limit retained; not expected success",
            "human_reviewed":False}
    write_new(folder/"protocol.json",policy)
    paths=set(frozen["files"])|set(frozen["prototype_source_sha256"])|{"data/question_sets/kp2_v1/manifest.json"}
    for name in ["src","scripts","tests"]:
        paths.update(str(p.relative_to(ROOT)).replace("\\","/") for p in (ROOT/name).rglob("*.py"))
    paths.update(["scripts/local_model.ps1","data/config/local_model.json","tmp/pdfs/phosagro-2024-ru.pdf","tmp/retrieval/document.sqlite"])
    manifest={"run_schema_version":"0.1","run_id":folder.name,"prepared_at":utc(),"python":platform.python_version(),"platform":platform.platform(),
              "prompt_sha256":digest(SYSTEM_PROMPT),"tool_schema_sha256":digest(TOOLS),
              "dataset_id":d["dataset_id"],"dataset_version":d["version"],"coverage":coverage,
              "input_sha256":{name:sha(ROOT/name) for name in sorted(paths)},
              "protocol_sha256":{name:sha(folder/name) for name in ["protocol.json","execution-plan.json"]},
              "source_policy":"Only hashes for PDF/index; full originals remain tmp","grading_version":VERSION}
    write_new(folder/"run-manifest.json",manifest)
    print("Протокол сохранён до запуска:",folder.relative_to(ROOT))


def grade(folder, save=False):
    manifest, policy, seal = read(folder/"run-manifest.json"),read(folder/"protocol.json"),read(folder/"collection.json")
    for name,h in manifest["protocol_sha256"].items():
        if sha(folder/name)!=h:
            raise ValueError("protocol_changed")
    # Replay requires gold and grader identity, not PDF/index/model or production solving.
    for name in ["data/question_sets/kp2_v1/questions.json","src/financial_assistant/measurement.py","scripts/measure_step12.py"]:
        if sha(ROOT/name)!=manifest["input_sha256"][name]:
            raise ValueError("gold_or_grader_changed")
    for name,h in seal["raw_sha256"].items():
        if Path(name).name!=name or sha(folder/"raw"/name)!=h:
            raise ValueError("raw_changed")
    cases={c["case_id"]:c for c in read(ROOT/"data/question_sets/kp2_v1/questions.json")["cases"]}
    rows, search, safety=[],[],[]
    for task in read(folder/"execution-plan.json"):
        raw=read(folder/"raw"/(task["key"]+".json"))
        output=raw.get("output") or {}
        if task["case_id"] in cases:
            result=grade_record(raw,cases[task["case_id"]],policy["scenario_controls"])
            actual=output.get("user_response",output)
            row={k:raw[k] for k in ["case_id","variant","suite","split","origin","elapsed_s","availability"]}
            row.update(result,actual_status=actual.get("status"),actual_reason=actual.get("reason_code"),
                       execution_status=output.get("status"),execution_reason=output.get("reason_code"))
            if task["variant"]=="C/LLM":
                trace=output.get("trace",{})
                log=folder/"raw"/(task["key"]+".calls.jsonl")
                calls=[json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
                received=[c for c in calls if c["event"]=="chat_response_received"]
                started=sum(c["event"]=="chat_request_started" for c in calls)
                complete=started==len(received) and all(type(c.get(k)) is int for c in received for k in ["input_tokens","output_tokens"])
                row["usage"]={"decision_attempts":len(trace.get("events",[])),"chat_requests_started":started,"chat_responses_received":len(received),
                              "usage_complete":complete,"observed_input_tokens":sum(c.get("input_tokens") or 0 for c in received),
                              "observed_output_tokens":sum(c.get("output_tokens") or 0 for c in received),"cost":None,
                              "load_duration_ns":[c.get("load_duration_ns") for c in received]}
            rows.append(row)
        elif task["variant"]=="retrieval_component":
            needed={loc["evidence_id"] for loc in cases["QA03"]["locators"]}
            covered={e for hit in output.get("hits",[]) for e in hit["existing_manual_evidence_ids"]}
            search.append({"case_id":task["case_id"],"query":"выручка 2024 2023","top_k":task["reproduction"]["top_k"],
                           "required_evidence_covered":sorted(needed&covered),"required_count":len(needed),
                           "covered_count":len(needed&covered),"both_found":needed<=covered,"elapsed_s":raw["elapsed_s"],"hits":output.get("hits",[])})
        else:
            safety.append({"case_id":task["case_id"],"passed":output.get("status")=="blocked" and output.get("reason_code")=="publication_unknown"
                           and output.get("ledger")==[] and output.get("return_pct") is None,"output":output,"elapsed_s":raw["elapsed_s"]})
    result={"grading_version":VERSION,"run_manifest_sha256":sha(folder/"run-manifest.json"),"collection_sha256":sha(folder/"collection.json"),
            "rows":rows,"metrics":summarize(rows),"retrieval":search,"real_source_safety":safety,
            "unsupported_financial_ids":UNSUPPORTED_IDS,"monetary_cost":None,"human_reviewed":False,
            "limitations":["One real PDF/two facts; only 3/10 financial tasks supported","All financial B/C cases dev/open; no supported reserved financial cases",
                            "Single pass, one numeric question; no market quality/advantage claim","Separate interface/component/simulator denominators; structured renderer, not general free-text QA"]}
    if save:
        write_new(folder/"results.json",result)
    elif not (folder/"results.json").exists() or read(folder/"results.json")!=result:
        raise ValueError("offline_replay_differs")
    print(json.dumps({"metrics":result["metrics"],"offline_replay_matches_saved":not save},ensure_ascii=False,indent=2))
    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["prepare","collect","grade","replay"])
    p.add_argument("--run-dir",required=True,type=Path)
    a=p.parse_args()
    folder=a.run_dir.resolve()
    try:
        if not folder.is_relative_to(ROOT/"evaluation") or folder==ROOT/"evaluation":
            raise ValueError("run_directory_must_be_inside_evaluation")
        if a.action=="prepare":
            prepare(folder)
        elif a.action=="collect":
            from financial_assistant.measurement_collect import collect
            collect(ROOT,folder)
        else:
            grade(folder,save=a.action=="grade")
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("Ошибка измерения:",str(exc)[:180])
        return 2


if __name__=="__main__":
    raise SystemExit(main())
