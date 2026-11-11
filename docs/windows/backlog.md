# Backlog Windows-приложения — версия1.0

61 задача: WIN-00 — завершённое исследование, WIN-01 — завершённый feasibility с ограничениями; WIN-02 — host validated, clean VM pending; WIN-03–60 — предлагаемые работы, ещё не выполненные. Это не список уже реализованных возможностей. Зависимости образуют DAG; security/evaluation/accessibility начинаются рано, CROSS-задачи завершают их проверку. Оценка готовности опирается на артефакт и наблюдаемое поведение, а не наличие JSON или красивого экрана.

При каждом этапе: свежий fetch/main/PR; отдельная codex/ветка и worktree; сохранить исходные байты; allowlist commits/push/PR/technical tag; merge только по поручению. Новые факты/метрики/модели требуют собственной версии/проверок. Неприкосновенность старых gold/manifests и права на данные сохраняются.

[Основной план](../../ПЛАН_РАЗВИТИЯ_WINDOWS.md) · [JSON](roadmap.json) · [Возобновить WIN-02B после готовности guest](../../prompts/windows_02b_resume_when_guest_ready.md)

## WIN-00. Зафиксировать исследование и продуктовые границы

Выпуск: RESEARCH. Зависимости: нет. Состояние: research_complete.

**Результат:** Исследование классов продуктов, документов, native architectures, локального AI и прогнозов; отдельный Windows-план и продолжение.

**Готовность и отрицательные проверки:** Решения пользователя сохранены; текущий код/данные/старые gold неизменны; источники и непроверенные гипотезы отделены. Это завершение исследования, не готовое приложение.

## WIN-01. Сравнительный native spike Qt и WPF

Выпуск: D0. Зависимости: WIN-00. Состояние: feasibility_complete_with_limits.

**Результат:** Одинаковый короткий slice: собственный PDF, таблица10000строк, одна старая операция, источник, background job/cancel; основной UI для WIN-02 — WPF + Python worker.

**Готовность и отрицательные проверки:** Сопоставимые записи startup/RAM/DPI/UIA/keyboard, лицензии фактически выбранных модулей, no UI HTTP; timebox и ADR. Не две полные реализации и не screenshot-only решение.

**Фактически11.11:** оба source UI запущены; 15 новых тестов и8 component runs прошли. Qt gap695–760мс и actual packaged QtCore DLL failure — причина fallback. WPF системные200%, полный Narrator и OS high contrast не подтверждены; installer/clean VM не выполнялись. [ADR-D01](adr_001_native_ui.md), [evidence](../../evaluation/windows_01_2026-11-11/README.md). Это не готовый продукт D0.

## WIN-02. Проверить private runtime и installer в clean VM

Выпуск: D0. Зависимости: WIN-01. Состояние: host_validated_clean_vm_pending.

**Результат:** Минимальная поставка выбранного GUI, PDF renderer и частного Python; per-user installer, manifest dependencies.

**Готовность и отрицательные проверки:** Windows11 x64 без Python/Ollama/admin, Unicode путь, offline запуск собственного примера, uninstall; без PATH/global installs. Это feasibility, не подписанный публичный релиз.

**Фактически11.11:** per-user installer22434104байт, private CPython/PDFium/WPF, install/shortcut/source15,00%/cancel/crash/uninstall на хосте проверены;10 package checks прошли. Clean VM отсутствует, OS200/contrast/Narrator speech не приняты;25 legacy cross-root path guards сохранены. Полная приёмка02 не закрыта. [Результат](installer_spike_02.md), [evidence](../../evaluation/windows_02_2026-11-11/README.md), [WIN-02B](../../prompts/windows_02b_clean_vm_acceptance.md).

**WIN-02B,11.11:** resource_blocked_kit_prepared. Пользователь подтвердил отсутствие чистой среды; kit с неизменным installer/collector/runbook готов, guest acceptance не выполнена. [Результат](clean_vm_acceptance_02b.md). Не повторять подготовку до появления ресурса; WIN-02 не complete.

## WIN-03. Выбрать stock CPython и зафиксировать зависимости

Выпуск: D0. Зависимости: WIN-02. Состояние: proposed_not_implemented.

**Результат:** Проверка текущего ядра на private stock CPython; lock/hash wheels и worker runtimes; MSYS2 baseline сохраняется.

**Готовность и отрицательные проверки:** Подходящая полная старая регрессия на новом runtime, native DLL/plugins inventory, повторяемая сборка. Отсутствующая совместимость явно исправляется новой версией, frozen receipts не переписываются.

## WIN-04. Ввести ApplicationPaths и WorkspaceContext

Выпуск: D0. Зависимости: WIN-01, WIN-03. Состояние: proposed_not_implemented.

**Результат:** Readonly assets отдельно от AppData/vault/cache/models/logs; адаптер исторического ROOT/tmp и реестра exact-resources.

**Готовность и отрицательные проверки:** Два vault, read-only install, перемещение и source-missing/hash-mismatch; нет Value/OneDrive/Git cwd defaults; исходные v1/заморозки сохраняются.

## WIN-05. Отделить ApplicationService и typed IPC

Выпуск: D0. Зависимости: WIN-04. Состояние: proposed_not_implemented.

**Результат:** GUI/CLI вызывают одну версию service; serializable commands, run_id, context/version/size limits, structured outcome.

**Готовность и отрицательные проверки:** Неверная/лишняя schema, stale context, duplicate IDs, malformed/oversized response, worker crash; UI не получает право на произвольный shell/path/SQL.

## WIN-06. Сделать supervisor долговременных заданий

Выпуск: D0. Зависимости: WIN-05. Состояние: proposed_not_implemented.

**Результат:** Job states/progress/cancel/deadline/retry/resume, event log, process ownership, one-heavy-job queue.

**Готовность и отрицательные проверки:** Повторный клик идемпотентен; late results не применяются; cancel/crash/reopen без поддельного completed, orphan worker и повреждённого vault.

## WIN-07. Создать локальное хранилище и миграции

Выпуск: D0. Зависимости: WIN-04, WIN-05. Состояние: proposed_not_implemented.

**Результат:** SQLite metadata/FTS, immutable originals, revisioned derived assets, atomic commits, backup и recovery skeleton.

**Готовность и отрицательные проверки:** Диск заполнен/обрыв записи/schema mismatch/restore; исходник не перезаписывается, версии не смешиваются; несколько vault изолированы.

## WIN-08. Создать native оболочку и понятную навигацию

Выпуск: D0. Зависимости: WIN-01, WIN-05, WIN-06. Состояние: proposed_not_implemented.

**Результат:** Qt/WPF shell в согласованном бело-зелёном направлении; projects/documents/analysis, labels, empty/loading/error states.

**Готовность и отрицательные проверки:** Реальные действия, длинные русские подписи, клавиатура/фокус/Narrator/125–200%DPI. Нет нефункциональных кнопок и UI-side финансовой арифметики.

## WIN-09. Встроить просмотр документа и точный источник

Выпуск: D0. Зависимости: WIN-07, WIN-08. Состояние: proposed_not_implemented.

**Результат:** Сменный renderer, lazy pages, text/table alternative, cell highlight и page/sheet locator.

**Готовность и отрицательные проверки:** Rotation/crop/zoom/DPI/printed page/page index; opening только через trusted resource ID. Viewer success не считается новой сверкой числа; licenses зафиксированы.

## WIN-10. Доставить D0: пять прежних операций в Windows

Выпуск: D0. Зависимости: WIN-03, WIN-04, WIN-05, WIN-06, WIN-07, WIN-08, WIN-09. Состояние: proposed_not_implemented.

**Результат:** Direct/delta/relative/scale/margin через прежний B и admission, уточнения, source/trace; private runtime installer и собственный rights-cleared demo с исходником/evidence.

**Готовность и отрицательные проверки:** Прежние financial gates, поиск без полного комплекта блокирует ответ, publication unknown/technical failure; новые desktop workflows на clean VM. Нет Streamlit/browser UI server.

## WIN-11. Сделать безопасный универсальный импорт

Выпуск: D1. Зависимости: WIN-06, WIN-07. Состояние: proposed_not_implemented.

**Результат:** Определение типа по содержимому, immutable asset/SHA, duplicate handling, quotas, encrypted/corrupted/unsupported states.

**Готовность и отрицательные проверки:** Zip-slip/bomb, oversized images/pages, вложенный executable/макрос/JS не исполняется; file/extraction/semantic states различаются. Security controls вводятся здесь, не откладываются до50.

## WIN-12. Добавить CSV/XLSX/DOCX/TXT адаптеры

Выпуск: D1. Зависимости: WIN-11. Состояние: proposed_not_implemented.

**Результат:** Encoding/delimiter/locale, workbook sheets/cells/styles/merged headers, DOCX paragraph/table locators; safe HTML sanitization.

**Готовность и отрицательные проверки:** Десятичная запятая/пробел/скобки, external refs/VBA/DDE/формулы и cached value stale; нет произвольного пересчёта Excel-кодом. CSV formula injection обезвреживается при экспорте.

## WIN-13. Подготовить DocumentIR digital PDF

Выпуск: D1. Зависимости: WIN-09, WIN-11. Состояние: proposed_not_implemented.

**Результат:** Text spans/boxes/table geometry/compound headers/multi-page linkage с parser/config/environment fingerprints.

**Готовность и отрицательные проверки:** Потерянные headers, rotation, columns, split table, units/signs, отсутствующая страница; результат на exact cell/context, не только красивый Markdown.

## WIN-14. Провести RU/EN OCR benchmark

Выпуск: D1. Зависимости: WIN-11, WIN-13. Состояние: proposed_not_implemented.

**Результат:** Rights-cleared diverse sample: pdfplumber baseline vs Docling/Paddle/Tesseract; time/RAM/Windows compatibility/code+weights licenses.

**Готовность и отрицательные проверки:** Независимый cell/context gold, held-out layouts, failed docs в знаменателе; OCR/structure/semantic accuracy отдельно. Публичные заявления поставщика не заменяют измерение.

## WIN-15. Интегрировать выбранные OCR и языковые пакеты

Выпуск: D1. Зависимости: WIN-14, WIN-06. Состояние: proposed_not_implemented.

**Результат:** Один основной и ограниченный fallback adapter, page-at-a-time processing, model-pack hashes/licenses/import/download.

**Готовность и отрицательные проверки:** Чистая offline машина, cancel/OOM/mixed PDF/low disk; нет скрытого скачивания/облака. Fallback не повышает непроверенное число до Fact.

## WIN-16. Определять тип и контекст документа

Выпуск: D1. Зависимости: WIN-12, WIN-13. Состояние: proposed_not_implemented.

**Результат:** Rule/Qwen proposals: класс, стороны/группа, стандарт, периоды, единицы, структура и confidence-by-field.

**Готовность и отрицательные проверки:** Банк/RAS/IFRS/управленческий не смешиваются; неизвестный тип/alias/поле требуют уточнения; upload/signature/report/publication dates отдельно.

## WIN-17. Утвердить rich DocumentIR и provenance schema

Выпуск: D1. Зависимости: WIN-12, WIN-13, WIN-16. Состояние: proposed_not_implemented.

**Результат:** Версионированные документы/страницы/таблицы/ячейки/поля, transforms, original lexical value, relationships.

**Готовность и отрицательные проверки:** Round-trip и stale source invalidation; unit/period/header/source references обязательны для поддержанной схемы; extraction version не перезаписывает прежнюю.

## WIN-18. Сделать Fact vNext и admission profiles

Выпуск: D1. Зависимости: WIN-17. Состояние: proposed_not_implemented.

**Результат:** Candidate/Fact/DerivedValue и separate machine-checked policy; semantic mapping/versioned pack, false-admission/abstention evaluation; старые gates не ослаблять.

**Готовность и отрицательные проверки:** Кандидат/Qwen/structure_checked не автоматически admitted; изменённый source/config/index блокируется; human_reviewed только фактическое действие. Independent gold вне runtime.

## WIN-19. Создать рабочее место проверки и исправлений

Выпуск: D1. Зависимости: WIN-08, WIN-09, WIN-18. Состояние: proposed_not_implemented.

**Результат:** Очередь неоднозначных полей с источником, локальное исправление, audit history, versioned template/profile.

**Готовность и отрицательные проверки:** Исправление одной ячейки не подтверждает весь документ; прежние версии сохраняются; отмена/две конфликтующие правки/смена исходника не скрываются.

## WIN-20. Расширить структурированный и текстовый поиск

Выпуск: D1. Зависимости: WIN-07, WIN-17, WIN-18. Состояние: proposed_not_implemented.

**Результат:** SQLite FTS5 + filters + table context; optional local embeddings/reranker по результатам сравнения.

**Готовность и отрицательные проверки:** Evidence coverage/recall и wrong-version negatives; partial retrieval/timeout/missing index не превращаются в финансовый ответ; fulltext и raw docs приватны.

## WIN-21. Расширить IFRS pack до трёх форм и примечаний

Выпуск: D2. Зависимости: WIN-18, WIN-19, WIN-20. Состояние: proposed_not_implemented.

**Результат:** Definition mapping/perimeter/reporting basis для balance/P&L/CF/notes/audit; IFRS18 отдельная проверка основы.

**Готовность и отрицательные проверки:** Original/comparative, full/YTD/instant, OP composition/final CFO, отрицательные числа/единицы; поздняя comparative не original; прав на PDF не добавляется.

## WIN-22. Создать независимый РСБУ pack

Выпуск: D2. Зависимости: WIN-18, WIN-19, WIN-20. Состояние: proposed_not_implemented.

**Результат:** Проверенные действующие редакции форм/пояснений/FSBU и dictionary юрлица, versioned line mapping.

**Готовность и отрицательные проверки:** Нормативные тексты реально прочитаны и применимость доказана; не переносить IFRS definitions по похожему имени. Иной период/код строки/редакция требуют проверки.

## WIN-23. Импортировать банковские CSV/XLSX

Выпуск: D1. Зависимости: WIN-12, WIN-18, WIN-19. Состояние: proposed_not_implemented.

**Результат:** Account/transaction model, opening/closing, transaction/posting dates, currencies, categories и internal transfers.

**Готовность и отрицательные проверки:** Debit/credit direction, duplicates, refunds/fees, missing balance, несколько счетов и same transfer. Приход не равен выручке; корректировка категории аудируема.

## WIN-24. Добавить PDF-выписки и сканы

Выпуск: D2. Зависимости: WIN-15, WIN-17, WIN-23. Состояние: proposed_not_implemented.

**Результат:** Bank-layout profiles с geometry и переносом строк, source каждой транзакции, неполные страницы.

**Готовность и отрицательные проверки:** Held-out bank layouts/многовалютность/расхождение opening+flows=closing; неподдержанные строки не исчезают из знаменателя и не дополняются моделью.

## WIN-25. Добавить счета, чеки и акты

Выпуск: D2. Зависимости: WIN-15, WIN-17, WIN-18, WIN-19. Состояние: proposed_not_implemented.

**Результат:** Document/line item/VAT/totals/parties/due dates, duplicate IDs; нормализация с оригинальной записью.

**Готовность и отрицательные проверки:** Net+tax=gross по объявленной политике округления, discounts/returns, неверный контрагент/период; документ не доказывает оплату или recognized revenue.

## WIN-26. Связать документы и платежи

Выпуск: D2. Зависимости: WIN-23, WIN-25. Состояние: proposed_not_implemented.

**Результат:** Reconciliation graph: contract/invoice/act/payment, partial/many-to-many match с объяснением признаков.

**Готовность и отрицательные проверки:** Похожие суммы/номера, commissions/FX, split/overpayment/refund, duplicates; ambiguous links требует выбора; match не меняет исходные документы.

## WIN-27. Извлекать договорные обязательства

Выпуск: D2. Зависимости: WIN-16, WIN-18, WIN-19, WIN-20. Состояние: proposed_not_implemented.

**Результат:** Contracts/amendments/loans/leases: сроки, условия, ставки, индексация, security/covenants, conditional obligations.

**Готовность и отрицательные проверки:** Действующая редакция/приложение/условность/отмена/просрочка; буквальный clause и интерпретация разделены; нет окончательного юридического заключения от Qwen.

## WIN-28. Поддержать управленческие и пользовательские схемы

Выпуск: D2. Зависимости: WIN-12, WIN-18, WIN-19. Состояние: proposed_not_implemented.

**Результат:** Mapping статей/проектов/центров затрат, plan/actual, пользовательский chart of accounts без обязательного IFRS.

**Готовность и отрицательные проверки:** Units/periods/currencies и aggregation rules, explicit user mapping, не сравнивать budget соactual как два reported Facts; профиль не распространяется скрыто на все файлы.

## WIN-29. Расширить registry финансовых показателей

Выпуск: D2. Зависимости: WIN-18, WIN-21. Состояние: proposed_not_implemented.

**Результат:** Небольшие пакеты profitability/liquidity/leverage/efficiency с formula version/admission/variants/reference.

**Готовность и отрицательные проверки:** Independent Fraction/Decimal checks, zero/negative denominator, средние vs closing, days/scale/FX gates. EBITDA/FCF/net debt только отдельная доказанная методика; старые пять операций unchanged.

## WIN-30. Согласовать три финансовые формы

Выпуск: D2. Зависимости: WIN-21, WIN-29. Состояние: proposed_not_implemented.

**Результат:** Balance/equity/debt/cash bridges и coverage residual; бухгалтерские уравнения по фактическим строкам.

**Готовность и отрицательные проверки:** Неполный комплект/разные версии/округление/currency translation; unexplained residual виден, Qwen не создаёт балансирующую статью.

## WIN-31. Сделать тренды, common-size и variance bridges

Выпуск: D2. Зависимости: WIN-29, WIN-30. Состояние: proposed_not_implemented.

**Результат:** Сопоставимые динамики, доли, вклад статей, user-selected periods/entities; reported vs normalized distinction.

**Готовность и отрицательные проверки:** Несопоставимость/период нестандартной длины/negative base; арифметический вклад не причинность, annualized не выдаётся за actual quarter.

## WIN-32. Добавить анализ cash quality и working capital

Выпуск: D2. Зависимости: WIN-21, WIN-29, WIN-30. Состояние: proposed_not_implemented.

**Результат:** Profit/CFO, receivables/inventory/payables, DSO/DIO/DPO/CCC, cash capex/FCF при достаточных входах.

**Готовность и отрицательные проверки:** Средние и подходящие потоки/дни, acquisitions/noncash/reclassifications; нельзя автоматически использовать revenue вместо purchases или accrual capex вместо cash.

## WIN-33. Добавить долг, ковенанты и ликвидность

Выпуск: D2. Зависимости: WIN-27, WIN-29, WIN-30. Состояние: proposed_not_implemented.

**Результат:** Debt maturity, fixed/floating/FX, lease/restricted-cash policy, covenant headroom и liquidity calendar.

**Готовность и отрицательные проверки:** Правила конкретного договора, future interest assumptions, missing facilities, inconsistent units; scenario covenant breach не объявляется actual нарушением.

## WIN-34. Анализировать сегменты, риски, notes и аудит

Выпуск: D2. Зависимости: WIN-20, WIN-21, WIN-29. Состояние: proposed_not_implemented.

**Результат:** Segments/concentration/related parties/contingencies/accounting changes/audit flags с exact passages.

**Готовность и отрицательные проверки:** Scope и consolidation eliminations, разные restated segments, conditional language; не делать fraud/solvency guarantee. Source silence/нет prepared Fact не доказывает отсутствие раскрытия.

## WIN-35. Сравнивать версии и совместимые компании

Выпуск: D2. Зависимости: WIN-20, WIN-21, WIN-22, WIN-29. Состояние: proposed_not_implemented.

**Результат:** Version diff numeric+text, original/comparative map, compatibility proofs и peer cohorts из доступных файлов.

**Готовность и отрицательные проверки:** Дата/периметр/definition/currency/стандарт/период; Segezha CFO не автоматически эквивалентны; внешние market data/FX только отдельные будущие доверенные входы.

## WIN-36. Создать native аналитическое рабочее пространство

Выпуск: D2. Зависимости: WIN-08, WIN-09, WIN-19, WIN-31. Состояние: proposed_not_implemented.

**Результат:** Overview/three statements/metrics/charts/notes/sources/review, novice explanations и detailed mode.

**Готовность и отрицательные проверки:** Нет чисел без locator/units/version; смена фильтра инвалидирует answer; клавиатура/контраст/масштаб; ratios показываются только по выпущенным packs.

## WIN-37. Расширить natural input и явные уточнения

Выпуск: D3. Зависимости: WIN-18, WIN-20, WIN-36, WIN-40. Состояние: proposed_not_implemented.

**Результат:** Local Qwen semantic proposals + deterministic schema/domain validation, structured equivalent для каждого workflow.

**Готовность и отрицательные проверки:** Original/raw/origins/history/direction/why сохраняются; multi-intent/unfulfilled requests; unsupported schema/limit не считается успешным ответом. Ни model value, ни формула не trusted Fact.

## WIN-38. Сделать durable многошаговый исследовательский агент

Выпуск: D3. Зависимости: WIN-06, WIN-20, WIN-37, WIN-40. Состояние: proposed_not_implemented.

**Результат:** Видимый bounded plan/tools, dependency execution, checkpoints/resume/coverage, read-only analysis by default.

**Готовность и отрицательные проверки:** Tool injection/loop/budget/deadline/crash/cancel, partial search, stale inputs, no arbitrary exec/SQL/path/URL. Явно отделить настоящие calls от mock/dev и B быстрых операций.

## WIN-39. Проверять grounded аналитические объяснения

Выпуск: D3. Зависимости: WIN-29, WIN-34, WIN-38. Состояние: proposed_not_implemented.

**Результат:** Claim graph: reported/calculated/interpretation/scenario/forecast, cited support, coverage and unresolved why.

**Готовность и отрицательные проверки:** Неверная предпосылка, unsupported causality, число/версия/единица не из inputs, omission/counter-evidence; текст не создаёт admission и не прячет неисполненные требования.

## WIN-40. Создать local model registry и hardware policy

Выпуск: D3. Зависимости: WIN-03, WIN-06, WIN-07. Состояние: proposed_not_implemented.

**Результат:** Pinned Qwen/Ollama initial adapter, optional llama.cpp/embeddings/reranker, model licenses/SHA/template/context, LocalOnlyPolicy.

**Готовность и отрицательные проверки:** No cloud/env fallback; active-network/hostile-config/foreign-endpoint test, owned loopback process policy; no executable model code, explicit downloads/import/resume; RAM/VRAM/CPU profiling, known tasks parity. Модель не обязательна для базового чтения/расчётов.

## WIN-41. Добавить повторяемые workflows и локальную обратную связь

Выпуск: D3. Зависимости: WIN-19, WIN-38, WIN-39. Состояние: proposed_not_implemented.

**Результат:** Шаблоны исследования, approved-folder intake с явным выбором, сохранённые настройки/правки без скрытого обучения.

**Готовность и отрицательные проверки:** Только выбранная папка, duplicate idempotency, document change invalidation, остановка наблюдения; feedback не становится новым verified Fact в другом документе.

## WIN-42. Сделать переносимые аналитические экспорты

Выпуск: D3. Зависимости: WIN-18, WIN-36, WIN-39. Состояние: proposed_not_implemented.

**Результат:** CSV/XLSX/Markdown и собственный PDF анализа с inputs/provenance/versions/limitations, без первичных чужих страниц.

**Готовность и отрицательные проверки:** Formula injection, округление/locale, источники/единицы/периоды, redaction; экспорт не требует Excel и не копирует PDF/полный текст без прав.

## WIN-43. Добавить бюджет и план/факт

Выпуск: D4. Зависимости: WIN-28, WIN-31, WIN-36. Состояние: proposed_not_implemented.

**Результат:** Versions budgets, actual mapping, categories/projects, variance explanation and approval-independent local editing.

**Готовность и отрицательные проверки:** План не Fact, перенос статьи/периода версионирован, totals сходятся; неподдержанная классификация требует выбора, скрытая подгонка запрещена.

## WIN-44. Собрать платёжный календарь и cash projection

Выпуск: D4. Зависимости: WIN-23, WIN-26, WIN-27, WIN-43. Состояние: proposed_not_implemented.

**Результат:** Known obligations/expected collections, overdue, opening cash, user timing assumptions и scenario deficit.

**Готовность и отрицательные проверки:** Dates/working calendar/partial payments/double counting/conditional amounts; expected inflow не guaranteed. Нет переводов/торговли и невыраженного FX.

## WIN-45. Реализовать driver what-if и сценарные три формы

Выпуск: D4. Зависимости: WIN-29, WIN-30, WIN-43, WIN-44. Состояние: proposed_not_implemented.

**Результат:** Volume/price/cost/tax/working-capital/debt drivers, base/upside/downside, sensitivity and assumption provenance.

**Готовность и отрицательные проверки:** Сценарный баланс и cash bridges, negative cases/constraints, immutable versions; predicted не reported Fact, Qwen не подставляет неизвестные drivers.

## WIN-46. Проверять пригодность временных рядов и vintages

Выпуск: D5. Зависимости: WIN-18, WIN-35, WIN-43. Состояние: proposed_not_implemented.

**Результат:** Unique regular periods, definitions/perimeter/currency, revisions/as_of/publication и target actual vintage заранее, series inventory/readiness report.

**Готовность и отрицательные проверки:** Сравнительные ячейки не новые периоды; unknown publication блокирует historical claims; нынешний snapshot forecast отдельно. Нет универсального magic minimum samples.

## WIN-47. Ввести статистические baseline и backtesting

Выпуск: D5. Зависимости: WIN-46. Состояние: proposed_not_implemented.

**Результат:** Naive/seasonal/ETS/ARIMA candidate pipeline, rolling origin + locked temporal holdout, independent metrics/report.

**Готовность и отрицательные проверки:** No future leakage in preprocessing/HPO/covariates, MAE/bias/MASE when defined, coverage/width/horizon, regime breaks/zero/negative data. Неуспех baseline comparison сохраняется.

## WIN-48. Показать прогнозы, интервалы и историю ошибок

Выпуск: D5. Зависимости: WIN-36, WIN-47. Состояние: proposed_not_implemented.

**Результат:** ForecastVintage/model+data hashes/as_of/horizon/assumptions, interval charts and matured actual comparison.

**Готовность и отрицательные проверки:** Forecast/plan/scenario/consensus раздельны, no point-only confidence, stale/revised actuals handled; Qwen объясняет код. Непригодный ряд не получает вымышленную кривую.

## WIN-49. Исследовать foundation time-series models опционально

Выпуск: RND. Зависимости: WIN-47, WIN-48. Состояние: proposed_not_implemented.

**Результат:** Отдельный feature-flag benchmark лицензированных local weights против baseline на неизменном holdout.

**Готовность и отрицательные проверки:** Выбор на dev/validation, locked test не для подбора; лицензия конкретных checkpoint/quantization/deps, Windows/RAM/latency; TimesFM3 non-production weights не включать в production. Нет улучшения — не включать, не задерживать V1.

## WIN-50. Завершить threat model и hardening

Выпуск: CROSS. Зависимости: WIN-10, WIN-11, WIN-18, WIN-38. Состояние: proposed_not_implemented.

**Результат:** Модель угроз, изоляция parsing/model workers, broker/allowlists/limits, dependency vulnerability process; baseline с11.

**Готовность и отрицательные проверки:** Malicious PDF/DOCX/zip/path/reparse point, prompt injection, cross-vault access, no arbitrary exec, parser crash/DoS; Job Objects не называются полным sandbox.

## WIN-51. Добавить защиту данных и переносимый recovery

Выпуск: CROSS. Зависимости: WIN-07, WIN-50. Состояние: proposed_not_implemented.

**Результат:** Проверенное encryption/key storage/DPAPI policy, secrets/log redaction, encrypted portable backup/recovery.

**Готовность и отрицательные проверки:** Restore на другом разрешённом устройстве, forgotten key story, damaged backup, no plaintext sensitive logs; DPAPI сам по себе не encrypted SQLite.

## WIN-52. Измерить performance и ресурсные профили

Выпуск: CROSS. Зависимости: WIN-06, WIN-15, WIN-36, WIN-40. Состояние: proposed_not_implemented.

**Результат:** Cold/warm start/import/OCR/search/AI, peak RAM/VRAM/disk, cache invalidation, queue priorities and lazy pages.

**Готовность и отрицательные проверки:** 8/16/32GB tiers проверяются, OOM graceful, UI responsive/cancel, no runaway cache, model file size не RAM requirement. Цели утверждаются после baseline.

## WIN-53. Автоматизировать native UIA и доступность

Выпуск: CROSS. Зависимости: WIN-08, WIN-09, WIN-36. Состояние: proposed_not_implemented.

**Результат:** Accessibility identifiers, keyboard/Narrator/high contrast/DPI, component/UIA regression and actual user paths.

**Готовность и отрицательные проверки:** Long RU/large numbers/multiple monitors/focus/error/cancel, источники text alternative. Старые18AppTest не записываются как native tests; checks вводятся с8.

## WIN-54. Настроить license/SBOM/signing/update pipeline

Выпуск: CROSS. Зависимости: WIN-02, WIN-03, WIN-50. Состояние: proposed_not_implemented.

**Результат:** Собственная лицензия по решению пользователя, per-module/weights inventory, trusted signing channel и signed staged updates.

**Готовность и отрицательные проверки:** Code vs weights/PDF/GPU licenses, no unsigned substitution/old vulnerable rollback, signature/hash/version, cert availability реальные. SmartScreen не обходится; ранний inventory с1.

## WIN-55. Проверить полную поставку на чистых Windows

Выпуск: CROSS. Зависимости: WIN-10, WIN-51, WIN-52, WIN-53, WIN-54. Состояние: proposed_not_implemented.

**Результат:** VM matrix install/import/basic/offline/model-pack/update/migration/rollback/backup/uninstall, artifacts/receipts.

**Готовность и отрицательные проверки:** Pinned supported Windows build/arch/security lifecycle, no Python/admin/CLI/Ollama manual setup, Unicode paths/low disk/proxy/offline/interrupted update/Mark-of-the-Web; snapshot restore после schema migration, no writes before health check. User data retained by default; no orphan processes.

## WIN-56. Создать новый eval corpus и независимые эталоны

Выпуск: CROSS. Зависимости: WIN-00, WIN-11. Состояние: proposed_not_implemented.

**Результат:** Начать с14/18 и расширять с каждым pack: rights-cleared diverse docs, hand-labelled context/cell/claims, grouped/temporal split.

**Готовность и отрицательные проверки:** Known dev vs locked holdout, raw failures/denominators/family provenance, independent numeric references вне runtime. Старые freeze14/gold/QA не переписываются; не ждать всех функций для начала eval.

## WIN-57. Провести будущий usability pilot

Выпуск: V1. Зависимости: WIN-36, WIN-39, WIN-53, WIN-55. Состояние: proposed_not_implemented.

**Результат:** Добровольцы разного опыта выполняют реальные novice tasks, наблюдения/task metrics/confusion/fixes.

**Готовность и отрицательные проверки:** Согласованное использование собственных/разрешённых данных, честные n/время/ошибки, реальные действия; не приписывать интервью или вклад формальным ролям. Нет требования чужой формальной приёмки.

## WIN-58. Подготовить scoped public beta и поддержку

Выпуск: V1. Зависимости: WIN-42, WIN-54, WIN-55, WIN-56, WIN-57. Состояние: proposed_not_implemented.

**Результат:** Подписанный installer, собственный demo project, onboarding/help/capabilities/limitations/privacy/support/preview diagnostics.

**Готовность и отрицательные проверки:** Только прошедшие packs/hardware/Windows объявлены supported; no secret telemetry; PDF/model redistribution licenses проверены. Документация продукта, не отменённый академический отчёт18.

## WIN-59. Выпустить устойчивую V1 в измеренном scope

Выпуск: V1. Зависимости: WIN-58. Состояние: proposed_not_implemented.

**Результат:** Release checklist/artifacts/hashes/changelog/source licenses/update/recovery, перечень supported и unsupported.

**Готовность и отрицательные проверки:** Матрица обязательных сценариев/финансовых gates/security/UX/cleanVM пройдена, no invented unseen quality. D5/RND не блокируют V1, если явно исключены из выпуска.

## WIN-60. Поддерживать адаптеры и планировать дальнейшее расширение

Выпуск: MAINTENANCE. Зависимости: WIN-59. Состояние: proposed_not_implemented.

**Результат:** Regression новых форм/моделей/нормативов, security updates, новые domain/language packs и structured-source connectors по правам.

**Готовность и отрицательные проверки:** Не ломать user vault/старые receipts; каждое расширение version+tests+PR. Future cloud seam выключен до отдельного задания; никакого автоматического scraping/trading.
