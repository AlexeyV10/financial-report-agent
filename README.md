# Новое направление: локальное Windows-приложение

Активный продуктовый план после нового решения пользователя11.11.2026: [ПЛАН_РАЗВИТИЯ_WINDOWS.md](ПЛАН_РАЗВИТИЯ_WINDOWS.md). Универсальные финансовые документы, локальный Qwen, native UI; академические отчёт/презентация18 сейчас не выполняются. Это завершённое исследование, реализация ещё не начата.

[Подробный backlog61задача](docs/windows/backlog.md) · [Источники](docs/windows/sources.json) · [Следующий WIN-01 prompt](prompts/windows_01_native_desktop_spike.md). Старые результаты КП3 ниже сохранены; названия готового desktop в прежних разделах относятся к Streamlit-оболочке17, а не к новой Windows-сборке.

Возобновление11.11.2026:329pins и SHA manifest сохранены; свежие B/UI readiness готовы. В первоначальной проверке10.11 A/C дали adapter_unavailable, а11.11 уже существующий pinned endpoint ответил на readonly probe. Новых финансовых A/C ответов и modelchat нет, модель в этой задаче не запускалась/не останавливалась. Первоначальная Git-доставка не исполнилась из-за лимита автоматической проверки разрешений; после возобновления обычная проверка разрешений приняла повтор. Публикация датируется11.11; идентификатор rc1 и папка evidence сохраняют дату начала10.11. КП3-18 не запускался.

## КП3-17: ограниченный кандидат выпуска kp3-rc1 — 10.11.2026

Кандидат kp3-rc1-2026-11-10 подготовлен с сохранением оценённого14/16 финансового ядра и принятого после16 интерфейса «Рабочий стол». Канонический manifest data/releases/kp3_rc1/manifest.json (SHA1aadafb7640f27758bb2b7f04a2d6310b668da5b8746cb8dcf8b0d10cce5765c) связывает329 собственных файлов. Документация: docs/kp3/release_candidate_v1.md; аудит/acceptance/version-diff/results: evaluation/kp3_17_2026-11-10/; самостоятельный промт18: prompts/kp3_18_report_presentation_demo.md. Полный первоначальный P0 не объявлен: общего UI загрузки/проверки/допуска нового PDF нет, язык ограничен, historical/realtradingblocked; пакет19/материалы18 не выполнены.

799/799unit (778+21),18/18 AppTest (15 прежних+3 адресных на17),17checkers03–14/oldgold04/07/corpus05/5legacy,143/143 known probes15 (включая20явных controller mocks),отдельно2actualworkercontrols прошли.19 известных release-controls (14financial forms:7numeric/7refusal;1clarification;2technical;2scenario) прошли в worktree и в новой папке на этой же машине; это те же19, не38 независимых наблюдений. Answer/JSON/Markdown/history/trace/UI presentation/evaluator согласованы.7negativeCLI и5actuallaunchercontrols прошли. Все первые ошибки среды/стенда сохранены;799полныхтестов после реальной эскалации, без обхода ос.link/socket guards.

B/UI готовы; A/C readiness=adapter_unavailable/error без финансового результата, новыхnativechat0/сервермодели не запускался. Новый guarded launcher scripts/release_ui.ps1 diagnose/start/status/stop использует localhost8522, проверяет code/resources/deps/ownPID/path/time/manifest и отказывает на чужом порту. Собственный UI17 после проверки остановлен, прежнийUI8521 сохранён. Frozen134files/28resources,138raw16 и идентичный offline replay сохранены, source48Fact/8PDF/publicationunknown8/human_reviewed0/rightsunknown неизменны. Новыхисточников/OCR/формул/моделей/gold/finalbenchmark нет. Это qualified local RC, не полная версия1.0/новая оценка качества.18 подготовлен как промт и не запускался; merge не поручен. Старые разделы ниже сохранены побайтово.

КП3-UI,10.11.2026: выбранный первый вариант «Рабочий стол» реализован в отдельном app_kp3/desktop_app.py: светлая навигация, вопрос/форма, ответ с источником, уточнения, история, собственный MD/JSON и прежний учебный сценарий. Основная кнопка сразу после вопроса, детали раскрываются. Запуск из tmp/kp3-ui-worktree: scripts/desktop_ui.ps1 start; localhost8521. Документация: docs/kp3/desktop_ui_v1.md; evidence: evaluation/kp3_ui_2026-11-10; самостоятельный контекст: prompts/kp3_ui_handoff.md.

778/778 unit (760+18),15/15 Streamlit integration,17checkers03–14/oldgold04/07/corpus05/5legacy прошли. Реальный браузер проверен: расчёт/источник/выгрузка/повтор/смена компании/уточнение/360px-меню/desktop. Сохранены134frozenfiles/28resources,138raw16 и идентичный replay16. Новых realFact/публикаций/human_reviewed/моделей/библиотек нет, native modelcalls0. Каталог48Fact/8PDF прежний,8publicationunknown: historical/realtradingblocked. Это UI-задача после16;17/18 не начаты, usability research/новый benchmark не заявлены. Старые разделы ниже сохранены побайтово.

## КП3-16 завершён технически — 10.11.2026

КП3-16,10.11.2026:138/138 actual (120primary+18warm),227native chat/unknownrequests0. На40 известных явныхформах каждый B/A/C:32/32strictnumeric,8/8correctrefusal,40/40technical,86/86observedclaims;6/6повторов укаждого совпали. Primarymedian B0.207/A2.459/C5.496с; преимущества A/C вточности здесь нет. Отдельно20/20owncalculator,8/8parser,29/29preparedqueries46/46Evidence,automatic40/48cells6/8docs/8unsupportedвn,12/12scenario (4owncompleted/7blocked/1expectederror),robustness15reused.760/760unit (728+32),checkers03–15/oldgold04/07/corpus05/5legacy/freeze/replay прошли. Frozen134files/28resources unchanged; runmanifest sealed доответов, дваreplay identical, no-opresumeoffline без новыхвызовов.32exactcells/28economiccontexts/8versions/2lineages,known/unseen0. НовыхrealFact/publication/rights/human_reviewed/worker/models/packages/UI0; realtradingblocked. СтарыеQA07/3из10/reserved0 сохранены. Это known-corpus сравнение, не рыночное/unseenкачество. Сервер16остановлен поownPID/path/starttime. Промт17готов,17не применён;mergeне поручен.

Результаты: docs/kp3/final_comparison_v1.md и evaluation/kp3_16_2026-11-10/analysis-final.md. Git-доставка: git-publication и финальная локальная квитанция этапа.

## КП3-15 завершён технически — 10.11.2026

КП3-15,10.11.2026:143/143 объявленных dev-probes по сбоям/границам; отдельно2 native A/C setup→adapter_unavailable/error/no money/0chat и2 actual bounded-worker checks с входом/timeout/отсутствием поздней записи. В143 входят67B/input/search/gates,15calculator-only,20явных A/C mock,17history,17own scenario,7real-source variants (включая8publication unknown).728/728unit (710+18), checkers03–14/old gold04/07/corpus05/5legacy, freeze134files/28resources и replay прошли. Первые ошибки стенда/ос.link sandbox/SQLite cleanup сохранены и исправлены; production/старые данные/gold/manifests/UI неизменны. Chat0, новых real Fact/publication/rights/human_reviewed0; это не benchmark/LLM quality/security proof. Промт16 подготовлен,16 не запускался; merge не поручен.

Git-доставка: evaluation/kp3_15_2026-11-10/git-publication.json и финальная локальная квитанция. Протокол14 не переписан.

**КП3-14,10.11.2026: заморожен контролируемый known-corpus протоколv1 до итоговых ответов.92 случая:20 own07 calculator dev/40 real comparison forms (32numeric+8refusal)/8 input/12 scenario/12 robustness plans;29 уникальных SearchSpec/46 Evidence targets.51 финансовый gold Fraction/integer+Decimal80 и12 own scenario paths independent oracle.710 unit (657 прежних+53 evaluator), checkers03–14/gold04/07/corpus05/5legacy прошли.40 форм проверены только binding,8parser,2own calculator dev-controls,4прежних actual13 envelopes для grader; replay двух явно модифицированных unit fixtures совпал побайтово, не принят как actual. Новых model calls0/comparison attempts0;120primary/18warm не выполнялись. Freeze072a1caf92423d2e41ae12625cc485d81f0bc3c321c3cce5cbb1db663bcf1fbe связывает134file hashes/28actual resources.32 exact cells/28economic contexts/8versions/2lineages из известных48 Fact, holdout/unseen0. Original/comparative/comparability/publication/rights/human_reviewed не повышены; real trading закрыт. Old src/UI/data/gold/manifests сохранены. Промт15 подготовлен;15/16 не начаты, merge не поручен.** [Протокол14](docs/kp3/evaluation_protocol_v1.md). [Промт15](prompts/kp3_15_failure_boundaries.md).

**КП3-13,10.11.2026: новая изолированная P0-оболочка B/C/A, форма5операций/русский ввод/уточнения, Answer/Evidence/страницы, scenario12, готовность/exact-восстановление, атомарная собственная история и JSON/Markdown.657 unit (620 прежних+37 новых),14 AppTest, checkers03–13/old gold04/07/corpus05/5legacy прошли.104 real product cases над прежними48 Fact совпали с независимым reference07+Decimal80,104 повторных lookup без запуска,8 historical blocked. Реальная CUA включила настоящий A1chat/C5chat по одному известному семейству, повтор/архив без модели, downloads, exact PDF/уточнения/false premise/own signal/no signal/real blocked.12 UI records,5 финансовых reference и2 own scenario/6 reference paths; модель затем остановлена. Ноутбучный1280×720 без горизонтального overflow. Новых real Fact/publication/human_reviewed/прав/пакетов/моделей0; предыдущие ядра/данные/gold/manifests/UI09/12 неизменны. Все проверки известные dev, не benchmark/unseen; старые QA07 C/call_limit/3из10/reserved0 сохранены. КП3-14 не начат, промт14 подготовлен; остановка перед14, merge не поручен.** [Продукт и запуск13](docs/kp3/product_ui_v1.md). [Промт14](prompts/kp3_14_evaluation_protocol_freeze.md).

**КП3-12,10.11.2026: scenario service/явный финансовый bridge07-11 и новый изолированный UI.620 unit (584 прежних+36 новых), checkers03–12/old gold04/07/corpus05/5legacy,19 новых CLI и6 отдельных AppTest прошли.24 own параметрических dev-cases/72 пути (signal/cash/hold) полностью сверены Fraction/integer cents+Decimal80,8 real versions blocked с причинами,2 прежних actual C/A envelopes заново допущены без модели. Реальная CUA проверила own positive/curve/ledger/comparisons/false signal/stale reset/error/real blocked/trace. Новые2 own synthetic Fact/1 собственный текстовый документ, реальные48 Fact/8 PDF/unknown publications/human_reviewed0 сохранены. Scenario model_calls0, новых моделей/пакетов/реальных сделок нет. Legacy0.1 неизменён. Не benchmark/freeze14. По последнему поручению после доставки12 сразу выполнить13 в новой ветке, перед14 остановиться; merge не поручен.** [Сценарий и запуск12](docs/kp3/conditional_scenario_v1.md). [Промт13](prompts/kp3_13_product_ui_history_export.md).

**КП3-11,10.11.2026: настоящий одношаговый A — один основной поиск, один выбор модели по найденным metadata IDs/ролям/operation, затем неизменные gates/калькулятор07. Нет C-цикла/repair/B fallback. 584/584 unit (546 прежних+38 новых), checkers03–11/старые gold04/07/corpus05/5legacy и CLI06/07/08/B09,30 новых A CLI прошли. Из11 real-source dev-кейсов9 numeric совпали с независимым Fraction/integer07+Decimal80,2 остановились до модели;9chat. Отдельно1 own synthetic настоящий LLM-выбор→unsupported/nonpositive_base. Всего42 A executions,17actual chat (16real-source+1own),16numeric reference checks;38primary/34validation search calls наблюдены. Повторных model choices/repair не было, все исходы/первые ошибки сохранены. Все семьи известны разработчику, не quality benchmark/unseen/freeze14. Новых real Fact/публикаций/прав/human_reviewed/моделей нет;8 publication unknown, historical/trading закрыты. UI09 unchanged. Промт12 сохранён,12 не начат, merge не поручен.** [A и запуск11](docs/kp3/one_shot_a_v1.md). [Самостоятельный промт12](prompts/kp3_12_conditional_scenario.md).

**КП3-10,10.11.2026: настоящий локальный C через прежние Qwen3:4b/Ollama0.40.15, bounded tool protocol0.2/Answer0.2, финальный prompt v2. До поиска нет Fact IDs; после поиска модель выбирает найденные IDs и роли, программа проверяет источник/контекст/расчёт07/текущий receipt.546 unit (506 прежних+40 новых), checkers03–10/старые gold04/07/5legacy/9 новых C CLI прошли. Финальная real dev-матрица10/10:8 numeric +2 early missing,41 chat; все preliminary/CLI/probe попытки сохранены отдельно:37 real runs/148 chat,28 numeric references Fraction/integer+Decimal80. Это известные повторяющиеся dev-задачи, не benchmark/accuracy. QA07 старого C остаётся error/call_limit; публикации8 unknown, новых Fact/прав/human_reviewed нет. UI09 unchanged. A11 не начат, merge не поручен.** [C и запуск10](docs/kp3/agent_c_v2.md). [Самостоятельный промт11](prompts/kp3_11_single_step_a.md).

**КП3-09,10.11.2026: единый fixed B service/Answer0.1 и новый изолированный Streamlit UI. Обязательный поиск06 предшествует exact Evidence resolution/source checks/калькулятору07, skipped/error/clarification видимы.506 unit (467 прежних+39 новых),7 отдельных UI AppTest,37 новых CLI/checkers03–09/5legacy прошли;5 own+104 real known service-cases совпали с независимым reference07/Decimal80. Реальная CUA-проверка формы/ввода/уточнений/пяти операций/предпосылки/источника/сброса/historical/conflict/missing/technical error сохранена. Новых real Fact/модели нет, все8 publication unknown, historical закрыт. Не benchmark/freeze14. Только ветка09/зависимый PR в08, без merge.** [Сервис и запуск09](docs/kp3/fixed_service_b_v1.md). [Самостоятельный промт10](prompts/kp3_10_real_agent_c.md).

**КП3-08,10.11.2026: ограниченный детерминированный русский ввод, структурированная форма/адаптер и явные уточнения; отдельные Input/Form/Binding0.1 и узкая проверка передачи в Request0.3.467 unit-тестов (403 прежних+64 новых), checkers03–08,5 legacy CLI и117 новых CLI прошли.76 собственных открытых input-cases с отдельно заданными expected;15 числовых real probes совпали с независимым reference07/Decimal80. Original_question/выбор/предпосылка/история сохранены; causal why не выдумывается. Все8 publication unknown/historical закрыты; новых real Fact/моделей/UI/сервиса нет. Только ветка08/зависимый PR в07, без merge, не benchmark/freeze14.** [Грамматика/контракты/запуск08](docs/kp3/russian_input_v1.md). [Промт09](prompts/kp3_09_fixed_service_b.md).

**КП3-07,10.11.2026: пять зарегистрированных финансовых операций и отдельные Request/Calculation/Outcome0.3; старые0.1/0.2/finance.py/CLI сохранены.403 unit-теста (363 прежних +40 новых), checkers03–07,5 legacy и40 новых CLI прошли.160 real и45 собственных synthetic dev-случаев:199 числовых Fraction/integer эталонов совпали с Decimal80/HALF_UP,6 ожидаемых отказов. Это открытые известные dev-проверки над прежними48 real Fact, не новые факты/качество модели/итоговый freeze. Все8 publication unknown, historical закрыт; automatic candidates не допущены. Только ветка07/зависимый PR в06, без merge.** [Методика и запуск07](docs/kp3/calculator_v03.md). [Промт08](prompts/kp3_08_russian_input_and_clarifications.md).

# Проверяемый анализ финансовой отчётности

**КП3-06,10.11.2026:** [извлечение/поискv1](docs/kp3/extraction_retrieval_v1.md), два отдельных индекса: prepared56/56 полных dev-задач; automatic40/48 целевых ячеек и6/8 документов,8 неподдержанных ячеек не скрыты.363 unit-теста и5 legacy CLI прошли; новых Fact/финансовых формул/моделей нет. [Следующий промт07](prompts/kp3_07_expand_financial_calculator.md). Publication unknown, historical закрыт; зависимая Git-доставка в05 без merge.


**КП3-05,09.11.2026:** [реальный подготовленный корпусv1](docs/kp3/corpus_v1.md):8 PDF-версий/48 проверенных ячеек,39 сочетаний группа/показатель/период без версии.334 теста и5 прежних CLI прошли; все публикации unknown, исторические сценарии закрыты. Это ручная подготовка данных, не общий extractor/новый калькулятор/benchmark модели. [Промт следующего КП3-06](prompts/kp3_06_generalize_extraction_and_search.md). Git-доставка зависит от открытого PR04, merge не выполнен.


**Текущая политика GitHub,09.11.2026:** репозиторий [публичный](https://github.com/AlexeyV10/financial-report-agent), изменения main — только через PR. [Активный ruleset](https://github.com/AlexeyV10/financial-report-agent/rules/26853277) запрещает прямые push, force push и удаление main без bypass-исключений. Обязательных одобрений0. [Как работать через ветки](docs/github_collaboration.md). Прежние упоминания приватного состояния относятся к первоначальной загрузке.


Учебный проект: «Агентный ассистент для проверяемого анализа финансовой отчётности и моделирования торговых решений для бизнеса».

**КП3-04,09.11.2026:** подготовлены [финансовый словарь и эталонная методикаv1](docs/kp3/financial_method_v1.md),62 собственных открытых dev-кейса и независимый gold; все22 числовых эталона сверены двумя способами. 314 unit-тестов и5 legacy CLI прошли. Новый production-калькулятор не реализован. [Следующий промт — КП3-05](prompts/kp3_05_curate_verified_corpus.md). Ветка04 зависит от ещё открытого PR03; main без поручения не сливается.

**КП3-03,09.11.2026:** добавлены [общие Task/каталог и контракты0.2](docs/kp3/contracts_v02.md), явный адаптер v0.1 и собственные synthetic примеры. Это выбор входов без новых формул/parser/общего сервиса. Проверки:303 теста ядра/контрактов, семь CLI и пять проверок совместимости неизменённого локального UI. [Следующий промт — КП3-04](prompts/kp3_04_financial_dictionary_and_method.md). Материалы КП3-01/02 остаются отдельно локальными и в этот PR не входят.

**Фактически проект делает пользователь вместе с Codex.** Пять именных ролей сохранены только для регламента; проверки и подписи остальных лиц не требуются. Все содержательные согласования — только с пользователем. Правила — [workflow](docs/workflow.md), результат — [STATUS](STATUS.md).

Шаги 2–14 выполнены в описанном учебном объёме. Текущий код восстановлен и проверен в отдельных папках/venv на этом компьютере. [Инструкция запуска и восстановления](docs/local_demo.md), [технический ZIP](delivery/kp2-local-step13-v1-2026-11-09.zip), [receipt](delivery/kp2-local-step13-v1-2026-11-09.receipt.json). Фактическое состояние — [STATUS](STATUS.md).

## Совместная работа на GitHub

Публичный репозиторий: [AlexeyV10/financial-report-agent](https://github.com/AlexeyV10/financial-report-agent). По новому запросу пользователя09.11.2026 проект загружен на GitHub, аккаунту kostyaNegoday отправлено приглашение с правом вносить изменения. Пока приглашение не принято, доступ участника не считается активным. [Клонирование, запуск и работа через ветки](docs/github_collaboration.md). Это возможность дальнейшей совместной работы, а не приписывание новому участнику прежнего вклада.

В репозитории — собственный код, документация, тесты, разметка, материалы КП2 и проверенные архивы. Первичные PDF/страницы/полный текст, индекс, веса модели и ключи исключены. Публикация на GitHub не означает сдачу КП2 в вуз.

## Готовые материалы КП2 — шаг14

[Отчёт и презентация с описанием файлов](materials/kp2_2026-11-09/README.md): редактируемый DOCX10 страниц и PPTX5 слайдов, оба со своими PDF; речь, демонстрация и текстовый исходник. [Пакет материалов](delivery/kp2-materials-step14-v1-2026-11-09.zip) и [receipt](delivery/kp2-materials-step14-v1-2026-11-09.receipt.json) — отдельно от прежнего технического архива, который не менялся. КП1 сохранена.

Все страницы и слайды просмотрены после нативного экспорта, числа/знаменатели сверены с прежними результатами; доказательства — evaluation/step14_2026-11-09/. Новых вызовов модели не было. Речь228 слов, примерно2мин по расчёту; текущий регламент неизвестен, реальное выступление пользователя не замерялось. Ошибка Ctop1 и ограничения одного PDF/одного числового dev-вопроса сохранены.

В форму курса материалы не отправлены. Следующий шаг основного плана —15, [самостоятельный промт сдачи и сохранения подтверждения](prompts/step15_submit_and_preserve_receipt.md). Нужно уточнить действующие требования и конкретный канал отправки только у пользователя; проверки других участников не требуются. Для дальнейшей работы с кодом через GitHub подготовлен [отдельный промт](prompts/github_continue_collaboration.md).

## Восстановленная демонстрация — шаг13

В новых копиях прошли **267 unit-тестов (255 прежних +12 архива)**, 8 минимальных/4 поисковых интеграционных случая и один normal настоящего C/LLM. Для модели:5 решений,19120/268 токенов,14,611с всего CLI; это проверка запуска на том же компьютере, не новая метрика качества. Сервер остановлен. Прежние финансовые исходники/тесты/данные и frozen questions не менялись.

Пример без PDF/модели из корня восстановленной папки:

```powershell
python -I scripts\run_local.py fixed --source manual
```

```powershell
python -I scripts\run_local.py scenario
```

Оболочка run_local.py поддерживает fixed/agent/scenario/questions/replay и явные adapter/source. Она исправляет импорт соседнего CLI при -I, не выполняет произвольные команды. Минимальная проверка — python -I scripts/check_local_demo.py minimal. ZIP не содержит PDF/индекс/полный текст/веса/бинарники/секреты; личные source/LLM-ресурсы подключаются отдельно по инструкции. MSYS2 venv здесь использует bin/python.exe, обычный Windows Python — Scripts/python.exe; восстановитель создаёт пустую рабочую tmp/. Эти зависимости проверены, исходные сбои сохранены в evaluation/step13_2026-11-09/.

Первый малый замер шага12 сохраняет B/C1/1 на одном числовом вопросе и отказы B2/2/C1/2: top1 Ccall_limit — ошибка. Поддержаны только3/10 financial, все парные вопросы dev/open; общего/слепого финансового бенчмарка и превосходства C нет.

## Первые реальные измерения — шаг 12

[Таблицы, методика и ограничения](docs/measurements.md), [сырые результаты и оценки](evaluation/step12_2026-11-09/run-02-environment-retry/results.json). Первый проход run-01 сохранил ошибку доступа сервера к модели до генераций; run-02 — отдельный объявленный повтор после разрешённого запуска того же сервера вне песочницы. Промпт/модель/входы/лимиты/gold не менялись. Все неуспехи сохранены.

| Финансовые метрики, одинаковые задачи | B | C/LLM |
|---|---|---|
| Числовой вопрос QA03 | 1/1 | 1/1 |
| Отказы QA06/QA07 | 2/2 | 1/2 |
| Подтверждённые числовые claims QA03 | 4/4 | 4/4 |

UI01 — отдельно 1/1 у обоих, finance API — отдельно 2/2, synthetic simulator — отдельно 2/2. Поиск одного query: k1 покрывает 0/2 Evidence, k5 — 2/2. Reserved financial B/C — не измерено (n=0). В run-02 было 17 chat-запросов, 39000/849 фактических входных/выходных токенов; стоимость не измерена. После прогона сервер остановлен.

Пересчёт без модели/поиска/симулятора:

```powershell
python scripts\measure_step12.py replay --run-dir evaluation\step12_2026-11-09\run-02-environment-retry
```

**255 unit-тестов (231 прежний +24 оценщика), 8 CLI-проверок прошли.** Совпадение offline replay дополнительно проверено с запретом socket и production-ответчика. Все37 прежних файлов кода/данных и frozen-набор сохранены. Это отдельные проверки кода, не дополнительные вопросы качества. Новых скачиваний/облака/торговли/настройки по резерву не было.

## Проверочные вопросы — шаг 11

**13 записей:** 10 финансовых QA, 1 интерфейсное уточнение и 2 искусственных сценария. 9 dev/open, 4 reserved; резерв виден Codex, исходные данные уже использовались, слепая независимая оценка не заявляется.

```powershell
python scripts\check_question_set.py
```

[Инструкция и реестр с единицами](docs/question_set.md), [полные эталоны](data/question_sets/kp2_v1/questions.json), [manifest](data/question_sets/kp2_v1/manifest.json). Два реальных числа повторно сверены на свежем рендере того же PDF4; дробная и целочисленная арифметика сохранена отдельно. Страницы/полный текст отчёта только tmp/.

B/C сейчас поддерживают **3/10** финансовых шаблонов и отдельно UI01. Двум synthetic QA доступен finance API, двум сценариям — simulator; пяти задачам нужен новый адаптер. Прямой вопрос, смена масштаба, первоначальная версия2023 или проверка предпосылки не подменяются default growth.

```powershell
python scripts\check_step11.py
```

Исторический итог шага11: **231 unit-тест** (198 прежних +33 новых) и **9 CLI-проверок валидатора**. Все37 прежних файлов кода/данных побайтно сохранены. На момент подготовки набора новых ответных/модельных запусков question set не было. [Доказательства](evaluation/step11_2026-11-09/report.json). Последующие измерения шага12 хранятся отдельно; замороженные вопросы/history не переписывались.

## Искусственный виртуальный сценарий — шаг 10

Из корня проекта, без модели и сети:

```powershell
python scripts\simulate_scenario.py
```

```powershell
python scripts\simulate_scenario.py --save output\synthetic-scenario.txt --trace output\synthetic-scenario.trace.json
```

Все входы вымышлены и явно помечены: выручка 100→120, капитал 10000 RUB, лимит номинала 20%, комиссия 1 RUB на сторону, slippage 0. Контроль: после покупки 7999, после продажи 10098 RUB / +0,98%; удержание той же доли даёт тот же итог. Это проверка арифметики, не доходность рынка и не преимущество стратегии.

```powershell
python scripts\simulate_scenario.py --case real-source
```

Настоящий источник отдельно даёт blocked/publication_unknown, без сделок/показателя доходности и подстановки вымышленных дат. Старый финансовый gate не разблокируется.

**Историческая проверка шага 10:** 198 unit-тестов (161 прежний +37 новых), 25 CLI и 4 регрессии B/C_mock прошли; модельных вызовов 0. [Инструкция](docs/simulation.md), [пример](evaluation/step10_2026-11-09/demo-synthetic.txt), [отчёт](evaluation/step10_2026-11-09/report.json).

```powershell
python scripts\check_step10.py
```

## Локальный агент — шаг 9

Из корня проекта в PowerShell 7.4+:

```powershell
.\scripts\local_model.ps1 start
```

```powershell
python scripts\agent_assistant.py --adapter ollama --trace output\agent-trace.json --save output\agent-answer.txt
```

Переносимая Ollama 0.40.15 и qwen3:4b уже скачаны с разрешения пользователя в исключённую tmp/local-model/. Облачные функции отключены, адрес только 127.0.0.1:11435; платных API нет. После проверок сервер остановлен. Остановить свой сервер: .\scripts\local_model.ps1 stop. Без модели отдельно работает прежняя команда ниже.

Для явного имитатора: python scripts/agent_assistant.py --adapter mock. Модель и mock выбираются отдельно, автоматической подстановки нет. Лимиты — 6 решений, 180 секунд всего / 90 на ожидание; финальный текст только через прежние финансовые валидаторы.

**Проверки:** 161 unit-тест, 16 CLI-сценариев, 9 парных B/C_mock. Реальная модель дала валидированный ответ/отказ в двух из трёх открытых демонстраций; top1 — известный неуспех call_limit. Это не оценка качества на закрытом наборе. Подробности/известные неудачи/команды: [docs/agent.md](docs/agent.md), [report.json](evaluation/step9_2026-11-09/report.json).

Статистика выше — исторический протокол шага 9. Его строгий check_step9.py привязан к прежним байтам user_path.py; после объявленного изменения последней фразы используйте текущую check_step10.py. Старые before/report не переписывались. При необходимости отдельного нового запуска LLM используйте agent_assistant.py --adapter ollama и сохраните новый trace; он не требуется для симуляции. Полные PDF/индекс/hits/веса/бинарники не входят в отчёты/архив; v2 остаётся снимком шагов 2–5.

## Пользовательский запуск — шаг 8

Из корня проекта:

```powershell
python scripts\assistant.py
```

Одна команда запускает явно ограниченный сценарий: группа «ФосАгро», МСФО, выручка 2024 к 2023, выбранная версия и локальный поиск. ID фактов вводить не нужно. Показываются оба полных периода, исходные суммы/единица, +67 385 млн руб. и +15,30%, формула, оба локатора и версия, а также ограничения данных.

```powershell
python scripts\assistant.py --save output\user-answer.txt
```

Для исторического запроса добавьте --mode historical --as-of 2025-02-14T10:00:00+03:00; он честно отказывает из-за неизвестной публикации PDF-версии. Явный --source manual использует прежний ручной реестр без текущего поиска; ошибки обычного режима не переключают его автоматически. Другие компания/показатель/период требуют уточнения и не подменяются текущим примером.

Нужны уже имеющиеся локальные PDF и индекс; создание описано ниже. Коды завершения: 0 — ответ или финансовый отказ, 1 — уточнение запроса, 2 — техническая ошибка. Это шаблон сценария, не понимание произвольного русского вопроса.

Подробности: [docs/user_path.md](docs/user_path.md). Свежие проверки: `python scripts/check_step8.py`, отчёты в `evaluation/step8_2026-11-09/`. Прошли 127 unit-тестов и 23 CLI-сценария; пример ответа — `evaluation/step8_2026-11-09/demo-answer.txt`. Формула, финансовые факты и прежние инструменты не менялись.

## Запуск на Windows

Откройте PowerShell в корне проекта. Расчёты, поиск и тесты проверены на CPython 3.14.7 и используют стандартную библиотеку. Для извлечения PDF отдельно проверен комплектный Python 3.12.14 с pdfplumber; команды ниже. Установка пакетов и ключи для текущего локального запуска не нужны.

```powershell
python scripts\check_stage1.py
```

Ожидается 4/4: обычный ответ, missing для отсутствующего значения, conflict для несовместимых периодов, missing для неизвестной публикации в историческом режиме. Реальный пример: 440 304 → 507 689 млн RUB; +67 385 млн RUB; +15,30%.

```powershell
python -m unittest discover -s tests -v
```

Ожидается 267 тестов: 255 прежних +12 архива. Это проверки кода/контрактов/арифметики/времени/ссылок/ограничений, не дополнительные вопросы оценки LLM или рынка. Для отдельной распаковки сначала создайте пустую tmp/ (package_project.py restore делает это сам). source_checked_by_assistant сообщает происхождение фактов, human_reviewed без пользовательской сверки не проставляется.

Историческая проверка компонента шагов 2–5 (не основной отчёт шага 6):

```powershell
python scripts\check_review.py
```

Результаты шагов 2–5 — `evaluation/solo_workflow_2026-11-09/`; текущие результаты шага 6 — `evaluation/step6_2026-11-09/`. Более ранние отчёты в `evaluation/` и `evaluation/recheck_2026-11-09/` — история. Скрипты не скачивают PDF и не выполняют повторную визуальную сверку. При отсутствии локального источника проверяется согласованность JSON, а не истинность ячеек.

## Файлы

| Путь | Назначение |
|---|---|
| `docs/first_scenario.md` | Вопрос, границы и ожидаемый ответ |
| `docs/source_verification.md`, `docs/acceptance_recheck.md` | Протоколы проверки источника и дат |
| `docs/contracts.md` | Document, Evidence, Fact, Calculation, Answer и черновой Scenario |
| `docs/acceptance.md` | Технический итог без пяти именных проверяющих |
| `docs/workflow.md`, `AGENTS.md` | Постоянные правила: пользователь и Codex |
| `data/examples/` | Минимальная ручная разметка и четыре случая |
| `src/financial_assistant/contracts.py`, `tests/` | Валидаторы, расчёт и тесты |
| `scripts/prepare_manual_fixture.py` | История ручного ввода, не PDF-парсер; не запускать поверх изменённой разметки без просмотра изменений |
| `scripts/build_review_archive.py`, `packaging/stage1_files.json` | Архив по явному списку и проверка распакованной копии |
| `docs/transfer.md` | Сохранение и восстановление локального пакета |

Рабочее место — локальная папка и архив пользователя. Общий remote и доставка другим людям не являются зависимостью. Текущий технический пакет — `delivery/kp2-local-step13-v1-2026-11-09.zip`, хеш/проверки — в одноимённом `.receipt.json`, инструкция — docs/local_demo.md. Старые stage1-local-v2 и v1 сохранены как история шагов2–5; прежняя политика пяти проверяющих отменена.

Первичные PDF, PNG и полный извлечённый текст остаются в исключённой `tmp/` и не входят в архив. Публикация именно выбранной PDF-версии неизвестна: анализ снимка допустим, исторический сценарий заблокирован. Права на повторное распространение копии не подтверждены. Человеческая проверка, заказчики, внедрение и метрики модели не выдумываются.

## Документы и поиск — шаг 6

Подробные команды, ограничения и формат выдачи — [docs/retrieval.md](docs/retrieval.md). В основном Python 3.14.7 работает SQLite FTS5; worker извлечения проверен отдельно на комплектном Python 3.12.14 / pdfplumber 0.11.9, без установки пакетов. Дополнительные версии записаны в requirements-pdf.txt. Это две среды, не заявление о работе PDF-пакетов в основном Python.

При первом запуске, если индекс отсутствует:

```powershell
python scripts\search_documents.py index --pdf-python "C:\Users\Value\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
```

Если индекс уже создан, выполняйте только поиск:

```powershell
python scripts\search_documents.py search --query "выручка 2024 2023" --period 2024 --top-k 5 --output tmp\retrieval\real-result.json
```

Нужная левая половина PDF-страницы 4 находится второй в пяти результатах. Выдача сохраняет заголовки, годовые столбцы, единицу, строку, документ/хеш и ссылку. Кандидаты не превращаются в подтверждённые факты. Фильтр года ограничен размеченными 2023/2024; это не проверка финансовой сопоставимости.

```powershell
python scripts\check_step6.py
```

Получены 23 страницы / 46 фрагментов. Пять поисковых smoke-случаев и 68 unit-тестов прошли; отчёт не содержит полного текста источника. Экспорт/индекс/поисковые JSON с цитатами остаются только в исключённой tmp/. Без PDF/worker либо при смене версии показывается техническая ошибка, не отсутствие финансового показателя. Ручной резерв выбирается только явным --manual и ищет лишь в минимальной прежней разметке.

Текущий код шага 6 — src/financial_assistant/retrieval.py, scripts/extract_pdf.py, scripts/search_documents.py и tests/test_retrieval.py. Архив stage1-local-v2 содержит только снимок шагов 2–5 и не пересобирался; новые файлы находятся в рабочей папке. Публикация PDF остаётся неизвестной, исторический поиск запрещён. Модели и агента нет, метрики их качества не измерялись.

## Финансовый инструмент — шаг 7

Подробный контракт и ограничения — [docs/finance.md](docs/finance.md). Арифметика осталась в contracts.answer; второй калькулятор не создавался. Прямой вызов работает на прежнем ручном реестре и не требует PDF/индекса:

```powershell
python scripts\calculate_financial.py calculate --previous-fact phosagro-revenue-2023 --current-fact phosagro-revenue-2024
```

Для проверки связи с живым локальным поиском:

```powershell
python scripts\calculate_financial.py from-search --previous-fact phosagro-revenue-2023 --current-fact phosagro-revenue-2024 --output output\finance-result.json
```

Выбирается доказательство из второго результата, а не первое примечание. Используются оба прежних Fact/Evidence, не числа из candidate.text; при неполном покрытии отказ, без скрытого прямого расчёта. Результат: +67 385 млн RUB и +15,30%, с обоими входами, периодами, формулой, строкой/колонками и ссылками. Исторический режим с --mode historical_as_of --as-of 2025-02-14T10:00:00+03:00 сохраняет missing/publication_unknown.

```powershell
python scripts\check_step7.py
```

Текущие результаты — evaluation/step7_2026-11-09/: 98 тестов и 11 CLI-сценариев, включая отдельные синтетические fixtures. Прежние отчёты шагов 2–6 сохранены как история. Минимальные вычисленные ответы могут сохраняться под output/ или tmp/; полного текста первичного документа/hits в них нет. Понятный единый CLI теперь есть на шаге 8; свободного разбора вопроса, агента и симулятора пока нет. Архив v2 по-прежнему только снимок шагов 2–5.
