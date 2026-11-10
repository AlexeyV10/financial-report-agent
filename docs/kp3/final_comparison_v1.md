# КП3-16: фактическое сравнение известного корпуса

На данном наборе B, A и C дали одинаковую строгую финансовую точность. Добавление модели не улучшило результат и увеличило время. Это вывод об ограниченном прототипе и подготовленных входах, не оценка рынка, unseen-документов или общего финансового мышления модели.

| Основной этап, 40 форм каждому | B | A | C |
|---|---:|---:|---:|
| Строгий числовой ответ | 32/32 | 32/32 | 32/32 |
| Правильный request/financial отказ | 8/8 | 8/8 | 8/8 |
| Техническое завершение | 40/40 | 40/40 | 40/40 |
| Полнота обязательных утверждений | 32/32 | 32/32 | 32/32 |
| Поддержанные наблюдённые typed claims | 86/86 | 86/86 | 86/86 |
| Медиана полного вызова, с | 0,207 | 2,459 | 5,496 |
| Настоящие chat-запросы | 0 | 34 | 159 |

Отдельные6 повторов каждому:6/6 строгих ответов,6/6 семантически совпали с первыми исходами; A6chat/C28chat/B0. Их медианы0,210/2,483/6,642с соответственно B/A/C. Это повтор тех же6 вопросов, не дополнительные18 уникальных примеров. Warm refusal n=0 остаётся not_measured.

Всего **138/138** запланированных попыток, **227** actual chat (A40+C187), unknown requests0, known output12990tokens. Основные120 и18warm идут ровно по frozen seed20261110/order; повторов/ремонта/замены первых outcomes нет. Реальная модель Qwen3:4b/Ollama0.40.15 с прежними digest/executable SHA; mocks/replay/B под A/C не использовались. Все финансовые значения считает общий зарегистрированный07, не текст модели. A выбирает по metadata; C может получить checked values и принимает bounded tool decisions. Это разные раскрытые условия, а не три свободных QA-метода.

Перед первым ответом запечатан `evaluation/kp3_16_2026-11-10/run-manifest.json`, SHA256 `9fe1686fa127b5e70ff34d05f459296d03c1b81bdfbca14ec8dc229768e5d3fa`:7 новых measurement/CLI/test файлов, setup hashes, environment, order, budget, limits и28 source/model descriptors. Финансовый freeze14 `072a1caf92423d2e41ae12625cc485d81f0bc3c321c3cce5cbb1db663bcf1fbe` и все134 файла/28ресурсов совпали до/после. Новый measurement package не является изменением answering src или нового financial bundle. Gold/ожидаемые поля не поступают в методы.

Перед каждым вызовом сохранён фактический `/api/ps`:1cold и137warm наблюдений. Это состояние загрузки модели, не холодный кэш PDF/FTS/ОС; у B модель не используется. Фаза warm_repeat сама не служит доказательством warm. Время измерено perf_counter вокруг полного зарегистрированного метода, включая его внутренние workers/guards; API model-state, reservation/serialization и общая подготовка ресурсов вне этого интервала. Для B применяется объявленный180с outer process guard. Trace содержит фактические стадии и skipped, A отдельно primary/validation searches, C — tool/decision/receipt/finished. Hardware: i7-14700HX/20cores28threads, около16GB RAM, RTX5060Laptop плюс integratedGPU; это одна локальная машина. Полные стоимость/электричество и переносимость времени не измерены.

Каждый slot сначала получает fsync/exclusive claim и отдельный run_id/run_dir, raw публикуется atomically без overwrite. OS lock не допускает второго runner. При прерывании можно восстановить только сохранившийся первый typed Answer; иначе фиксируется interrupted unknown, без нового вызова модели. После завершения выполнен no-op resume уже при остановленной модели:138 raw и progress байты не изменились, новых попыток0. Это реальная проверка завершённого resume, а не заявление об испытании всех видов process crash. Соответствующие interrupted/budget/gap/identity ветки покрыты32 собственными unit fixtures.

`raw-manifest.json` связывает138actual observations с freeze. Два независимых offline replay дали побайтово одинаковые metrics; дополнительный supplement replay тоже совпал. Строгая оценка проверяет статус/полные поля задачи, источники/Evidence/страницу/SHA/ячейку/единицы/версию, формулу/точный результат/округление, предпосылку/why/unfulfilled и order/skipped. Gold14 остаётся прежним Fraction/integer+Decimal80, не вызовом production answer. Ошибок по этим frozen typed criteria0; это не доказательство правильности произвольной свободной прозы. Claim support делит на наблюдённые claims, полнота использует все32 обязательных числовых ответа.

Особенность frozen v1 агрегатора usage: у A:primary поле `tokens.unknown_records=12` считает два null token-поля у6 ранних отказов без chat. Это **не12 неизвестных запросов**. Null сохранены, не заменены на0; actual unknown requests0. Название/семантика счётчика — ограничение измерения, возможное уточнение новой версии17, не причина молча переписывать frozen metrics16. Known token totals отражают только сообщённые provider значения.

Отдельные линии проверки не добавляются к40:

- Own07 calculator-only dev:20/20, в том числе19numeric и1unsupported/nonpositive CFO base. Не B-search по synthetic issuer PDF.
- Parser:8/8 hand-specified semantics/clarifications, не40 свободных русских вопросов.
- Prepared retrieval:29/29 полных уникальных queries,46/46 exact Evidence targets. Это не дополнительный финансовый ответ.
- Automatic:40/48 целевых ячеек,6/8 документов;8 неподдержанных остаются в n, ещё8 квартальных candidates вне Fact. Повторён geometry/lexicon над прежними8 pinned worker exports; новых worker/PDF parsing/OCR0. Успешное чтение JSON не объявляется новым извлечением PDF.
- Scenario:12/12 по независимому reference12:4completed own,7blocked,1expected error; все4real readiness остаются publication_unknown с6gaps. Own prices/calendar не подставлены под issuer.
- Robustness:переиспользованы sealed143probes15 (20 явных A/C mock отдельно от реальных native offline2 и worker2). Не новые12runtime attacks16. UI16 unchanged; новая CUA не проводилась, прежняя UI13 проверка остаётся прежней.

32exact cells из известных48,28economic contexts,8PDF versions,2real lineages; holdout/unseen0. Уже известные03–15 data/templates не становятся независимыми от присвоения split. Prepared pool часто однозначен, все методы делят источник и калькулятор. Поэтому100% этого набора не обобщаются на новые компании/макеты/язык. OP двух групп имеет разный report-defined состав; Segezha2021 CFO original/comparative не исправлены и не объявлены эквивалентными. Все8 публикаций unknown, права primary неизвестны, human_reviewed0. Реальная торговля/исторический допуск по-прежнему закрыты.

Регрессия:760/760unit (728 прежних+32 runner); checkers03–14/old gold04/07/corpus05/5legacy прошли. Артефакты15 проверены по прежнему manifest/хешам, не заменены новым mock-прогоном. Первые setup ошибки сохранены: CIM sandbox denied→настоящая эскалация того же read-only запроса; первый Markdown имел пустые строки между rows→отдельная исправленная таблица, JSON analysis до/после побайтово совпал. Frozen runtime/gold не исправлялись по outputs16. Старые QA07 C/call_limit=error,3/10financial,reserved0 остаются прежними измерениями.

Подробные результаты/время/usage/errors: `evaluation/kp3_16_2026-11-10/metrics.json`, `analysis-final.json/.md`, supplement/replay receipts. Статус/доставка — git-publication и финальная локальная квитанция. Промт17 подготовлен отдельно;17/release fixes не выполнялись, merge не поручен.
