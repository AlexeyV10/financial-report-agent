# Набор и протокол КП3-14, версия1

Это предварительно объявленное контролируемое сравнение на **известном корпусе**, не unseen/слепой тест и не результат итогового прогона. Все48 real Fact и предыдущие семейства уже использовались на03–13. Reserved unseen real=0, human_reviewed=0; перенос на новые документы/макеты не измеряется. Проект делают пользователь и Codex, без вымышленных человеческих подписей. На14 итоговые A/B/C ответы не получают; следующий шаг15 — отдельное поручение, итоговое сравнение относится к16.

## Контракт до подготовки gold

`kp3-suite-0.1` разделяет cases и evaluator-only `kp3-gold-0.1`. Cases содержат case_id/suite/split/category/profile/family/data_origin/known_to_developer/source/answers/fault_id. Финансовый source — только обычный Input/Form08; в нём нет ожидаемого числа, формулы, правильного Fact ID или gold. Только `source` и `answers` получает B/A/C. Metadata семейства, catalog facts, reference и причины ожидаемого исхода остаются evaluator. Trusted profile и fault registry передаются настройкой runner, не моделью и не вопросом. Документы и поля не являются исполняемым кодом.

Gold хранит отдельно ожидаемые execution/request/financial statuses и reason, фазу остановки, семантику входа, точные обязательные входы/источники/ячейки/единицы/версии/SHA/происхождение, независимый exact result/display/rounding, предпосылку/why и ограничения. Ошибка/limit/clarification не правильный финансовый отказ; parsed/resolved не answered. Missing в каталоге не доказывает отсутствие строки PDF. Нечисловой ожидаемый исход не содержит скрытого правильного ответа.

План92: financial dev20 на прежнем own07 каталоге, financial comparison_known40 на неизменных real05 источниках, interface8, scenario12, robustness12. Числа инженерные, не требования преподавателя. Сценарные/robustness записи на14 являются планами и gold для последующих изолированных проверок, не заявлением об уже выполненных сбоях15. Никаких новых issuer facts, дат публикации, цен или формул.

40 financial comparison:10 direct,8 delta/relative,6 margin,4scale,8 nonnumeric refusal,4 проверки предпосылки =32 числовых+8 отказов. Отказы бывают на уровне binder/search и финансового Outcome07; это отдельные поля. Technical отказ не засчитывается вместо них. Dev own07 включает известную отрицательную базу CFO и соответствующий unsupported; количество numeric/отказов выводится из gold, не предполагается20. Точность первичного отчёта арифметикой не повышается.

## Зависимости и границы split

Финансовые семьи объединяют lineage организации/документов, версии и экономические контексты без версии; операции/шаблоны дополнительно маркируются. Все связанные real версии одной группы входят в comparison_known; own07 lineage входит в dev. Это отсутствие пересечения в новом назначении split, а не стирание исторической утечки: real comparison **целиком известен разработчику** по03–13. В comparison всего2 real source-lineage clusters;40 вопросов не40 независимых документов/фактов. Семантически одинаковые вопросы с теми же входами/операцией/единицей/предпосылкой запрещены; разные операции над теми же ячейками явно зависимы.

Interface и scenario используют часть тех же источников для других задач и имеют собственные знаменатели; это не дополнительные независимые financial eval наблюдения. Document/template holdout отсутствует; операции/грамматика/набор известны. Обычный независимый биномиальный интервал на40 вопросах не заявляется.

## Независимость и представление

Gold получает исходные значения из immutable checked catalogs05/own07/own12, а не из production Answer или parser. Fraction/integer reference07 и отдельный Decimal80/HALF_UP проверяют финансовые значения. Own scenario oracle12 независимо считает cents/ledger/cash/quantity/fees/slippage/drawdown; real scenario — только blocked и gaps. Runtime source checks/admission/comparability/publication не создаются из gold. Reference modules и golden files не импортируются answering src/app.

Основной формат сравнения — строго типизированный существующий B0.1/C0.2/A0.1 Answer, не A_raw. Все опубликованные financial_result.inputs/result/sources/assumption_checks рассматриваются как claims. Проверяются также extra keys/лишний financial text: неизвестное свободное повествование не становится правильным при совпавшем числе. Входы сверяются с первичной минимальной разметкой по полному контексту, не по одной ссылке/ID. Формула/округление/точная дробь/отображение проверяются раздельно. После отказа направление предпосылки not_checked, причинное why не выдаётся за выполненное.

Дополнительный аудит представления поддерживает только фиксированный Markdown export13: человеческий раздел и вложенный JSON проверяются целиком по объявленной грамматике. Лишняя сумма/удалённое ограничение/иная ячейка/HTML/закрытие блока выявляются. Если Markdown не собирался, renderer metric — not_observed, не автоматический успех. Открытие PDF не новая сверка числа; primary pages/text/weights в suite/export не попадают.

## Метрики, порядок и расходы

Каждая метрика имеет x/n; n=0 означает not_measured. Numeric correctness — все32 answerable comparison, включая ошибки/timeout/ложные отказы. Correct refusal — все8 ожидаемых завершённых отказов; technical error/limit никогда не успех. Отдельно false refusal/technical completion/claim support/обязательная полнота, Evidence@k и complete retrieval по уникальным SearchSpec, parser/clarification, scenario/robustness. Зависимые перефразировки и несколько ячеек одной таблицы не становятся разными retrieval queries. Usage unknown не заменяется нулём, ошибки и дополнительные попытки входят в расходы.

Порядок40×3=120 primary method attempts фиксируется до ответов с seed20261110; A/C чередуются, B тот же trusted input.6 заранее выбранных numeric задач×3=18 warm repeats идут отдельно, не увеличивают40/32/8. Итоговый максимум138 объявленных попыток. Внешние retries не автоматические; первый исход сохраняется и участвует в primary метрике, новая попытка имеет отдельный ID/reason/phase. Все методы получают одни вопросы/catalog/source/index/admission/definitions/top_k32 и gates07. A — metadata after1primary search/1chat; C — tool loop с checked values по запросу; B — fixed. Runtime validation searches07 учитываются отдельно от primary, а не скрываются.

C:8 decisions,180с total,60с invocation,384outputtokens,top_k32,4096action/32768observation/8192summary. A:1choice,180/60с,top_k32,384tokens,4096choice/32768observation. B outer timeout180с,0chat. Worst-case model requests46A+368C=414 including18warm attempts; это верхняя граница, не фактический расход. Unknown transport/usage считается консервативно и отдельно; фактические tokens/latency нужны из raw. Новые вызовы на14 не требуются. Setup probes/cold-warm/model load не прячутся в latency; полное пользовательское время не равно model duration. Полная денежная себестоимость local hardware/electricity не измерена.

## Freeze и воспроизведение

Manifest после проверки набора и **до** итоговых ответов фиксирует hashes inputs/gold/families/order/protocol/evaluator/code/model prompts и config, sources/export/index/config/worker/environment/admission/definitions. Source base commit13 фиксирован, новые файлы14 — через hashes; Git delivery receipt отдельно, чтобы не было кругового хеша. Manifest не хеширует себя. Новая версия после freeze имеет новый immutable путь и объяснение; прежние03–13 manifests/gold не переписываются. Локальный resource map и run paths — доверенная настройка; перенос допустим только при совпадении logical IDs и всех artifact hashes. Индексы06 детерминированы по текущим bytes и пересобираются в новом tmp; сырьё не копируется в Git.

Replay читает сохранённые raw/manifest/gold, проверяет hashes/порядок/полноту плановых attempts и пересчитывает metrics без production-answer/model/network. Отсутствующие/повторные/неизвестные attempts остаются диагностикой и не уменьшают знаменатель. На14 replay тестируется только на отдельных явно помеченных evaluator controls, без выдачи их за120 итоговых запусков. Модель/пакеты/UI/old source data не меняются.

## Зафиксированный состав и проверка перед seal

Основные40 financial inputs — явные структурированные формы08 с полным контекстом. Нейтральный комментарий не подменяет заполненные поля;4 случая дополнительно содержат русскую предпосылку/why. Это сравнение выбора проверенных входов/методов на типизированной задаче, не40 вопросов свободного русского QA. Русский ввод имеет отдельные8 hand-specified controls.20 own07 dev — **прямые Request0.3 калькулятора**, а не выдуманный B/C/A поиск по отсутствующим synthetic PDF. Поэтому profile/target задаёт trusted runner; эти20 не входят в120 method attempts.

Числовая часть40 использует32 разных exact Fact IDs из48,28 экономических контекстов без версии/масштаба,8 версий,2 source lineages,3 definitions и full_year/quarter/YTD. Изменение масштаба не создаёт новый экономический факт. Такое объединение не доказывает эквивалентность original/comparative: Segezha CFO остаётся различающимся и несопоставимость не исправляется. Весь реальный каталог содержит положительные значения этих3 метрик; отрицательные изменения и собственный отрицательный CFO покрываются отдельно, отрицательные реальные revenue/OP не выдуманы.

Плановые знаменатели:32 numeric+8 refusal на метод,29 уникальных prepared queries/46 обязательных Evidence. Для scenario gold:4 completed own,7 blocked (3own+4real),1 technical error.12 robustness — изолированные планы; runtime fault campaign относится к15, не заявляется выполненной на14. Смена периода/стандарта/источника/ячейки/SHA/заголовка, потеря why/claim, лишнее число/текст, automatic и technical failure проверяются53 evaluator unit tests, а прежние финансовые gates — сохранённой регрессией.

Перед freeze прошли710 unit (657 прежних+53 новых), checkers03–14, immutable gold04/07/corpus05 и5 legacy CLI.40 новых comparison forms проверены **только** на normalization/binding/точные контексты,8 отдельных parser controls — на hand expectations. Два заранее объявленных own07 calculator controls проверили signed CFO и negative-base refusal;4 прежних actual13 B/A/C envelopes использованы только для проверки grader, не как новые14 model responses. На14 model calls=0, comparison attempts=0; ни120 primary, ни18 warm не выполнялись. Старые QA07 C/call_limit/3из10/reserved0 не меняются. UI13 и всё answering src сохранены побайтово; визуальный проход не повторялся.

Подготовительные ошибки сохранены: catalog-page URL отличался от требуемого exact-PDF page URL; text08 сохраняет весь вопрос как premise fragment, а form — явно переданный фрагмент. В первом комментарии формы повтор дат конфликтовал с полями; комментарий сделан нейтральным, полные поля сохранены. Input08 с «руб.» потребовал валюту; в control до freeze использовано объявленное «рублей». Это правки открытого черновика до seal, без изменений parser08 или расчётов и без результатов model comparison. Первый sandbox отказ os.link у прежнего product13 checker сохранён; та же команда прошла после настоящей эскалации, критерии не менялись.

Локально сверены28 физических ресурсов:8 PDF,8 exports,2 индекса+2 sidecar и8 model/server артефактов. GGUF/manifest/config/template/license/params и executable проверены по реальным bytes; сервер модели на14 не запускался/не вызывался, его текущая доступность не измерялась. Export worker environment совпал с3.12.14/pdfplumber0.11.9/pdfminer20251230. MainPython3.14.7/SQLite3.53.4. Private maps/полные exports/источники/веса остаютсяtmp, в публичном manifest только logical ID/hash/size/kind.

Команды для чтения/аудита (без итогового получения ответов):

```powershell
C:/msys64/ucrt64/bin/python.exe -X utf8 -I scripts/check_kp3_evaluation.py --report tmp/evaluator-new-audit.json
C:/msys64/ucrt64/bin/python.exe -X utf8 -I scripts/replay_kp3_evaluation.py --freeze evaluation/protocols/kp3_eval_v1/freeze-manifest.json --raw-dir tmp/replay-controls14 --raw-manifest tmp/replay-controls14/raw-manifest.json --output tmp/replay-controls-new.json --evaluator-controls
```

Повтор генерации/seal не перезаписывает существующие файлы. Freeze manifest0.1 связан с текущими source/gold/code hashes, receipt и SHA сохранены отдельно в evaluation14. Если15 потребует исправления frozen dependency, до16 нужна честная новая версия freeze с сохранениемv1, а не правка старого manifest/gold. Наличие подготовленного набора и успешного replay не означает полученную точность модели.
