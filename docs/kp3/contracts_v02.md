# КП3-03: каталог и Task v0.2

09.11.2026, Europe/Moscow. Это общий контракт данных и выбор входных фактов. Калькулятор, parser, извлечение PDF, сервис A/B/C и новая история в этом этапе не реализуются. `binding_status=ready` означает, что входы выбраны, а не что финансовый ответ рассчитан.

## Версия и расположение

- `contracts_v2.py`: общие проверки, ошибки, даты/периоды/единицы и отдельный Outcome.
- `catalog.py`: Organization, Metric definition, Document, Evidence, Fact, проверка связей, aliases, поиск по Fact ID и допуск версии по публикации.
- `tasks.py`: Task, обязательные поля, явные версии и выбор входов без вычислений.
- `legacy_adapter.py`: отдельные `catalog_from_v01`, `task_from_v01`, `outcome_from_legacy`.

Формат — обычные JSON-объекты с точным набором полей и `schema_version="0.2"`. Исполняемая спецификация полей — функции `shape` и `validate_*` этих модулей. Дополнительный JSON Schema validator не установлен. Неизвестная версия отклоняется; миграция только явным адаптером. Добавление несовместимых обязательных полей/смысла требует новой версии, а не тихой перезаписи v0.1. Чтение JSON отклоняет дубли ключей, NaN/Infinity и файлы более2МБ; данные не исполняются.

## Каталог не содержит вопроса

Верхние поля: `schema_version catalog_id organizations metrics documents evidence facts`. Здесь нет `request`, `expected`, gold или программы расчёта. Контракт не читает question_sets/evaluator. Текущие метаданные и цифры по-прежнему подготовлены заранее; структурная проверка не подтверждает истинность первичного документа.

| Запись | Обязательный смысл |
|---|---|
| Organization | `organization_id`, имя, непустые aliases, `group` либо `legal_entity`, список IFRS/RAS |
| Metric | ID, `definition_id`, подпись и допустимые виды периода `duration`/`instant`; это ссылка на определение, содержательный словарь предстоит на КП3-04 |
| Document | ID организации/стандарт, тип, отчётный период, версия/SHA, размеры/страницы/URL, раздельные `fetched_at`, `signed_on`, `approved_on`, publication, доступность, подготовка, provenance, rights, audit, related_release, real/synthetic |
| Evidence | Документ/версия/SHA, locator, показатель/определение, период, валюта/масштаб, исходная запись/кодировка и provenance |
| Fact | ID, организация/документ/версия, показатель/определение, десятичная строка/null, исходная подпись, валюта/масштаб/период, Evidence ID/digest, provenance и reported/comparative роль |

Один `document_id` обозначает одну зарегистрированную версию. Для другого файла/версии регистрируется другой ID; Task хранит также явный `version_id`. Версия с префиксом `sha256:` должна совпасть с SHA файла. Нельзя выбирать «самую новую» версию неявно.

Периоды: `{"kind":"duration","duration_type":"full_year|year_to_date|quarter|custom","start":"…","end":"…"}` либо `{"kind":"instant","date":"…"}`. `full_year` — полный календарный год; квартал проверяется по календарным границам. Год и девять месяцев различаются. Custom можно хранить/запросить прямым фактом; сравнение custom пока отклоняется до отдельной методики. Все даты проверяются, timestamp требует явного offset.

Fact.value — ASCII десятичная строка без экспоненты/разделителей/NaN/Infinity; float/bool запрещены. Знак сохраняется. Валюта RUB/USD и масштаб1/1000/1000000/1000000000 разделены; bool не является масштабом. Evidence поддерживает явные `decimal_string` и прежнюю `comma_thousands_integer`. Смена кодировки/масштаба не выполняется автоматически.

Реальный PDF locator содержит страницу PDF и печатную/формы, область, таблицу, строку, колонку и заголовок единиц. Собственный synthetic locator содержит record_id и подписи без выдуманных PDF-страниц. `evidence_digest` в Fact связывает полную запись Evidence с фактом, включая локатор и provenance. Это проверка согласованности, не аутентификация и не независимая сверка ячейки: подделав все поля и digest, нельзя считать число доказанным первичным документом.

Дубли ID запрещены. Разные Fact IDs с одинаковым полным ключом, даже с одинаковым значением, дают конфликт выбора, а не первый найденный факт. Конфликтующие значения также не выбираются по рангу.

## Три разных вида состояния

| Что описываем | Поля и значения | Что из этого не следует |
|---|---|---|
| Локальный ресурс | file_status: not_checked/missing/available/hash_mismatch; extraction_status: not_run/extracted/unsupported_layout/error; local_resource_id — ID, не исполняемый путь | Наличие/извлечение файла не проверяет финансовый смысл |
| Подготовка документа | registered/candidates/checked/ready/conflict | Даже ready не доказывает историческую доступность |
| Происхождение проверки | candidate/structure_checked/assistant_checked/human_reviewed, метод и human_reviewer | Сверка ассистентом не превращается в человеческую проверку |

Checked/ready требует checked provenance и известный SHA; для ready реального PDF нужны URL/размеры/число страниц. Неполная registered-запись может храниться без них. Checked Fact требует Evidence; кандидат может быть ещё без Evidence, но не допускается `bind_task`. Кандидат/structure_checked Evidence не допускает checked Fact к выбору. Human_reviewed требует reviewer; без фактической человеческой проверки адаптер его не назначает. Отсутствие human_reviewed не блокирует assistant_checked snapshot.

В ручном подготовленном каталоге входы могут связываться при `file_status=missing`: это не запуск поиска или извлечения. Будущий сервис обязан отдельно проверить доступность ресурса выбранного режима. В этом этапе нет источникового сервиса, который мог бы скрыть отсутствие PDF за успешным поиском.

## PublicationEvidence

Поля: `precision value timezone binding record_id source_url version_id document_sha256`. Unknown требует null-доказательства, `binding=unproven`; никакие approval/fetched/подпись/конец периода или related_release его не заменяют. Известная дата без доказанной связи с версией остаётся unproven. Связь `document_version` требует совпадения версии и известного SHA.

Для реальной записи нужен HTTPS source_url; synthetic может иметь только явно собственный record_id. Ссылки не открываются автоматически и не считаются доказанной публикацией сами по себе. Временные доказательства должны быть подготовлены по первичному источнику до включения.

Snapshot не требует публикации и не заявляет доступность в прошлом. Historical требует as_of с offset и доказанную доступность всех явно выбранных документов. Timestamp сравнивается как момент времени. При точности «дата» — консервативно со следующей полуночи: Europe/Moscow используется как UTC+03:00 для нынешнего учебного корпуса, также поддержан UTC. Иные зоны и исторические изменения смещений не реализованы; для такого корпуса нужна новая методика. Никакой дата-публикации текущего реального PDF не добавлено.

## Task и политика версии

Поля: `schema_version task_id original_question operation_id organization_id consolidation accounting_standard metric_id definition_id periods documents version_policy result_unit mode as_of`. Документы — непустой список пар document_id/version_id. Исходный вопрос не заменяется шаблоном. Нет default организации/лет/стандарта/операции. Нет поля expected, свободного Python, shell, URL или пути к инструменту.

Зарегистрированные описания операций: direct_fact_v1 (один период), absolute_change_v1 и annual_growth_v1 (два периода). Здесь нет реализации новых формул. Для сравнения нужны однотипные непересекающиеся duration-периоды в явном порядке; для годового роста — два последовательных полных календарных года. Неполный ввод даёт ClarificationRequired с полями, неизвестные ID/версия/операция — ContractError с кодом; они не означают отсутствие показателя в отчётности.

- `explicit_versions`: выбор только среди перечисленных версий; сравнительная колонка допускается как comparative_period.
- `original_period_documents`: требуются reported_period и исходный документ соответствующего периода (для instant — документ на эту отчётную дату). Сравнительная колонка2023 в отчёте2024 не подменяет исходный отчёт2023.

`resolve_organization` нормализует регистр/пробелы/ё. Пустой ввод или неоднозначный alias запрашивает уточнение; неизвестный alias отклоняется. Общий alias разных организаций допустим в каталоге и не выбирается по первой записи. `fact_by_id` возвращает копию записи с provenance, не финансовое подтверждение её пригодности.

`bind_task` валидирует каталог/Task, контекст и публикацию, затем выбирает допустимые Fact IDs. Результат: `binding_status=ready|missing|conflict`, reason_code, fact_ids/candidate_fact_ids, catalog_digest и `calculations_performed=false`. При отказе fact_ids пуст. Неизвестный ID — ошибка входа, другая группа/стандарт — конфликт, неизвестная публикация — missing/publication_unknown. Нельзя смешать валюты/масштабы или выдать иной result_unit без отдельного пересчёта.

## Выполнение отдельно от финансового результата

Outcome v0.2: `schema_version run_id task_id execution_status financial_status reason_code clarification_fields financial_result`.

| execution_status | financial_status | Содержимое |
|---|---|---|
| completed | answered | ok, непустой структурированный financial_result; формулы/истинность проверяются прежним финансовым валидатором, не этим конвертом |
| completed | missing/conflict/unsupported | Код из явного финансового набора, без расчёта и clarification_fields |
| awaiting_clarification | null | Причина и непустой список уточняемых полей, без financial_result |
| error | null | source_missing/registry_invalid/model_unavailable/input_invalid/protocol_error/save_failed, без расчёта |
| limit_exceeded | null | call_limit/timeout, без расчёта |

Неизвестные причины и невозможные сочетания отвергаются. `call_limit` нельзя назвать финансовым missing. Адаптер Outcome принимает уже валидированный старый user_response либо agent envelope; старые технические причины нормализуются в технический набор. Он не является новым оценщиком достоверности ответа. Старые prose-уточнения без нормализованного списка полей явно требуют отдельной миграции (`legacy_clarification_fields_required`), список не угадывается из текста.

## Миграция v0.1

Catalog и Task создаются отдельными функциями. Изменение старого request.question/formula_id не меняет адаптированный каталог. v0.1 JSON не изменяется, значения/исходные записи/локаторы/периоды/review/rights/audit/related_release сохранены. Approval_date переносится только в approved_on; signed_on остаётся null. Доступность локальных файлов не проверяется и записана not_checked/not_run. Историческая неизвестность сохранена. `definition_id=<metric>:legacy-row-v1` — временная ссылка на прежнюю строку, не готовый новый финансовый словарь.

Старые contracts.py/finance.py/user_path.py/retrieval.py/agent.py/simulation.py, CLI, frozen questions и evidence не переписаны. Новые модули пока не подключены к старому ответчику/UI. Новая Task на иной показатель не означает, что старый калькулятор уже поддерживает его.

## Проверить из корня ветки КП3-03

```powershell
python -I scripts\check_kp3_contracts.py
```

Показывает старый snapshot, старый historical/missing и четыре собственных synthetic Task. Нет финансового расчёта или LLM. Synthetic-каталог содержит две искусственные организации, IFRS/group и RAS/legal_entity, иные годы/показатели и отрицательное/нулевое значение. SHA synthetic-источника — digest явно заданного искусственного объекта, не реального PDF. Реальные эмитенты/корпус не расширены.

```powershell
python -I -m unittest discover -s tests -v
```

Доказательства — `evaluation/kp3_03_2026-11-09/`, подробный следующий промт — `prompts/kp3_04_financial_dictionary_and_method.md`. Качество рынка/модели и human_reviewed этим этапом не заявлены. QA07/call_limit и 3/10financial остаются прежними результатами.
