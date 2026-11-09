"""Validate/freeze references only. Never runs B/C, simulate(), or a language model."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from assistant import ArgumentIssue,Parser
from agent_assistant import output_path
from financial_assistant.question_set import PREFIX,QuestionSetError,digest,read_json,validate_dataset,validate_frozen


def freeze():
    folder=ROOT/PREFIX
    if (folder/"manifest.json").exists():
        raise QuestionSetError("Frozen set exists; no overwrite. Create/review a new version for changes.")
    d=read_json(folder/"questions.json");validate_dataset(d,ROOT)
    lines=["# Реестр проверочных вопросов КП2 v1", "", "Эталоны подготовлены; ответы модели на этот набор не измерены. Резерв не является слепым тестом. Полные контексты/локаторы/единицы — questions.json.", "", "| ID | Группа | Split | Вопрос | Эталонный исход | B/C |", "|---|---|---|---|---|---|"]
    for c in d["cases"]:
        e=c["expected"];values="; ".join(o["measure"]+"="+o["value"]+(" "+o["currency"] if o["currency"] else "%") for o in e["outputs"])
        lines.append("| "+" | ".join([c["case_id"],c["suite"]+" / "+c["origin"],c["split"],c["question"].replace("|","/"),e["layer"]+":"+e["status"]+"/"+e["reason_code"]+("; "+values if values else ""),c["capability"]["B"]])+" |")
    lines += ["", "Числа выше читаются только вместе с валютой/масштабом/периодом/источником в JSON. Для QA04 масштаб — млрд RUB; для остальных реальных денежных QA — млн RUB. Сценарные деньги — RUB. QA07 ожидает финансовый missing; прежний call_limit агента сохранён как неуспех, не эталон."]
    (folder/"REGISTER.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    files={str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}
    for a in d["assets"]:files[a["path"]]=a["sha256"]
    for name in ("source-verification.json","reference-checks.json"):
        path="evaluation/step11_2026-11-09/"+name;files[path]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    before=read_json(ROOT/"evaluation/step11_2026-11-09/before.json")["protected_sha256"]
    m={"freeze_schema_version":"0.1","dataset_id":d["dataset_id"],"version":d["version"],"frozen_at":datetime.now(timezone.utc).isoformat(),
       "dataset_canonical_sha256":digest(d),"files":files,"reserved_ids":["QA04","QA05","QA08","SC02"],"prototype_source_sha256":before,
       "scope":"New formulations on known data, visible to Codex; not blind/independent. No model/prototype answering runs for this set at freeze."}
    validate_frozen(ROOT, m)
    with (folder/"manifest.json").open("x",encoding="utf-8") as file:
        file.write(json.dumps(m,ensure_ascii=False,indent=2)+"\n")


def main(argv=None):
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    parser=Parser(description=__doc__)
    parser.add_argument("--freeze",action="store_true",help="однократно зафиксировать проверенный набор; без перезаписи")
    parser.add_argument("--report",type=Path,help="минимальный .json под output/ или tmp/")
    try:
        args=parser.parse_args(argv)
        target=output_path(args.report,".json") if args.report else None
        if args.freeze:freeze()
        d,summary,m=validate_frozen(ROOT)
        if target:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps({"dataset_id":d["dataset_id"],"version":d["version"],"freeze_sha256":hashlib.sha256((ROOT/PREFIX/"manifest.json").read_bytes()).hexdigest(),"coverage":summary,"quality_metrics":"not measured"},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(f"Проверен набор эталонов {d['dataset_id']} / {d['version']}: {summary['total']} записей.")
        print("10 финансовых QA, 1 интерфейсное уточнение и 2 искусственных сценария; группы не смешиваются в метриках.")
        print("9 dev/open, 4 в резерве; резерв виден Codex и не является слепым тестом.")
        print("B/C поддерживают 3/10 финансовых шаблонов и отдельно интерфейсный случай. У 5 задач требуется новый адаптер; 2 синтетические QA доступны финансовому API, 2 сценария — отдельному симулятору.")
        print("Запуски прототипа/модели на этом наборе и оценка качества здесь не выполнялись.")
        return 0
    except (QuestionSetError,ArgumentIssue,OSError,TypeError,ValueError,KeyError):
        print("Ошибка проверки набора, фиксации версии или пути отчёта. Замороженные файлы не заменены; оценка модели не выполнялась. См. docs/question_set.md.")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
