"""Reference preparation checks. No B/C answering run, no model benchmark."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from financial_assistant.question_set import PREFIX,read_json,validate_frozen


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def main():
    out,work=ROOT/"evaluation/step11_2026-11-09",ROOT/"tmp/step11-checks"
    work.mkdir(exist_ok=True)
    d,coverage,manifest=validate_frozen(ROOT)
    before={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in manifest["files"]}
    cli=[]
    cases=[("validate",[],0,"13 записей"),
           ("save_report",["--report",str(work/"coverage.json")],0,"оценка качества здесь не выполнялись"),
           ("reject_refreeze",["--freeze"],2,"Ошибка проверки"),
           ("protect_questions",["--report",str(ROOT/PREFIX/"questions.json")],2,"Ошибка проверки"),
           ("protect_source",["--report",str(ROOT/"data/examples/reference_bundle.json")],2,"Ошибка проверки"),
           ("protect_code",["--report",str(ROOT/"src/financial_assistant/contracts.py")],2,"Ошибка проверки"),
           ("wrong_extension",["--report",str(work/"report.txt")],2,"Ошибка проверки"),
           ("reject_exec_argument",["--execute","QA04"],2,"Ошибка проверки"),
           ("reject_model_argument",["--model","qwen3:4b"],2,"Ошибка проверки")]
    for name,args,expected,token in cases:
        r=subprocess.run([sys.executable,str(ROOT/"scripts/check_question_set.py"),*args],cwd=ROOT,capture_output=True,encoding="utf-8",timeout=15)
        passed=r.returncode==expected and token.casefold() in r.stdout.casefold()
        cli.append({"case":name,"exit_code":r.returncode,"expected_exit_code":expected,"passed":passed})
        assert passed,(name,r.returncode,r.stdout,r.stderr)
    after={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in before}
    assert after==before,"A validator/negative CLI test changed frozen inputs"
    assert read_json(work/"coverage.json")["quality_metrics"]=="not measured"
    with (out/"unit-tests.txt").open("w",encoding="utf-8") as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/"tests")))
    assert result.wasSuccessful(),"See unit-tests.txt"
    old=read_json(out/"before.json")["protected_sha256"]
    current={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in old}
    assert old==current,"Unexpected change to previous code/data"
    # No arbitrary answering commands generated from question text are executed.
    for c in d["cases"]:
        assert c["history"]["model_executed_after_freeze"] is False
    proof=read_json(out/"source-verification.json")
    pdf=ROOT/proof["pdf_relative_path"]
    source_state={"local_pdf_present":pdf.is_file(),"pdf_sha256":proof["pdf_sha256"],"fresh_visual_review_record":"source-verification.json"}
    if pdf.exists():
        assert hashlib.sha256(pdf.read_bytes()).hexdigest()==proof["pdf_sha256"]
        source_state["local_pdf_hash_matches"]=True
    report={"stage":11,"dataset_id":d["dataset_id"],"version":d["version"],"coverage":coverage,
            "unit_tests":{"run":result.testsRun,"successful":result.wasSuccessful()},"new_test_methods":33,"previous_test_methods":198,
            "validation_cli":cli,"all_frozen_files_unchanged_after_checks":after==before,"prototype_files_unchanged":current==old,
            "protected_existing_files":len(old),"protected_sha256":current,"frozen_manifest_sha256":hashlib.sha256((ROOT/PREFIX/"manifest.json").read_bytes()).hexdigest(),
            "source_verification":source_state,"independent_reference_check":"reference-checks.json",
            "question_set_prototype_answers_run":0,"question_set_model_calls":0,"reserved_model_runs":0,
            "quality_metrics":"not measured at step11","prior_regression_tests":"Full unit regression uses prior development fixtures; it does not execute this question set as a prototype evaluation.",
            "limitations":["One real PDF version/two actual revenue facts","Reserved questions visible to Codex; underlying data used in development","Only 3/10 financial templates currently supported by B/C; UI and simulation have separate denominators","Known C top1 call_limit retained as failure, not gold","No NLP adapter or free-text answer grader added"]}
    write(out/"report.json",report)
    write(out/"coverage.json",coverage)
    print(json.dumps({"questions":coverage["total"],"suites":coverage["by_suite"],"split":coverage["by_split"],"unit_tests":result.testsRun,"validation_CLI_passed":len(cli),"unchanged_existing_files":len(old),"question_set_model_calls":0,"question_set_prototype_answers":0},ensure_ascii=False))


if __name__=="__main__":
    main()
