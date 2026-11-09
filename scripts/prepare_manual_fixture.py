"""Recreate the explicitly manual annotation; this is not PDF extraction.

Do not run after a human has changed the fixture without reviewing the diff.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASH = "824f100d14396c26faacf80a03cca6b20d458c9b5d835201bc80068decb3d6e1"
PDF = "https://ar2024.phosagro.ru/pdf/ar/ru/additional-information_financial-statements.pdf"
RELEASE = "https://www.phosagro.ru/press/company/fosagro-publikuet-operatsionnye-i-finansovye-rezultaty-za-12-mesyatsev-2024-g/"


def annual(year):
    return {"kind": "duration", "start": f"{year}-01-01", "end": f"{year}-12-31"}


def review(method):
    return {"status": "assistant_checked", "method": method, "human_reviewer": None}


def build():
    version = "sha256:" + HASH
    doc = {
        "document_id": "phosagro-group-ifrs-2024-annual-extract-ru",
        "entity_id": "phosagro_group", "entity_name": "ПАО «ФосАгро» и дочерние общества",
        "consolidation": "group", "accounting_standard": "IFRS",
        "document_type": "financial_statements_extract_from_integrated_annual_report",
        "report_period": annual(2024),
        "source_page_url": "https://ar2024.phosagro.ru/additional-information/financial-statements",
        "document_url": PDF, "version_id": version, "sha256": HASH,
        "byte_length": 1521928, "pdf_pages": 23,
        "fetched_at": "2026-11-08T23:57:34+03:00", "approval_date": "2025-02-13",
        "publication": {"precision": "unknown", "value": None, "source_url": None,
                        "timezone": "Europe/Moscow", "version_binding": "unproven"},
        "related_release": {"url": RELEASE, "displayed_date": "2025-02-13", "binds_pdf_version": False},
        "rights": {"status": "unconfirmed", "public_copy_allowed": False,
                   "note": "Открыты просмотр и ссылка скачивания. Лицензия на повторную публикацию PDF, страниц и корпуса не установлена. В проекте только локальная исключённая копия и минимальная ручная разметка; не юридическое заключение.",
                   "checked_on": "2026-11-08"},
        "audit": {"opinion": "qualified", "limitation": "Нераскрытие информации о сегментах за 2024 и 2023 годы, требуемой IFRS 8; PDF-страница 1. Это не безоговорочное аудиторское мнение."},
        "review": review("Веб-извлечение PDF и локальный рендер Poppler; сверка с отдельным релизом эмитента. Это не независимая человеческая приёмка.")
    }
    evidence, facts = [], []
    for year, raw, value in [(2023, "440,304", "440304"), (2024, "507,689", "507689")]:
        ev_id = f"phosagro-revenue-{year}-p4"
        evidence.append({
            "evidence_id": ev_id, "document_id": doc["document_id"], "version_id": version,
            "document_sha256": HASH, "pdf_page": 4, "printed_page": "320",
            "statement_page": "1", "page_region": "left_half_of_spread",
            "table_title": "Консолидированный отчет о прибыли или убытке и прочем совокупном доходе за 2024 год",
            "row_label": "Выручка", "column_label": str(year), "period": annual(year),
            "currency": "RUB", "scale": 1000000, "unit_header": "Млн руб.",
            "raw_value": raw, "numeric_encoding": "comma_thousands_integer",
            "review": review("Ручная сверка строки, заголовков, валюты, масштаба и положительного знака на изображении PDF-страницы 4; релиз подтверждает числа с пробелом-разделителем.")
        })
        facts.append({
            "fact_id": f"phosagro-revenue-{year}", "evidence_id": ev_id,
            "entity_id": doc["entity_id"], "consolidation": "group", "accounting_standard": "IFRS",
            "metric_id": "revenue", "original_label": "Выручка", "value": value,
            "currency": "RUB", "scale": 1000000, "period": annual(year), "version_id": version,
            "review": review("Перенесено вручную из проверенной ячейки; значение 2023 — сравнительный столбец версии отчёта 2024, а не исходный отчёт 2023.")
        })
    return {
        "schema_version": "0.1", "document": doc, "evidence": evidence, "facts": facts,
        "request": {
            "request_id": "first-revenue-growth", "question": "Как изменилась выручка группы «ФосАгро» по МСФО за 2024 год по сравнению с 2023 годом по выбранной версии отчётности? Укажи оба значения, изменение в млн рублей, процент и страницу.",
            "entity_id": doc["entity_id"], "consolidation": "group", "accounting_standard": "IFRS",
            "metric_id": "revenue", "current_period": annual(2024), "previous_period": annual(2023),
            "mode": "document_snapshot", "as_of": None, "formula_id": "annual_growth_v1"
        },
        "scenario": {"rule_id": "educational_revenue_threshold", "rule_version": "draft-1",
                     "condition": "growth_pct_gt", "threshold_pct": "10", "data_mode": "synthetic_only",
                     "signal_at": None, "calendar_id": None, "price_snapshot_id": None, "execution_at": None}
    }


if __name__ == "__main__":
    target = ROOT / "data/examples/reference_bundle.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
