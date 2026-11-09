"""Trusted step12 collection only. Does not load questions/expected/reference gold."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from unittest.mock import patch

from . import local_model, user_path
from .agent import Limits, retrieval_summary, run_agent
from .finance import calculate_metric, validate_financial_result
from .measurement import read, sha, write_new
from .simulation import assess_real_source, simulate, validate_scenario_result
from .simulation_view import render_scenario


def utc():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MeasuredAdapter:
    """Only metadata around actual /api/chat requests, no prompt/content/reasoning log."""
    base: local_model.OllamaAdapter
    call_log: str

    @property
    def metadata(self):
        return dict(self.base.metadata, measurement_wrapper="request-counters-v1")

    def decide(self, observation, timeout_s):
        import json
        original = local_model.local_json
        def event(value):
            with Path(self.call_log).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(value, ensure_ascii=False) + "\n")
                stream.flush()
        def measured(route, payload=None, timeout=5):
            if route != "/api/chat":
                return original(route, payload, timeout)
            tick = time.monotonic()
            event({"event":"chat_request_started", "at":utc()})
            try:
                res = original(route, payload, timeout)
                event({"event":"chat_response_received", "at":utc(), "elapsed_s":time.monotonic()-tick,
                       "input_tokens":res.get("prompt_eval_count"), "output_tokens":res.get("eval_count"),
                       "load_duration_ns":res.get("load_duration"), "total_duration_ns":res.get("total_duration")})
                return res
            except Exception as exc:
                event({"event":"chat_request_failed", "at":utc(), "error_type":type(exc).__name__})
                raise
        with patch.object(local_model, "local_json", measured):
            return self.base.decide(observation, timeout_s)


def input_receipt(root, task):
    obj = read(root/task["asset_path"])
    bundle = obj.get("financial_bundle", obj)
    doc = bundle["document"]
    return obj, {"asset_path":task["asset_path"], "asset_sha256":sha(root/task["asset_path"]),
                 "reproduction":task["reproduction"], "document":{k:doc[k] for k in
                  ("entity_id", "consolidation", "accounting_standard", "document_id", "version_id", "sha256")}}


def collect_one(root, run_dir, task, config):
    obj, receipt = input_receipt(root, task)
    variant = task["variant"]
    record = {"record_schema_version":"0.1", "case_id":task["case_id"], "variant":variant,
              "suite":task["suite"], "split":task["split"], "origin":task["origin"], "input":receipt,
              "started_at":utc(), "availability":"executed", "origin_notices":[], "searches":[]}
    pdf, db = root/"tmp/pdfs/phosagro-2024-ru.pdf", root/"tmp/retrieval/document.sqlite"
    tick = time.monotonic()
    try:
        rep = task["reproduction"]
        if variant in {"B", "C/LLM"}:
            q = user_path.UserQuery(**rep["parameters"])
            if variant == "B":
                original = user_path.search_index
                def capture(*args, **kwargs):
                    r = original(*args, **kwargs)
                    record["searches"].append(retrieval_summary(r, kwargs["top_k"]))
                    return r
                with patch.object(user_path, "search_index", capture):
                    record["output"] = user_path.run_user_query(q, obj, pdf, db, rep["top_k"])
            else:
                base = local_model.OllamaAdapter(config["model"], config["model_digest"], config["server_version"])
                log = run_dir/"raw"/(task["key"]+".calls.jsonl")
                adapter = MeasuredAdapter(base, str(log))
                limits = Limits(max_search_results=rep["top_k"])
                record["output"] = run_agent(q, obj, adapter, pdf, db, limits)
                record["searches"] = [e["output"] for e in record["output"]["trace"]["events"]
                                       if e.get("tool")=="search_evidence" and e.get("status")=="ok"]
        elif variant == "finance_component":
            result = calculate_metric(obj, rep["parameters"])
            # Generation validates the production contract; offline grader has independent gold.
            validate_financial_result(result, obj, rep["parameters"])
            record["output"] = {"status":result["status"], "reason_code":result["reason_code"],
                                "financial_result":result, "text":"Искусственный реестр: не факты эмитента."}
            record["origin_notices"] = ["synthetic_data_not_issuer_facts"]
        elif variant == "simulator":
            result = simulate(obj)
            record["elapsed_to_result_s"] = time.monotonic()-tick
            validate_scenario_result(result, obj)
            record["output"] = result
            record["text"] = render_scenario(obj, result)
        elif variant == "real_safety":
            record["output"] = assess_real_source(obj, rep["parameters"]["as_of"])
        elif variant == "retrieval_component":
            from .retrieval import search_index
            r = search_index(db, pdf, obj, "выручка 2024 2023", entity_id=obj["document"]["entity_id"],
                version_id=obj["document"]["version_id"], top_k=rep["top_k"], mode="document_snapshot", as_of=None)
            record["output"] = retrieval_summary(r, rep["top_k"])
        else:
            raise ValueError("unapproved_route")
    except Exception as exc:
        # Safe error identity, never arbitrary source/provider error text.
        record.update(availability="execution_error", error_type=type(exc).__name__, output=None)
    record.update(ended_at=utc(), elapsed_s=time.monotonic()-tick)
    return record


def collect(root, run_dir):
    plan, manifest = read(run_dir/"execution-plan.json"), read(run_dir/"run-manifest.json")
    for name, digest in manifest["input_sha256"].items():
        if sha(root/name) != digest:
            raise ValueError("input_changed: "+name)
    for name, digest in manifest["protocol_sha256"].items():
        if sha(run_dir/name) != digest:
            raise ValueError("protocol_changed")
    if (run_dir/"raw").exists():
        raise ValueError("collection_already_started; preserve existing attempt")
    (run_dir/"raw").mkdir()
    config = read(root/"data/config/local_model.json")
    for task in plan:
        record = collect_one(root, run_dir, task, config)
        write_new(run_dir/"raw"/(task["key"]+".json"), record)
        out = record.get("output") or {}
        print(task["key"], record["availability"], out.get("status"), out.get("reason_code"),
              round(record["elapsed_s"],3), flush=True)
    write_new(run_dir/"collection.json", {"ended_at":utc(), "raw_sha256":{
        p.name:sha(p) for p in sorted((run_dir/"raw").iterdir())}, "one_pass":True})
