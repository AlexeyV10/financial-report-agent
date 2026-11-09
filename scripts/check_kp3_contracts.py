"""Show v0.2 input bindings only; this is not a financial answering service."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from financial_assistant.contracts_v2 import read_json
from financial_assistant.legacy_adapter import catalog_from_v01, task_from_v01
from financial_assistant.tasks import bind_task


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    legacy = read_json(ROOT / "data/examples/reference_bundle.json")
    catalog, task = catalog_from_v01(legacy), task_from_v01(legacy)
    rows = [{"origin": "legacy assistant_checked registry; no new PDF check", **bind_task(catalog, task)}]
    task.update(mode="historical", as_of="2025-02-14T10:00:00+03:00")
    rows.append({"origin": "legacy historical gate", **bind_task(catalog, task)})
    artificial = read_json(ROOT / "data/catalogs/kp3_v02/synthetic_catalog.json")
    rows.extend({"origin": "SYNTHETIC ONLY, not issuer data", **bind_task(artificial, t)}
                for t in read_json(ROOT / "data/tasks/kp3_v02/examples.json"))
    print(json.dumps({"schema_version": "0.2", "stage": "contract_binding_only", "model_calls": 0,
                      "financial_calculations": 0, "cases": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
