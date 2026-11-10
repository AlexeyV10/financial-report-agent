# Самостоятельный контекст после выбранного дизайна «Рабочий стол»

Пользователь выбрал первый дизайн. Отдельная КП3-UI реализует его в работающем интерфейсе. Не считать её выполнением17/18 и не начинать следующий этап автоматически. Дальнейшее действие определяется новым явным поручением пользователя. Если он просит18, сначала адресно установить состояние/зависимости17; не объявлять их завершёнными по номеру запроса.

## Где продолжать

ROOT: `C:\Users\Value\OneDrive\Документы\ChatGPT\Проектная практика`. Dirty root `codex/kp3-01-02-scope-baseline` c18e3fe сохраняет неопубликованные01/02, план/product_scope/baseline/analysis/старый UI/venv. Их автоматически не публиковать.

Новый интерфейс: ROOT/tmp/kp3-ui-worktree, ветка `codex/kp3-ui-desktop-redesign`, база16 b6c622e002ef8ff6eb101c099442a8397c4e4456. Фактические head/tag/PR/base читать в `evaluation/kp3_ui_2026-11-10/git-publication.json` и локальной финальной квитанции ROOT; технический тег указывает проверенный коммит, последующий коммит содержит публикационную квитанцию. PR зависим от16, merge не поручался. На старте UI main f349717 и PR03–16 открыты — это история, перед новой задачей требуется свежий fetch/GitHub.

Постоянные правила: прочитать AGENTS/workflow/github_collaboration; рабочий HANDOFF до BEGIN_SOURCE_ARCHIVE; STATUS/README/последние decisions обеих папок и нужный раздел локального плана. Проект делают пользователь и Codex; подписи других лиц не нужны. Отдельная codex-ветка/worktree ДО значимого изменения. Сохранять байтовые хеши и старые разделы, не reset/clean/stash/force/main push. Commit/push/PR/tag разрешены, merge только по поручению.

## Реальная реализация

`docs/kp3/desktop_ui_v1.md`, `app_kp3/desktop_app.py`, `desktop.css`, `src/financial_assistant/desktop_presentation.py`, `scripts/desktop_ui.ps1`, tests/test_desktop_presentation.py, tests_ui/test_desktop_app.py. Новый UI отдельно от неизменного product_app.py13 и dirty root UI.

Светлая боковая навигация: Анализ отчётности/Документы/История/Учебный сценарий/Как это работает. На desktop вопрос слева и ответ справа. Главная кнопка сразу под вопросом. Текст или явные поля формы; уточнения с runtime-вариантами; источники/страница; собственные MD/JSON; техническое раскрытие. История — явно снимок, не новый расчёт. Все разделы вызывают прежние service/product_service07–13, не дублируют арифметику.

Текстовый вопрос сохраняется без префикса/перезаписи. UI selections передаются как явные ответы08; parse_form не является скрытым merge полей из текста. Нет default ФосАгро/2024/2023/mode. Default B явно подписан. A/C доступны через прежние реальные адаптеры, не имитируются и не подменяются B при отказе. В новой UI-проверке запускался только B, новых native model calls=0. Кнопка примера явно выбирает Phosagro2025Q1/сравнительный2024 в одном exactPDF, без значений/expected/FactID в форме. Значения119272/159390 млн RUB и33,64% приходят от прежнего сервиса.

Смена компании/периода/версии/единиц/as_of/method/context скрывает старый ответ и отзывает source/download URLs. Повторный идентичный запуск открывает существующий RunStore snapshot, отдельная новая попытка требует явной кнопки. Ложная предпосылка/why/unfulfilled сохраняются, при отказе не подтверждаются. Exact PDF доступен только из прежней доверенной карты; никакого исполнения путей/URL/кода вопроса.

## Ресурсы и доказательства

Ядро: C:/msys64/ucrt64/bin/python.exe3.14.7 SQLite3.53.4. UI — прежний ROOT/tmp/kp3-ui-cpython312/Scripts/python.exe3.12.14, Streamlit1.67.0/Pandas3.1.1; глобальные пакеты/старые venv не менялись. Модель после16 не запускалась. Источники/полный текст/рендеры/exports/index только исключённая tmp, прав не приписывать.

W/tmp/service-context.json, local-resources.json, export-resources.json, retrieval-run-ui/{prepared,automatic}.sqlite, reused-extraction-06 и freeze-resources-ui.json — новые доверенные карты с проверенными реальными байтами. Восемь export повторно использованы без worker/download; индексы байтово равны14: prepared1cd853349a3c034c0823eddebc00965acfbc374b765e0d28712ece048f666f3f, automatic7d1dc62d3020272dec4695aefbbb8a523000c08c9ef208b21dcc11dd1da81943. Старый PDF ROOT/tmp/pdfs/phosagro-2024-ru.pdf SHA824f100d14396c26faacf80a03cca6b20d458c9b5d835201bc80068decb3d6e1 не менять и не качать заново.

Запуск из W: scripts/desktop_ui.ps1 start/status/stop, localhost8521. На завершении собственный UI оставлен работающим для пользователя; owner receipt W/tmp/desktop-ui-owner.json. Остановка только по совпадению PID/path/starttime. Другие8509/8512/8513 не останавливать. В свежем clone отсутствующие ресурсы/venv не считать установленными.

Проверки: 778/778 unit (760+18), 15/15 Streamlit AppTest, все17 checkers03–14/oldgold04/07/corpus05/5legacy; 15/16 manifests проверены в их исходных worktree; frozen14 134files/28resources и138raw16 сохранены, replay16 идентичен. Отчёт, сохранённые первые ошибки, команды, исходные snapshots/хеши, ui-checks и собственные screenshot desktop/mobile — evaluation/kp3_ui_2026-11-10. Browser event download timeout338s честно сохранён; реальные JSON/MD скачались и побайтово совпали. Sandbox os.linkWinError5 повторён с реальной эскалацией. Две первые ошибки дополнительных UI-тестов: неверная подпись и неявный выбор процентов; исправлены тесты, parser/финансовое ядро не менялись.

Реальная CUA-проверка — расчёт, источникPDF5printed1, выгрузка, повтор, смена компании, уточнение, меню/документы на360px, desktop1280×720. На360px scrollWidth=360, меню открывается/закрывается. Viewport сброшен и completion_summary выполнен. Новая вкладка оставлена пользователю. Новые UI-правки снова проверять реальными действиями; перед UI применять computer-use skill, перед PDF — pdf skill. Первичные страницы в Git не включать.

## Не потерять прежние результаты/ограничения

03 Catalog/Task/Outcome0.2 и legacy adapter;04 определения и independentFraction/Decimal80/HALF_UP;05 неизменные48checkedFact/8PDF/2lineages,39economiccontexts+9versioncells;06 prepared56/56 vs automatic40/48/6of8 плюс8extraquarters неFact;07 пятьoperations Request/Outcome0.3, admission1.0;08 ограниченный deterministic parser и явные уточнения;09 B с обязательным полным поиском;10 настоящий C и11 одношаговый A;12 собственный scenario;13 история/экспорт/exact viewer;14 immutable protocol;15 известные robustness143/143,20mock отдельно,2offline/2worker отдельно;16 actual138/227nativechat известный корпус.

КП3-16: B/A/C каждый32/32strictnumeric+8/8refusal над40известнымиform-вопросами/32exactcells/28economiccontexts/8PDF/2lineages, не unseen и не обобщённое качество. МедианыprimaryB206.76195/A2458.96105/C5496.4491ms. Больше nativeшагов не показало точностного преимущества на этом наборе. Старые QA07 C/call_limit,3/10financial/reserved0 — история, не переписывать новым названием UI. Нет нового benchmark/freeze.

Все8publicationunknown/unproven, human_reviewed0, праваunknown, historical/realtradingblocked. Нет новых Fact/источников/OCR/финансовыхформул/FX/quarter subtraction. Report-defined OP разного состава у двух групп, final signed net CFO; Segezha2021original vs comparative2021 из2022 различаются, причина/эквивалентность не доказаны. Relative positivebase, margin sameexactcontext, HALF_UP2percent, exactmoney; candidate/automatic без Evidence не допускаются. Собственные synthetic не эмитент и не реальные цены. Runtime не читает gold/targets/expected, вопросы/документы недоверенные данные.

Закончив только новое явно порученное изменение, сохранить evidence/status/решения, Git-доставку по порядку и самостоятельный промт. Не запускать следующий этап автоматически. По текущей UI-задаче работа завершена и остановлена.
