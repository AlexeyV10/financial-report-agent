# Зарегистрированный финансовый калькулятор0.3 — КП3-07

Калькулятор выполняет пять операций над допущенными Fact каталога0.2. Числа берутся из выбранных Fact, финансовый смысл — из проверенных definitions/source bindings05. Русский вопрос пока сохраняется как текст: parser, выбор намерения, общий сервис, агент и UI относятся к следующим этапам.

## Версии и операции

Старые Catalog/Task/Outcome0.2, адаптер0.1, `finance.py`, `calculate_financial.py` и `annual_growth_v1` сохранены байт в байт. Новый отдельный интерфейс Request/Calculation/Outcome имеет `schema_version="0.3"`; автоматического преобразования старых Task в него нет. Это предотвращает запись процентов в старое денежное поле.

| Название плана | operation_id методики04 | Входные роли в порядке | Выход |
|---|---|---|---|
| get_fact | direct_fact_v1 | fact | amount, исходные валюта/масштаб и десятичная запись |
| absolute_delta | absolute_change_v1 | previous, current | amount, current − previous |
| relative_change | relative_change_v1 | previous, current | percent, (current − previous) / previous ×100 |
| scale_conversion | scale_v1 | fact | amount, исходное значение × исходный масштаб / целевой масштаб |
| operating_margin | operating_margin_v1 | profit, revenue | percent, отчётный OP / revenue ×100 |

`percentage_point` выделен как вид единицы, но операция изменения маржи в п.п. на07 не зарегистрирована. Для пяти операций нельзя подставить п.п. вместо процента. `annual_growth_v1`, EBITDA, FX, FCF, capex и произвольные формулы не являются новыми операциями.

## Запрос и доверенный контекст

Точные поля Request0.3: `schema_version, request_id, original_question, operation_id, organization_id, consolidation, accounting_standard, inputs, version_policy, comparability_id, result_unit, mode, as_of`. Все поля обязательны; `comparability_id/as_of` явно равны null, когда не нужны. В inputs1–2 ссылки: `role, fact_id, document_id, version_id, metric_id, definition_id, period, source_unit`. Полный period и source_unit используют старую проверку0.2; `result_unit` — `{kind:"amount",currency,scale}` либо `{kind:"percent"}`. В запросе нет поля value, formula, пути PDF, URL исполнения или expected. Неизвестные поля отвергаются; недостающие содержательные поля дают `awaiting_clarification`, без defaults компании/года/документа.

Отдельный доверенный `CalculationContext` создаёт локальная программа/CLI, а не модель и не поиск. Он содержит Catalog0.2, словарь04 и admission1.0. Для real обязательны исходные bindings05,48 source-check records и локальная карта ресурсов. Admission связывает canonical SHA-256 каталога/словаря/bindings/checks, происхождение real/synthetic и отдельные comparability records. Загруженные JSON-файлы проверяются по байтовым SHA при каждом вызове. Выбранные реальные PDF проверяются по наличию, длине, сигнатуре и SHA перед арифметикой. Совпадение хеша не заменяет смысловую сверку: каждый real Fact дополнительно сверяется с binding и своим исходным source-check record.

Это контроль целостности доверенной конфигурации, не криптографическая аттестация автора. Если произвольно заменить все доверенные входы и их manifests, программа не может восстановить финансовую истину. Будущий parser не должен создавать/исправлять admissions, значения Fact, source checks или доказательства сопоставимости.

Порядок: строгая форма запроса → целостность и Catalog → организация/IFRS/group/definition → exact-документ/период/единицы/конфликты → checked Fact/Evidence/source binding/первичный source check → фактические байты PDF → публикация/версии/сопоставимость → при подключении проверенный поиск06 → арифметика. Candidate, structure_checked и автоматическая ячейка не повышаются до assistant_checked.

## Смысл, периоды и версии

Поддерживаются definitions04 нефинансовой консолидированной IFRS-группы: точная отчётная выручка, report-defined operating subtotal и конечный signed net CFO после относимых налогов/процентов. Различие состава OP двух групп сохранено в bindings05; оно не означает универсальную межотраслевую сопоставимость. IFRS18 по дате не приписывается. Положительное «использовано» автоматически не инвертируется.

P0 принимает полные стандартные duration: full_year, year_to_date, quarter. Custom и instant в этом калькуляторе не поддержаны; год, накопленные9/6месяцев и отдельный квартал не взаимозаменяемы. Для delta/relative previous идёт раньше current без пересечения, календарные окна и duration_type совпадают. Смежность лет не обязательна: это изменение за явно выбранные периоды, а не автоматический CAGR. Разность накопленных периодов не создаёт квартальный Fact.

Внутри exact-документа сравнение comparative→reported допустимо при явной `explicit_versions`: обе исходные версии колонок показаны в результате. `original_period_documents` отвергает comparative. Для разных документов delta/relative требуют двух reported_period и отдельный доверенный comparability_id, привязанный к обоим document/version/SHA, организации, определению, периоду и проверенным Evidence. Наличие разных SHA само по себе допустимо, но не доказывает сопоставимость. На07 такие положительные записи сделаны **только для собственных synthetic fixtures**; реальных новых доказательств междокументной сопоставимости не заявляется. Отсутствие записи даёт `comparability_not_established`. Сегежа2021 original CFO и comparative2021 из2022 не объявлены эквивалентными; причина отличия не установлена.

Маржа использует OP/revenue одной exact-версии, организации, IFRS, полного периода, валюты и масштаба. Масштаб меняется только `scale_v1`, без валютного курса. `relative_change_v1` требует previous>0;0/отрицательная база — unsupported. Отрицательная OP при положительной revenue допустима; revenue=0/отрицательная — отдельные unsupported причины. Технические ошибки ресурсов/индекса не являются финансовым отсутствием показателя.

Все8 реальных PublicationEvidence остаются unknown/unproven, поэтому snapshot допустим, historical закрыт. Дата получения/подписания/утверждения/HTTP не используется вместо публикации. Для доказанной точной даты в собственном synthetic тесте применяется консервативный допуск со следующей полуночи указанной зоны. Это не дата реального эмитента и не разблокировка торговли.

## Точность и результат

Вход — ASCII decimal string без float/экспонент/NaN. Production преобразует его в целую несократимую дробь и считает целыми. Денежные delta/scale показывают точную конечную десятичную запись без округления до копеек. Direct сохраняет запись Fact (включая значащие хвостовые нули); исходная запись документа, скобки и encoding отдельно сохранены в Evidence. Проценты — HALF_UP до2 знаков на целых, включая отрицательные ties; округлённый отрицательный ноль показывается0.00. Точная арифметика не повышает исходную точность отчёта.

Outcome0.3 разделяет execution_status completed/awaiting_clarification/error и financial_status answered/missing/conflict/unsupported либо null при техническом исходе. Только answered содержит financial_result. Он сохраняет полный структурированный request, admission/context/component digests, входные Fact/Evidence IDs и снимки, document/version/SHA, provenance, оригинальные строки/колонки/страницы/единицы, источники/публикацию/аудит/права, собственное описание зарегистрированной формулы, точные промежуточные дроби/результат, отображение и округление. Refusal, clarification и error не содержат финансового результата.

`validate_outcome` проверяет форму/сочетания статусов; `validate_calculation_binding` повторно разрешает входы и выполняет зарегистрированную операцию, сравнивая **весь** результат с внешним запросом и контекстом, в том числе ложный отказ. Это runtime-проверка, её нельзя считать независимым gold.

## Подключение к поиску06

Опциональный доверенный retrieval guard задаётся отдельными CLI-флагами index/config/lexicon/exports. Из выбранных ссылок строится полный SearchSpec06; это не разбор свободного языка. Prepared индекс должен вернуть все выбранные точные Evidence, их digest/локаторы/контекст/значения повторно сопоставляются с каталогом. Значения для арифметики всё равно берутся из допущенных Fact. Partial не вычисляется; automatic всегда отклоняется как непроверенный источник кандидатов. Неподдержанный макет не удаляет имеющийся ручной Fact: без требования автоматического извлечения проверенный snapshot доступен. Изменённые PDF/index/export/config и отсутствующий ресурс дают техническую ошибку без числа. Сервис/агент на07 не добавлены.

## Проверки и повторение

Публичная проверка без первичных PDF:

~~~powershell
python -I scripts/check_kp3_calculator.py
~~~

Она исполняет45 synthetic случаев и отдельно сверяет205 reference записей; real arithmetic не выполняется без ресурсов. С локальной картой существующих PDF:

~~~powershell
python -I scripts/check_kp3_calculator.py --resources tmp/local-resources.json --report tmp/calculator-check/report.json
~~~

Новый CLI — `scripts/calculate_financial_v3.py --catalog ... --dictionary ... --admission ... --request ...`; real дополнительно требует `--bindings ... --source-checks ... --resources ...`. Опциональный поиск: `--index ... --config ... --lexicon ...`, для automatic ещё `--exports ...`. Все пути — доверенные параметры локального запуска; в request их нет. Выход stdout — Outcome0.3; exit0 completed,2 error,3 clarification. Примеры структурированных запросов — `data/dev_cases/kp3_calculator_v1/`, независимые эталоны — только `evaluation/fixtures/kp3_calculator_v1/`. Runtime не загружает gold/expected/control-calculations.

Новый собственный synthetic каталог содержит9 Fact (6 исходных искусственных и3 явно созданных comparative),2 искусственных документа,3 доказательства сопоставимости собственной конструкции. Fixture overrides в dev-cases применяет только evaluator к **собственным synthetic данным**, с пересозданием Evidence/digests. Это не поле runtime-запроса. `build_kp3_calculator_dev.py` воспроизводит входы/эталоны независимым Fraction reference, не импортируя production калькулятор. Все199 числовых эталонов дополнительно сверены Decimal80/HALF_UP;6 остальных — ожидаемые отказы.

Матрица real160:48 direct +48 scale +24 delta +24 relative +16 margin; одни и те же48 исходных ячеек используются повторно. Synthetic45:39 числовых и6 неподдержанных. Это открытые известные разработчику dev-проверки, не205 независимых наблюдений, не модельные ответы, не unseen benchmark/freeze14. Новых реальных Fact/PDF/публикаций/human_reviewed нет. Старые результаты QA07 C/call_limit,3/10financial и reserved financial n=0 не изменены. Детальные проверки/первые ошибки/сохранность — `evaluation/kp3_07_2026-11-10/`.
