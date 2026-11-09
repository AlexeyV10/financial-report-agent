"""Known local entry points, including isolated Python (-I); no arbitrary commands."""
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
ENTRIES={"fixed":("assistant.py",[]),"agent":("agent_assistant.py",[]),
         "scenario":("simulate_scenario.py",[]),"questions":("check_question_set.py",[]),
         "replay":("measure_step12.py",["replay"])}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv)<2 or sys.argv[1] not in ENTRIES:
        print("Выберите локальный режим: fixed, agent, scenario, questions, replay.")
        return 2
    script,prefix=ENTRIES[sys.argv[1]]
    # Isolated Python omits the implicit sibling path. Use only packaged directories.
    sys.path[:0]=[str(ROOT/"scripts"),str(ROOT/"src")]
    sys.argv=[str(ROOT/"scripts"/script),*prefix,*sys.argv[2:]]
    runpy.run_path(sys.argv[0],run_name="__main__")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
