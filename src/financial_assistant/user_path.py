"""A bounded user scenario over the existing tools; no natural-language model."""
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
import re
import unicodedata

from .contracts import ContractError, instant, validate_bundle
from .finance import calculate_from_retrieval, calculate_metric, tool_request, validate_financial_result
from .retrieval import RetrievalError, search_index


@dataclass(frozen=True)
class UserQuery:
    company: str = "ФосАгро"
    standard: str = "МСФО"
    metric: str = "выручка"
    year: str = "2024"
    compare: str = "2023"
    scope: str = "группа"
    mode: str = "snapshot"
    as_of: str | None = None
    source: str = "search"


def clean(value):
    return "".join(c if c.isprintable() else " " for c in str(value))[:300]


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().replace("ё", "е").split())


def question(q):
    return (f"Как изменилась {clean(q.metric)} ({clean(q.company)}, {clean(q.scope)}, "
            f"{clean(q.standard)}) за {clean(q.year)} год по сравнению с {clean(q.compare)} годом?")


def input_issue(q):
    fields = (q.company, q.standard, q.metric, q.year, q.compare, q.scope, q.mode, q.source)
    if any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in fields):
        return "incomplete_request", "Укажите компанию, группу, стандарт, показатель и оба полных года. Пустые поля не заменяются значениями примера."
    if norm(q.company) not in {"фосагро", "группа фосагро"}:
        return "company_not_supported", "Выберите одну компанию. Сейчас подготовлен только сценарий группы «ФосАгро»; другая или неоднозначная компания не подставляется автоматически."
    if norm(q.scope) not in {"группа", "group", "консолидированная группа"}:
        return "scope_not_supported", "Этот сценарий относится к консолидированной группе, а не к отдельному юридическому лицу. Укажите --scope группа."
    if norm(q.standard) not in {"мсфо", "ifrs"}:
        return "standard_not_supported", "В этом сценарии поддерживается только МСФО. Отчёт по РСБУ требует другого источника."
    if norm(q.metric) not in {"выручка", "revenue"}:
        return "metric_not_supported", "Сейчас поддерживается годовое изменение выручки. Для другого показателя нужен отдельный проверенный сценарий."
    if not all(re.fullmatch(r"20\d{2}", y) for y in (q.year, q.compare)):
        return "period_needs_clarification", "Укажите два полных года четырьмя цифрами. Квартал или девять месяцев нельзя считать полным годом."
    if (q.year, q.compare) != ("2024", "2023"):
        return "period_not_supported", "Сейчас подготовлено сравнение полного 2024 года с полным 2023 годом. Другой период или обратный порядок требуют отдельного сценария."
    if q.source not in {"search", "manual"}:
        return "source_needs_clarification", "Выберите источник: --source search (локальный поиск) или --source manual (прежний ручной реестр)."
    if q.mode not in {"snapshot", "historical"}:
        return "mode_needs_clarification", "Выберите --mode snapshot для выбранной версии либо --mode historical для анализа на определённый момент."
    if q.mode == "historical":
        if not q.as_of:
            return "as_of_required", "Для исторического режима укажите --as-of с датой, временем и часовым поясом, например 2025-02-14T10:00:00+03:00."
        try:
            instant(q.as_of)
        except ContractError:
            return "as_of_invalid", "Момент анализа должен содержать дату, время и часовой пояс, например 2025-02-14T10:00:00+03:00."
    elif q.as_of is not None:
        return "as_of_requires_historical", "Вы указали момент анализа. Выберите --mode historical; программа не будет игнорировать дату или менять режим молча."
    return None


def header(q):
    lines = ["Учебный анализ отчётности — ограниченный сценарий", "Вопрос: " + question(q)]
    if q.mode == "snapshot":
        lines.append("Режим: анализ выбранной версии отчётности; её доступность в прошлом не утверждается.")
    elif q.mode == "historical":
        lines.append("Режим: исторический анализ. Момент: " + (clean(q.as_of) if q.as_of else "не указан"))
    if q.source in {"search", "manual"}:
        lines.append("Источник данных: " + ("локальный поиск и прежний проверенный реестр фактов." if q.source == "search"
                                              else "прежний ручной реестр фактов; текущая проверка PDF и поиск не выполняются."))
    return lines


def number(value, signed=False):
    """Presentation only: no new arithmetic, conversion, division or rounding."""
    n = Decimal(value)
    shown = format(n, ",f").replace(",", " ").replace(".", ",")
    return ("+" if signed and n > 0 else "") + shown


def unit(currency, scale):
    currency_name = {"RUB": "руб.", "USD": "долл. США"}[currency]
    return {1: "", 1000: "тыс. ", 1000000: "млн ", 1000000000: "млрд "}[scale] + currency_name


def date_ru(value):
    year, month, day = value.split("-")
    return f"{day}.{month}.{year}"


WARNING_TEXT = {
    "manual_annotation": "Финансовые факты подготовлены вручную; автоматического подтверждения новых чисел нет.",
    "source_checked_by_assistant": "Реестр подготовлен ассистентом; проверка пользователем не заявляется.",
    "rights_for_public_copy_unconfirmed": "Право распространять копию отчёта и его страницы не подтверждено; используйте ссылки на сайт источника.",
    "auditor_qualified_opinion_segment_disclosure": "Аудиторское мнение с оговоркой: не раскрыта требуемая информация о сегментах. Здесь сравнивается только общая выручка.",
    "snapshot_only_publication_unknown": "Дата первой публикации именно этой PDF-версии неизвестна; историческая доступность не подтверждена.",
    "source_rounding_limits_precision": "Результат рассчитан по округлённым опубликованным суммам; дополнительные внутренние знаки не повышают точность отчёта.",
    "retrieval_only_locates_prior_verified_facts": "Поиск находит место прежних доказательств; текст кандидатов не становится новым подтверждённым фактом.",
}
REASON_TEXT = {
    "publication_unknown": "Не подтверждено, когда именно эта версия PDF стала доступна. Исторический ответ с числом сформировать нельзя; дата подписи или получения файла не заменяет публикацию.",
    "not_yet_available": "По принятому правилу документ ещё не был доступен на выбранный момент. Позднюю версию нельзя использовать для прежнего решения.",
    "value_missing": "В проверенном реестре отсутствует одно из двух необходимых значений. Отсутствие не считается нулём.",
    "unverified_candidate": "Одно из значений или его доказательство ещё не проверено. Поисковый кандидат не заменяет подтверждённый факт.",
    "document_unchecked": "Документ ещё не прошёл проверку, необходимую для числового ответа.",
    "duplicate_candidates": "Для одного входа есть несколько фактов. Требуется устранить неоднозначность источников; удобное число автоматически не выбирается.",
    "incompatible_periods": "Периоды несопоставимы для этой формулы: нужны два последовательных полных календарных года.",
    "incompatible_units": "Валюта или масштаб двух значений различаются. Автоматическая конвертация в этом сценарии не поддерживается.",
    "entity_or_standard_mismatch": "Запрос и документ относятся к разным границам организации или стандартам отчётности.",
    "nonpositive_base": "Процентное изменение по этой методике требует положительного предыдущего значения. При нулевой или отрицательной базе расчёт обычного роста не выполняется.",
    "unsupported_operation": "Операция выходит за поддержанную методику годового изменения выручки.",
    "verified_evidence_not_retrieved": "В найденных фрагментах нет обоих нужных доказательств. Попробуйте --results 5 и проверьте источник. Прямой расчёт вместо поиска автоматически не включается.",
    "retrieval_context_missing": "Поиск не предоставил контекст для обоих необходимых фактов. Число по реестру вместо поиска автоматически не подставляется.",
    "retrieval_duplicate_conflict": "В выдаче есть противоречивые копии фрагмента. Требуется проверить источник или индекс.",
    "input_fact_context_mismatch": "Выбранные факты не соответствуют показателю или порядку периодов запроса.",
    "input_fact_selection_mismatch": "Набор выбранных фактов расходится с запросом; автоматическая подмена запрещена.",
}
ERROR_TEXT = {
    "source_missing": "Локальный PDF не найден. Укажите существующий файл через --pdf; подготовка источника описана в docs/retrieval.md.",
    "source_version_mismatch": "Хеш PDF отличается от выбранной версии. Проверьте файл; подмена источника не допускается.",
    "source_too_large": "Размер PDF превышает предел учебного прототипа.",
    "index_missing": "Локальный поисковый индекс не найден. Постройте его по инструкции docs/retrieval.md или укажите существующий через --db.",
    "index_version_mismatch": "Индекс относится к другим метаданным или версии документа. Нужен согласованный источник и индекс.",
    "index_invalid": "Индекс повреждён или имеет неподходящий формат. Используйте новый согласованный снимок по инструкции docs/retrieval.md.",
    "invalid_top_k": "Число результатов должно быть от 1 до 10; укажите --results 5 для обычного сценария.",
    "registry_missing": "Файл реестра фактов не найден. Проверьте рабочую папку или путь --bundle.",
    "registry_invalid": "Реестр или результат не прошёл проверку формата и связей. Требуется исправить данные; числовой ответ не сформирован.",
    "configuration_mismatch": "Выбранный реестр не соответствует этому ограниченному сценарию. Другой набор данных не подставляется молча.",
    "save_failed": "Не удалось сохранить ответ. Используйте файл .txt внутри output/ или tmp/ и проверьте доступ к папке.",
    "invalid_arguments": "Параметры запуска не распознаны. Посмотрите python scripts/assistant.py --help.",
}


def warning_lines(result):
    lines = ["Ограничения:"]
    for warning in dict.fromkeys(result["warnings"]):
        lines.append("- " + WARNING_TEXT.get(warning, "Дополнительное ограничение инструмента: " + clean(warning)))
    lines.append("- Искусственный сценарий запускается отдельно; этот финансовый ответ не разрешает торговлю. Результат не является инвестиционной рекомендацией.")
    return lines


def render_financial(q, bundle, request, result, retrieval=None):
    validate_financial_result(result, bundle, request, retrieval)
    lines = header(q)
    if result["status"] != "answered":
        label = {"missing": "Недостаточно подтверждённых данных", "conflict": "Обнаружена несовместимость", "unsupported": "Методика не поддерживается"}[result["status"]]
        lines += ["", label + ".", REASON_TEXT.get(result["reason_code"], clean(result["message"])),
                  "Ответ с числом не сформирован.", "", *warning_lines(result)]
        return "\n".join(lines) + "\n"
    calc = result["answer"]["calculation"]
    previous, current = result["inputs"]
    lines += ["", "Ответ по выбранной версии отчётности", result["entity_name"] + "; МСФО; выручка."]
    for f in (previous, current):
        span = date_ru(f["period"]["start"]) + "–" + date_ru(f["period"]["end"])
        lines.append(span + ": " + number(f["value"]) + " " + unit(f["currency"], f["scale"]))
    lines += ["Изменение: " + number(calc["delta"], True) + " " + unit(calc["delta_currency"], calc["delta_scale"])
              + "; " + number(calc["growth_pct_display"], True) + "%.",
              "Формула: (текущее / предыдущее − 1) × 100%.",
              "Подстановка: (" + number(current["value"]) + " / " + number(previous["value"]) + " − 1) × 100% = " + number(calc["growth_pct_display"], True) + "%.",
              "Округление: до двух знаков, половина округляется вверх по модулю (ROUND_HALF_UP).", "", "Источники обоих значений:"]
    for source in result["sources"]:
        side = {"left_half_of_spread": "левая половина разворота", "right_half_of_spread": "правая половина разворота"}.get(source["page_region"], clean(source["page_region"]))
        lines += [f"- Столбец {source['column_label']}; PDF-страница {source['pdf_page']}, печатная {source['printed_page']}, страница формы {source['statement_page']}; {side}.",
                  "  Таблица: " + source["table_title"] + ". Строка: «" + source["row_label"] + "»; единица: " + source["unit_header"],
                  "  " + source["url"]]
    lines += ["Версия документа: " + result["answer"]["document_version"], "", *warning_lines(result)]
    return "\n".join(lines) + "\n"


def response(q, status, code, message):
    title = "Уточните запрос" if status == "clarification" else "Техническая ошибка"
    lines = header(q) + ["", title + ".", message]
    if status == "error":
        lines.append("Это сбой подготовки или проверки данных, а не вывод об отсутствии показателя в отчётности.")
    return {"user_path_schema_version": "0.1", "query": asdict(q), "status": status,
            "reason_code": code, "text": "\n".join(lines) + "\n", "financial_result": None}


def technical_response(q, code):
    return response(q, "error", code, ERROR_TEXT.get(code, "Не удалось проверить локальные данные. Проверьте реестр, исходный PDF и индекс; расчёт не завершён."))


def run_user_query(q, bundle, pdf=None, db=None, top_k=5):
    issue = input_issue(q)
    if issue:
        return response(q, "clarification", *issue)
    try:
        validate_bundle(bundle)
        expected = bundle["request"]
        if (bundle["document"]["entity_id"] != "phosagro_group" or expected["entity_id"] != "phosagro_group"
                or expected["metric_id"] != "revenue" or expected["accounting_standard"] != "IFRS"
                or expected["consolidation"] != "group" or expected["previous_period"]["end"][:4] != q.compare
                or expected["current_period"]["end"][:4] != q.year):
            return technical_response(q, "configuration_mismatch")
        selections = []
        for key in ("previous_period", "current_period"):
            matches = [f for f in bundle["facts"] if f["period"] == expected[key] and f["metric_id"] == expected["metric_id"]]
            if len(matches) != 1:
                code = "duplicate_candidates" if matches else "value_missing"
                # No arbitrary first fact and no fabricated IDs to call the tool.
                title = "Обнаружена неоднозначность." if matches else "Недостаточно подтверждённых данных."
                return {"user_path_schema_version": "0.1", "query": asdict(q), "status": "conflict" if matches else "missing",
                        "reason_code": code, "text": "\n".join(header(q) + ["", title, REASON_TEXT[code], "Ответ с числом не сформирован."]) + "\n", "financial_result": None}
            selections.append(matches[0]["fact_id"])
        request = tool_request(*selections, mode="historical_as_of" if q.mode == "historical" else "document_snapshot", as_of=q.as_of)
        retrieval = None
        if q.source == "search":
            retrieval = search_index(db or Path("tmp/retrieval/document.sqlite"), pdf or Path("tmp/pdfs/phosagro-2024-ru.pdf"), bundle,
                                     f"выручка {q.year} {q.compare}", entity_id=expected["entity_id"],
                                     version_id=bundle["document"]["version_id"], top_k=top_k, mode=request["mode"], as_of=request["as_of"])
            result = calculate_from_retrieval(bundle, request, retrieval)
        else:
            result = calculate_metric(bundle, request)
        rendered = render_financial(q, bundle, request, result, retrieval)
        return {"user_path_schema_version": "0.1", "query": asdict(q), "status": result["status"],
                "reason_code": result["reason_code"], "text": rendered, "financial_result": result}
    except RetrievalError as exc:
        return technical_response(q, exc.code)
    except (ContractError, KeyError, TypeError, ValueError):
        return technical_response(q, "registry_invalid")
    except OSError:
        return technical_response(q, "local_io_error")
