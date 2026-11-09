"""Russian presentation only; recomputation validates before displaying a saved result."""
from .simulation import LABEL, assess_real_source, fingerprint, need, validate_scenario_result
from .user_path import number

REASONS = {
    "publication_unknown": "Не подтверждена публикация именно этой версии источника. Сигнал и сделки запрещены.",
    "not_yet_available": "На момент решения версия ещё не доступна. Будущий факт использовать нельзя.",
    "missing_price": "Нет точной цены в обязательный момент календаря. Другая цена не подставляется.",
    "insufficient_cash": "Для заданного размера и комиссии недостаточно денег. Отрицательный остаток запрещён.",
    "zero_lot": "Лимита доли недостаточно даже для одного целого лота. Сделка не создаётся.",
    "no_eligible_session": "После решения нет разрешённого открытия сессии до конца окна.",
    "real_simulation_not_supported": "Допуск реального торгового сценария не реализован; искусственные цены к настоящему отчёту не присоединяются.",
    "real_synthetic_mixing_forbidden": "Настоящие факты нельзя подставить в искусственный набор с вымышленными датами/ценами.",
    "unverified_candidate": "Факт остаётся неподтверждённым кандидатом; числовой сигнал запрещён.",
    "value_missing": "Отсутствует финансовое значение; отсутствие не заменяется нулём.",
    "incompatible_units": "Валюты или масштабы финансовых значений несовместимы.",
    "nonpositive_base": "Неположительная база не допускает обычного расчёта роста по принятой методике.",
}
EVENTS = {"initial": "Начало", "signal_true": "Условие выполнено", "signal_false": "Условие не выполнено",
          "buy": "Виртуальная покупка", "sell": "Виртуальная продажа", "mark": "Оценка", "benchmark_entry_scheduled": "Вход сравнения", "cash_reference": "Денежное сравнение"}


def render_scenario(s, r):
    validate_scenario_result(r, s)
    lines = [LABEL, "Все компания, факты, даты, календарь и цены в этом наборе вымышлены."]
    if r["status"] != "completed":
        lines += ["Сценарий не исполнен: " + r["reason_code"], REASONS.get(r["reason_code"], "Входные данные не прошли проверку. Исправьте формат, параметры, календарь и связанные версии."),
                  "Виртуальные сделки и итоговая доходность не сформированы."]
        return "\n".join(lines) + "\n"
    p, rule, main = s["portfolio"], s["rule"], r["scenario"]
    fin = r["financial_result"]
    calc = fin["answer"]["calculation"]
    lines += ["", "Правило " + rule["rule_id"] + "/" + rule["version"] + ": рост выручки строго выше " + number(rule["threshold_pct"]) + "% → одна покупка, затем продажа в конце окна.",
              "Синтетический рост из прежнего калькулятора: " + number(calc["growth_pct_display"]) + "%.",
              "Капитал: " + number(p["initial_cash"]) + " RUB; лимит номинала как доля капитала: " + p["max_notional_fraction"] + "; комиссия сверх лимита доли.",
              "Комиссия каждой операции: " + number(p["fee_fixed"]) + " RUB; проскальзывание: " + number(p["slippage_bps"]) + " б.п.; лот: " + str(p["lot_size"]) + ".",
              "Версия финансового источника (собственная вымышленная таблица): " + s["financial_bundle"]["document"]["version_id"],
              "Публикация в вымышленном примере: " + str(r["eligibility"]["publication_available_from"]),
              "Решение: " + s["decision_at"], "Исполнение: первое открытие строго после решения; закрытие — последнее закрытие окна.",
              "Синтетическое окно: " + s["window"]["start"] + " — " + s["window"]["end"],
              "Календарь/цены: " + s["calendar"]["calendar_id"] + " / " + s["prices"]["snapshot_id"], "", "Журнал виртуального сценария:",
              "Время | Событие | Кол-во операции | Цена/исполнение | Номинал | Комиссия | Проскальзывание RUB | Деньги RUB | Позиция | Стоимость RUB"]
    for e in main["ledger"]:
        raw, effective = e["raw_price"], e["execution_price"]
        price = ("—" if raw is None else number(raw)) + "/" + ("—" if effective is None else number(effective))
        lines.append(" | ".join([e["at"], EVENTS[e["event"]], str(e["traded_quantity"]), price, number(e["notional"]), number(e["fee"]), number(e["slippage_cost"]), number(e["cash"]), str(e["quantity"]), number(e["equity"])]))
    lines += ["", "Итог: " + number(main["final_equity"]) + " RUB; позиция " + str(main["final_quantity"]) + "; изменение " + number(main["pnl"], True) + " RUB (" + number(main["return_pct"], True) + "%).",
              "Комиссии всего: " + number(main["fees"]) + " RUB; оценка проскальзывания: " + number(main["slippage_cost"]) + " RUB (уже в цене, повторно не вычитается).", "", "Сравнение на том же окне, с теми же ценами, долей и расходами:"]
    for key, label in (("cash_no_interest", "Деньги без процента"), ("buy_and_hold_same_allocation", "Удержание той же доли с первого допустимого открытия")):
        c = r["comparisons"][key]
        lines.append(label + ": " + number(c["final_equity"]) + " RUB; " + number(c["return_pct"], True) + "%.")
    lines += ["", "Проверяется арифметика и время виртуального сценария. Рыночная доходность, ликвидность и качество стратегии не измеряются.",
              "Дивиденды/сплиты и реальные корпоративные события не поддерживаются. Торговля и инвестиционная рекомендация отсутствуют."]
    return "\n".join(lines) + "\n"


def render_real_check(bundle, decision_at, result):
    need(fingerprint(result) == fingerprint(assess_real_source(bundle, decision_at)), "tampered_scenario_result")
    return "\n".join([result["label"], "Источник: " + bundle["document"]["entity_name"],
                      "Версия: " + result["document_version"], "Момент решения: " + decision_at,
                      "Допуск заблокирован: " + result["reason_code"],
                      REASONS.get(result["reason_code"], "Нет допустимого финансового результата для сценария."),
                      "Вымышленные цены и даты к настоящему отчёту не присоединялись. Сделок и показателя доходности нет."]) + "\n"
