# КП3-09: фиксированный сервис B и минимальный интерфейс

Версия Answer — `kp3-answer-0.1`, доверенного setup — `kp3-service-context-0.1`. Один `service_b.execute(source, method, context, answers, run_id)` вызывается CLI и новым изолированным `app_kp3/service_b_app.py`. Поддержан B; A/C/mock/replay не подменяются B. Модель на09 не используется. Старые0.1/0.2/0.3, определения/источники/формулы/gold и прежний неопубликованный UI не менялись.

## Порядок и исходы

| Этап trace | Фактическая работа |
|---|---|
| input | Строгий text/form08; исходный вопрос сохраняется |
| catalog_filters | Целостность trusted context, нормализация/уточнения и предварительные контексты08 |
| search | Обязательный живой поиск06 по полному SearchSpec, включая версии/периоды/единицы/as_of |
| fact_resolution | Каждый требуемый checked Evidence найден ровно один раз; digest/ячейка/значение/локатор совпадают с каталогом; повторная сверка binding |
| source_validation | Существующие source proof07 и байты выбранных real PDF, без новой первичной аннотации |
| calculation | Существующий калькулятор07 с обязательным live retrieval guard |
| result_validation | `validate_calculation_binding`07, включая независимое от переданного результата повторное выполнение зарегистрированной функции |
| answer | Общая форма ответа/исхода, предпосылки, trace и приватная запись запуска |

Предварительный binder08 не даёт права пропустить search: даже при известных подходящих Fact partial/error/automatic блокируют дальнейшее вычисление. Значения берутся из допущенных Fact после точного совпадения найденных Evidence. Поиск не переоценивает финансовый смысл и не повышает candidate. Старые bindings/source checks05 и admission07 проверяются отдельно от хешей. После search binding разрешается заново для защиты от смены контекста.

Trace всегда содержит восемь этапов с одним run_id; невыполненные имеют skipped/elapsed_ms0, а не выдуманный успех. Task/input_id, request_id0.3, outcome.run_id, retrieval wrapper, trace и сохранённый Answer связываются этим run_id; исходный пользовательский вопрос не меняется. Входной caller input_id не используется как скрытый выбор компании/версии. Технические durations измерены perf_counter, это не benchmark модели.

В07 live guard проверяет поиск ещё раз внутри calculate, затем валидатор результата повторяет его при пересчёте. Эти повторные обращения и recomputation видимы в trace. В успешном пути фактически три обращения к поиску и два исполнения зарегистрированной операции, последнее — проверка результата. Они не считаются разными финансовыми наблюдениями. Программные проверки и их повтор не означают human_reviewed или новую primary annotation.

Execution completed/awaiting_clarification/error/limit, request_status evaluated/awaiting_clarification/missing/conflict/unsupported/error разделены с financial_status. До калькулятора financial_status=null: например publication_unknown от обязательного поиска — предварительная блокировка request_status=missing, операция не выполнялась. Это не техническая ошибка и не утверждение об отсутствии строки PDF. После07 financial_status/outcome/financial_result совпадают с его проверенным исходом. При error/limit/clarification финансового результата нет. Готовый parse/binding не называется answered.

## Контекст и сохранность

Setup задаётся локальным JSON: schema_version/catalog/dictionary/admission/bindings/checks/resources/retrieval/run_dir. retrieval содержит db_path/config/lexicon/exports. Пути передаёт доверенный запуск, в пользовательском text/form/answers их нет. Все относительные пути разрешаются относительно текущего project worktree. Run_dir обязан быть в его исключённой tmp/. Источники могут находиться в прежней доверенной карте ресурсов05–08; совпавшие PDF не копируются/не скачиваются заново.

Context identity связывает каталог/словарь/admission/resources/file guards, retrieval configuration/export map, путь индекса/run-dir и config guard. Файлы исходного07 setup и service config проверяются перед исполнением; источник/индекс/export/config/code fingerprints проверяет06/07. Это целостность доверенной настройки, не криптографическая аттестация автора и не замена сверки финансового смысла.

Каждый запуск имеет новый run_id; файловое имя — SHA-256(run_id), а не исполняемый путь из вопроса. Приватный JSON открывается эксклюзивно до выполнения. Повторный run_id даёт технический run_id_exists без перезаписи предыдущего результата. Ошибки/уточнения тоже сохраняются; сбой самой записи отдельно возвращается как technical error без числа. Это минимальная запись исполнения для проверки09, не готовая история/экспорт следующих этапов.

UI использует тот же execute, без собственных формул/SQL/модельных веток. Изменение исходного ввода или context identity скрывает старый Answer и очищает цепочку уточнений; изменившийся контекст не принимает старый Answer. Конкретные уточнения08 можно применить к исходному вопросу, history/assumptions остаются в новой трассе. Понятая задача и происхождение inferred полей раскрываются отдельно. Стандарт/группа/definition/unit выводятся только при однозначности каталога, mode/периоды/организация/действие не имеют финансовых defaults.

Предпосылка проверяется по знаку exact difference уже рассчитанного07 absolute/relative; формула не дублируется в UI. supported/contradicted/not_checked и asserted/observed direction сохраняются. При отказе/error предпосылка не подтверждается. Причинное «почему» остаётся not_supported, причина не выдумывается; несколько запрошенных действий не объявляются выполненными одним результатом.

## Локальный просмотр источника

SourceViewer слушает только127.0.0.1 на выделенном порту. Из текущего answered допускаются только выбранные exact document/version; URL не содержит пути файловой системы и не исполняет текст документа/вопроса. До выдачи проверяются admission/setup, размер/сигнатура/SHA реальных байтов. После смены ввода registry отзывается; старая ссылка возвращает404.

В используемом IAB прямой PDF не отобразился. Исправленный основной путь показывает PNG нужной страницы через уже установленный Poppler pdftoppm: фиксированный argv, shell=False, допустимый номер страницы, timeout45с, скрытое окно. Перед/после рендера проверяется exact-PDF. Новые изображения имеют уникальные имена в tmp/source-pages; локальный cache связан с SHA/page и проверяется по SHA изображения. Старые PDF/страницы не перезаписываются; первичные изображения/текст/индексы/exports не входят в Git. Это локальный просмотр существующего источника, не новый extractor/OCR/финансовая аннотация.

Публикации всех8 документов unknown/unproven; snapshot допустим, historical/реальные сценарии закрыты. Неизвестные права остаются неизвестными; assistant_checked не становится human_reviewed. OP/CFO определения, периоды, версии/единицы, positive base, signed values и HALF_UP07 сохранены. Новых real Fact/публикаций/доказательств cross-original comparability нет.

## Запуск и проверки

Основной CLI — `python -I scripts/execute_service_b.py --context tmp/service-context.json --input tmp/input.json [--answers tmp/answers.json] [--method B]`. Exit0 completed/evaluated,3 clarification,4 предварительный missing/conflict/unsupported,2 technical error/limit. Runtime не читает evaluator expected/gold.

Публичные собственные fixtures без primary PDF: `python -I scripts/check_kp3_service_b.py`. Для существующего real setup — `--context tmp/service-context.json --report tmp/service-report.json`. Матрица содержит5 own synthetic и104 real случая (8 exact-версий,4 операции ×3 показателя +margin); исходные48 Fact повторяются, это не104 новых наблюдения. Financial reference — неизменный Fraction/integer07 с отдельным Decimal80, не production answer. Expected Fact IDs определены evaluator по явным document/metric/origin/period и проверяются отдельно от чисел.

UI использует прежний отдельный `tmp/kp3-ui-cpython312/Scripts/python.exe`: проверены Python3.12.14/Streamlit1.67.0. Основные тесты — MSYS2 Python3.14.7/SQLite3.53.4. Новых установок/изменений глобальных пакетов/старого venv нет. Пример PowerShell из нового worktree:

~~~powershell
$env:KP3_SERVICE_CONTEXT = (Resolve-Path tmp/service-context.json).Path
& '<исходная папка>/tmp/kp3-ui-cpython312/Scripts/python.exe' -I -m streamlit run app_kp3/service_b_app.py --server.address 127.0.0.1 --server.port 8509 --server.headless true --browser.gatherUsageStats false --server.fileWatcherType none
~~~

Автоматический AppTest и реальный браузер — разные доказательства. [AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest) симулирует приложение; отдельно через CUA выполнены реальные действия/просмотр страницы/уточнение/отказ/сбой. [Session State](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state) используется для состояния текущего ввода, а не как источник финансового факта. Проверены селекторы без неявного первого значения согласно [selectbox](https://docs.streamlit.io/develop/api-reference/widgets/st.selectbox).

Доказательства в evaluation/kp3_09_2026-11-10/:506 unit (467 прежних+39 новых),7 отдельных UI AppTest,37 новых CLI,checkers03–09/5 legacy,5 own+104 known real cases и отдельные наблюдения CUA. Ошибки браузерного прямого PDF/прерванного локального процесса сохранены как диагностика, не успешный финансовый ответ. Все семьи известны разработчику, reserved unseen real0, final eval freeze14 не выполнялся, качество модели/рынка не заявляется. По последнему поручению пользователя после доставки09 автоматически выполняется отдельно оформленный10;11 не начинается.
