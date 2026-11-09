"""Integration smoke checks from this restored root. No downloads or hidden fallback."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase",choices=["minimal","source","llm"])
    a=p.parse_args()
    folder=ROOT/"output"/("step13-"+a.phase)
    if folder.exists():
        print("Каталог этой проверки уже существует; сохранённый прогон не заменяется.")
        return 2
    folder.mkdir(parents=True)
    runs=[]
    def run(name,args,rc,tokens=(),trace=None,check=None):
        if trace:
            args=[*args,"--trace",str(folder/(name+".trace.json"))]
        tick=time.monotonic()
        r=subprocess.run([sys.executable,"-I",str(ROOT/"scripts/run_local.py"),*args],cwd=ROOT,
                         capture_output=True,encoding="utf-8",errors="replace",timeout=210)
        (folder/(name+".txt")).write_text(r.stdout+r.stderr,encoding="utf-8")
        passed=r.returncode==rc and all(t in r.stdout for t in tokens)
        trace_obj=None
        if trace and (folder/(name+".trace.json")).exists():
            trace_obj=json.loads((folder/(name+".trace.json")).read_text(encoding="utf-8"))
        if check:
            passed=passed and trace_obj is not None and check(trace_obj)
        result={"case":name,"command":["python","-I","scripts/run_local.py",*args],"cwd":str(ROOT),
                "interpreter":sys.executable,"exit_code":r.returncode,"expected_exit_code":rc,"passed":passed,
                "elapsed_s":time.monotonic()-tick,"stdout_file":name+".txt"}
        if trace_obj and "adapter" in trace_obj:
            result.update(adapter=trace_obj["adapter"],decision_attempts=len(trace_obj["events"]),
                          usage=trace_obj["usage"],financial_status=trace_obj["financial_status"],stop_reason=trace_obj["stop_reason"])
        runs.append(result)
        print(name,"PASS" if passed else "FAIL",r.returncode,flush=True)
    if a.phase=="minimal":
        run("B-manual",["fixed","--source","manual"],0,["440 304","507 689","+67 385","+15,30%","Источники обоих значений","#page=4"])
        run("partial-year",["fixed","--year","9 месяцев 2024"],1,["Уточните запрос"])
        run("synthetic",["scenario"],0,["ИСКУССТВЕННЫ"],True,
            lambda t:t["result"]["scenario"]["final_equity"]=="10098.00" and t["result"]["scenario"]["final_quantity"]==0 and t["model_calls"]==0)
        run("real-blocked",["scenario","--case","real-source"],0,["ТОРГОВЛИ НЕТ"],True,
            lambda t:t["result"]["status"]=="blocked" and t["result"]["reason_code"]=="publication_unknown" and t["result"]["ledger"]==[] and t["result"]["return_pct"] is None)
        run("C-mock-manual",["agent","--adapter","mock","--source","manual"],0,["C/mock","не языковая модель"],True,
            lambda t:t["adapter"]["kind"]=="deterministic_mock" and t["status"]=="completed")
        run("question-freeze",["questions"],0,["13 записей"])
        run("offline-replay",["replay","--run-dir","evaluation/step12_2026-11-09/run-02-environment-retry"],0,['"offline_replay_matches_saved": true'])
        run("search-source-missing",["fixed","--pdf","tmp/absent-primary.pdf"],2,["Локальный PDF не найден"])
    elif a.phase=="source":
        run("B-search",["fixed"],0,["440 304","507 689","+15,30%","#page=4","Аудиторское мнение с оговоркой"])
        run("B-historical",["fixed","--mode","historical","--as-of","2025-02-14T10:00:00+03:00"],0,["Ответ с числом не сформирован","дата подписи или получения файла не заменяет публикацию"])
        run("B-top1",["fixed","--results","1"],0,["нет обоих нужных доказательств","Ответ с числом не сформирован"])
        run("C-mock-search",["agent","--adapter","mock"],0,["C/mock"],True,lambda t:t["status"]=="completed" and t["financial_status"]=="answered")
    else:
        run("C-LLM-normal",["agent","--adapter","ollama"],0,["C/LLM","+15,30%"],True,
            lambda t:t["status"]=="completed" and t["financial_status"]=="answered" and t["adapter"]["kind"]=="local_llm" and len(t["events"])<=6)
    report={"phase":a.phase,"checked_at":datetime.now(timezone.utc).isoformat(),"root":str(ROOT),
            "python":sys.version,"interpreter":sys.executable,"isolated_child_python":True,"runs":runs,
            "passed":all(r["passed"] for r in runs),"scope":"Integration launch, not new model quality benchmark"}
    (folder/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 2


if __name__=="__main__":
    raise SystemExit(main())
