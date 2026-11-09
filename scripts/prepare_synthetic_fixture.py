"""Author a separate fictional fixture from scratch. Never reads the issuer bundle."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_fixture():
    source = "SELF-CREATED SYNTHETIC TABLE; NOT A PDF OR ISSUER REPORT\n2023|revenue|100|RUB|1000000\n2024|revenue|120|RUB|1000000\n"
    sha = hashlib.sha256(source.encode()).hexdigest()
    version = "sha256:" + sha
    url = "https://example.invalid/synthetic/revenue-v1"
    review = {"status": "assistant_checked", "method": "Self-created fictional table; technical consistency only, no issuer PDF or human review.", "human_reviewer": None}
    doc = {"document_id": "synthetic-revenue-document-v1", "entity_id": "synthetic_example_group", "entity_name": "Вымышленная группа «Учебный пример»",
           "consolidation": "group", "accounting_standard": "IFRS", "document_type": "synthetic_contract_fixture_not_a_pdf",
           "report_period": {"kind": "duration", "start": "2024-01-01", "end": "2024-12-31"}, "source_page_url": url, "document_url": url,
           "version_id": version, "sha256": sha, "byte_length": len(source.encode()), "pdf_pages": 1,
           "fetched_at": datetime.now(timezone.utc).isoformat(), "approval_date": "2025-06-04",
           "publication": {"precision": "timestamp", "value": "2025-06-04T19:00:00+03:00", "timezone": "Europe/Moscow", "version_binding": "document_version", "source_url": url},
           "related_release": {"url": url, "displayed_date": "2025-06-04", "binds_pdf_version": False},
           "rights": {"status": "confirmed", "public_copy_allowed": True, "note": "Own synthetic text, not third-party reporting. Compatibility PDF/page fields denote a virtual table, not a downloaded PDF.", "checked_on": "2026-11-09"},
           "audit": {"opinion": "not_applicable_synthetic", "limitation": "Fictional fixture, no auditor opinion."}, "review": deepcopy(review)}
    facts, evidence = [], []
    for year, value in ((2023, "100"), (2024, "120")):
        span = {"kind": "duration", "start": f"{year}-01-01", "end": f"{year}-12-31"}
        fid, eid = f"synthetic-revenue-{year}", f"synthetic-revenue-{year}-table1"
        evidence.append({"evidence_id": eid, "document_id": doc["document_id"], "version_id": version, "document_sha256": sha,
            "pdf_page": 1, "printed_page": "synthetic-table-1", "statement_page": "virtual-1", "page_region": "synthetic_table_not_pdf",
            "table_title": "Вымышленная таблица для проверки кода", "row_label": "Синтетическая выручка", "column_label": str(year),
            "period": deepcopy(span), "currency": "RUB", "scale": 1000000, "unit_header": "Условные млн RUB",
            "raw_value": value, "numeric_encoding": "comma_thousands_integer", "review": deepcopy(review)})
        facts.append({"fact_id": fid, "evidence_id": eid, "entity_id": doc["entity_id"], "consolidation": "group", "accounting_standard": "IFRS", "metric_id": "revenue",
            "original_label": "Синтетическая выручка", "value": value, "currency": "RUB", "scale": 1000000,
            "period": deepcopy(span), "version_id": version, "review": deepcopy(review)})
    bundle = {"schema_version": "0.1", "document": doc, "evidence": evidence, "facts": facts,
              "request": {"request_id": "synthetic-growth-v1", "question": "Искусственная выручка: 2024 к 2023", "entity_id": doc["entity_id"], "consolidation": "group", "accounting_standard": "IFRS", "metric_id": "revenue",
                          "current_period": deepcopy(facts[1]["period"]), "previous_period": deepcopy(facts[0]["period"]), "mode": "document_snapshot", "as_of": None, "formula_id": "annual_growth_v1"},
              "scenario": {"rule_id": "legacy-synthetic-placeholder", "rule_version": "draft-1", "condition": "growth_pct_gt", "threshold_pct": "10", "data_mode": "synthetic_only", "signal_at": None, "calendar_id": None, "price_snapshot_id": None, "execution_at": None}}
    sessions, observations = [], []
    for date, opening, closing in (("2025-06-04", "99", "99"), ("2025-06-05", "100", "101"), ("2025-06-06", "102", "98"), ("2025-06-09", "103", "105")):
        opened, closed = date + "T10:00:00+03:00", date + "T18:00:00+03:00"
        sessions.append({"open": opened, "close": closed})
        observations.extend(({"at": opened, "price": opening}, {"at": closed, "price": closing}))
    return {"scenario_schema_version": "0.1", "scenario_id": "synthetic-revenue-scenario-v1", "data_mode": "synthetic_only",
            "provenance": {"kind": "self_created_synthetic", "label": "ИСКУССТВЕННЫЕ ДАННЫЕ / ВИРТУАЛЬНЫЙ СЦЕНАРИЙ", "source_text": source,
                           "note": "All entities, values, publication/approval/release dates, sessions and prices are fictional. fetched_at records capture of this authored text; no report was downloaded. Page fields are legacy compatibility only."},
            "financial_bundle": bundle, "inputs": {"previous_fact_id": facts[0]["fact_id"], "current_fact_id": facts[1]["fact_id"], "operation_id": "annual_growth_v1"},
            "decision_at": "2025-06-04T19:30:00+03:00",
            "rule": {"rule_id": "synthetic-revenue-threshold", "version": "1", "condition": "growth_pct_gt", "threshold_pct": "10", "execution_policy": "next_session_open", "close_policy": "window_last_close"},
            "portfolio": {"currency": "RUB", "initial_cash": "10000", "max_notional_fraction": "0.20", "lot_size": 1, "fee_fixed": "1", "slippage_bps": "0"},
            "instrument": {"instrument_id": "SYNTH_ASSET", "currency": "RUB", "corporate_actions": "none_in_fixture"},
            "window": {"start": sessions[0]["open"], "end": sessions[-1]["close"]},
            "calendar": {"calendar_id": "synthetic-sessions-v1", "timezone": "Europe/Moscow", "synthetic": True, "sessions": sessions},
            "prices": {"snapshot_id": "synthetic-prices-v1", "synthetic": True, "instrument_id": "SYNTH_ASSET", "currency": "RUB", "observations": observations}}


if __name__ == "__main__":
    path = ROOT / "data/synthetic/scenario_v1.json"
    if path.exists():
        raise SystemExit("Fixture already exists; preserve it rather than silently regenerating versions/timestamps.")
    path.parent.mkdir(parents=True, exist_ok=True)
    fixture = make_fixture()
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"frozen_before_first_execution": True, "purpose": "Parameters fixed for code checks, no performance optimisation", "fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rule": fixture["rule"], "portfolio": fixture["portfolio"]}
    path.with_name("frozen_rule_v1.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Authored separate synthetic fixture and frozen rule manifest.")
