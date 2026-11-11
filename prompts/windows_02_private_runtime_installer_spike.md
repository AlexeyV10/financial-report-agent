# Самостоятельный промт WIN-02: private runtime и clean-VM installer spike

Это следующий отдельный этап после WIN-01. Подготовка этого промта **не запускает
WIN-02**. Не выполнять академические КП3-18/19/20, весь Windows backlog или два
полноценных интерфейса. Проект фактически делают пользователь и Codex; чужие
формальные подписи/проверки не требуются. Общаться по-русски, понятно первокурснику.

## База, Git и сохранность

Исходная папка:
`C:\Users\Value\OneDrive\Документы\ChatGPT\Проектная практика`.
Dirty-root `codex/kp3-01-02-scope-baseline`, неопубликованные01/02, старый UI/venv,
КП1, архивы и чужие изменения сохранить. Не добавлять весь root, не reset/clean/
stash/force push/прямой push main. Прочитать применимые AGENTS.md,
docs/workflow.md, docs/github_collaboration.md, рабочий HANDOFF до настоящего
BEGIN_SOURCE_ARCHIVE; последние STATUS/README/decisions root и проверенной базы.

WIN-01 находится в `tmp/windows-01-worktree`, ветка
`codex/windows-01-native-spike`, зависимая база исследования
`e62bd64ebb0a79037ae3ac56750490efdefff062` / `codex/windows-app-research-plan`.
Исследовательский PR19 был открыт на момент начала WIN-01, его положение в цепочке
не означает merge. Перед работой выполнить свежие fetch/API и взять **реальные**
WIN-01 head/base/PR/tag из `evaluation/windows_01_2026-11-11/git-publication.json`
и финальной локальной квитанции
`tmp/windows-01-final-local-receipt.json` исходной папки. Тег этапа
`windows-01-native-spike-v1-2026-11-11` указывает на проверенный stage commit;
финальный head может быть позднее из-за публикационной квитанции. Не путать их.

До значимых правок создать отдельную `codex/` ветку WIN-02 и изолированный worktree
в исключённой tmp/. Если предыдущий PR открыт, допустима явная зависимая база.
Сохранить branch/head/status/хеши старых файлов и исходные байты обновляемых
документов. Обычные allowlisted commit/push/PR/technical tag заранее разрешены;
merge не поручен. Перед Git-доставкой свежие main/PR/conflicts/diff/подходящие
тесты и проверка сквозного поведения. Не выдавать отсутствие конфликтов за исправность.

## Что фактически решил WIN-01

Читать `docs/windows/adr_001_native_ui.md`, `spikes/windows_01/README.md`,
`evaluation/windows_01_2026-11-11/{report,environment,wheels,builds,measurements,
tests,component-runs,ui-observations,first-errors,preservation}.json` и Windows-план.

Основной UI для следующего spike — **WPF + общий Python worker**. Это fallback
по конкретным практическим проблемам Qt, не выбор по популярности:

- PySide6 Essentials/shiboken6.11.3 source GUI работал, но повторные последовательные
  прогоны имели event-loop gap695–760мс. Причина/UIA влияние не изолированы.
- PyInstaller6.22.3 Qt onedir создан (202файла/136319176байт), но реальный запуск
  упал при импорте QtCore: DLL load failure/procedure not found. Не считать
  build success запуском и не исправлять системные DLL вслепую.
- WPF EXE31744байта +config341байт реально запускался. Он собран предустановленным
  Framework64 csc x64 и работает на **.NET Framework4.8.1**, Release533509,
  registryVersion4.8.09221, CLR4.0.30319.42000. Это не современный .NET SDK.
  Внешний worker пока использует новое dev-окружение stock CPython3.12.14.

Оба UI используют один pypdfium2 5.15.2 / фактический
PDFium159.0.8149.0@sourcebuild-toolchained, Pillow13.0.0 и исходный calculator07.
Qt PDF не используется. У собственного вымышленного PDF v1:
SHA256 `c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451`,
2327байт, одна страница420×360, МСФО/группа/полный2025/млнRUB,
выручка120, операционная прибыль18, оба положительные. Независимый expected15,00%.
Код генерации ReportLab4.4.9 — `generate_demo.py`; PDF остаётся локальным tmp/.
Это собственный оригинальный пример с разрешённым распространением **этого demo**,
не разрешение распространять старые issuer PDF и не выбранная code-license проекта.
`human_reviewer=null`, публикация неизвестна, historical не разрешён.

Прежний synthetic admission не ослаблялся: record_id отдельно связан адаптером
с SHA/page/rect собственного PDF. Финансовая логика не перенесена в C#. Нет
доказательства универсального PDF-import. Таблица10000строк — техническая нагрузка.
12 новых slice tests +3 Qt component tests прошли; отдельно8 записанных фактических
component runs проверены по2 расчётам/5render-state/cancel/crash23/recovery;
64rotation×zoom×DPI координатных проверки. 799unit/18AppTest — исторический
baseline17, не новые native tests. Сохранность старого кода доказывалась SHA.

На одной Windows11Pro10.0.26200/i7-14700HX/16873545728байтRAM медианный внешний
startup source Qt0,514с/WPF0,275с. Настоящий OS cold boot не измерен.
Idle окно лишь80мс, treeRSS повторно считает shared pages. Не обещать8/16/32GB
минимумы по этим опытам. WPF также имел gap108–153мс, не полный production pass.

Доступность ограничена: WPF UIA source/page/status/полный result Value наблюдены,
native dialog и ряд действий с клавиатуры/отмена/crash/recovery выполнены;
крупный19px при125% читабелен. WPF **системные200% не проверены**, OS high contrast
не включался. Narrator запущен, фокус/read command попытаны, слышимое чтение
не подтверждено. Qt effective200% — override поверх системных125%, не OS200 test;
с большим шрифтом тесная компоновка. Не переписать это в «всё прошло».

## Результат только WIN-02

Доказать или честно ограничить **минимальную установку WPF + private Python worker
+ PDF renderer на чистой Windows11x64**. Это feasibility, не подписанный
публичный релиз, не WIN-03 полная runtime migration и не WIN-04 workspace overhaul.

1. Сначала коротко инвентаризировать уже доступные SDK/build/installer/VM средства
   и возможность реальной чистой VM/Windows Sandbox. Не выдавать вторую папку,
   новый venv или текущий хост за clean VM. Если чистой среды нет, самостоятельно
   довести безопасный локальный артефакт до проверяемого состояния, затем указать
   конкретное недостающее средство/решение; не выдумывать VM-проход. Не менять
   настройки виртуализации/защиты/глобальные среды без существенного основания.
2. Выбрать минимальный воспроизводимый runtime path WPF. Допустимо использовать
   штатный .NET Framework, если реальный clean-VM baseline содержит подходящую
   версию и она явно проверяется. Если он не подходит, обосновать переход на
   современный app-local/self-contained WPF/.NET в пределах packaging spike;
   устанавливать SDK только изолированно, фиксируя версии/источник/SHA/условия.
   Не переписывать финансовый engine ради языка GUI.
3. Частный stock CPython3.12x64 + pinned renderer/dependencies должны поставляться
   рядом с приложением, без глобального Python/MSYS2/Ollama, PATH/pip setup
   пользователем, требования Git/OneDrive/рабочего cwd или dev-venv. Собрать
   **обе части**, а не крошечный frontend EXE с внешним development worker.
   Подходящий private Python вариант выбрать по реальной совместимости и лицензии,
   не копировать целиком защищённый runtime Codex в распространяемый installer.
4. Включить минимальные собственные readonly assets и собственный fixture.
   Пакет не содержит первичные8PDF/страницы/полныйissuertext/индекс/weights/секреты/
   платные выгрузки. Старые pinned manifests/gold не редактировать ради путей.
   При необходимости создать отдельный packaging adapter/manifest новой версии.
   Старые07 source/path/admission guards не отключать. Подтвердить сопоставимый
   расчёт15,00% и exact source highlight в установленной копии из Unicode/space
   пути вне репозитория. PDF просмотр сам по себе не доказывает расчёт.
5. Сделать per-user installer с shortcut и uninstall; offline базовый запуск,
   создание собственного рабочего каталога отдельно от readonly install,
   отсутствие console и admin для обычного пути. Пользовательские данные при
   uninstall сохраняются по умолчанию; удаление данных только отдельным явным
   выбором. Проверить cancel/crash/закрытие без orphan worker. Не писать
   production updater/Store/signer в этом spike.
6. Проверить фактический состав DLL/plugins/runtime, версии/источники/SHA и
   third-party licenses/notices. PDFium BUILD_LICENSES из конкретного колеса
   обязательны, binding Apache2/BSD3 не покрывает всё DLL. Pillow MIT-CMU,
   psutil BSD3 только если поставляется; compiler/build-only deps отделить.
   Windows .NET Framework не объявлять MIT modern .NET. Собственная лицензия
   проекта всё ещё не выбрана: не назначать её, не покупать договор/сертификат.
   Qt сейчас не основной GUI; его DLL не включать случайно в WPF worker package.
7. В реальной чистой среде обычного пользователя без Python/Ollama/admin:
   install → shortcut → offline ownPDF/view/exact source/calc15,00% → progress/
   cancel/crash/recovery → close → uninstall. Фиксировать конкретную OS/runtime,
   startup/idle/peak/размер полного артефакта и файлов, первые ошибки и реальные
   результаты. Настоящий cold/warm разделять; не переносить tiny demo результаты
   на всю будущую программу или финансовое качество.
8. Для выбранной поставки проверить keyboard/UIA/Narrator/125–200%DPI/большой
   русский текст/контраст в доступной среде. Отличать реально прослушанное чтение
   от наличия UIA Value; OS high contrast — от собственной палитры; OS200 — от
   zoom страницы. Если часть недоступна, сохранить точный remaining gate,
   не объявлять её пройденной. Перед реальными окнами читать computer-use skill;
   закончить CUA completion_summary после наблюдаемого результата. Скриншоты
   и полный UIA текст — tmp/, публично только собственные минимальные сведения.

Существующий **Qwen не запускать, не опрашивать, не перенастраивать**, моделей
не скачивать. Никаких новых источников/OCR/формул/прогнозов/облака/сделок/обещаний
доходности. Никакого eval/exec кода модели или произвольных путей/URL/SQL из документа.
Sandbox/network/install failures требуют настоящего разрешённого механизма
эскалации, а не обхода; учитывать фактические permissions текущей сессии.

## Проверки и завершение

В `evaluation/windows_02_<дата>/` сохранить before/env/build recipe/dependency
inventory/первые ошибки/host-vs-clean-VM результаты/измерения/лицензии/границы/
сохранность. Приватные VM exports, первичные документы и binaries — tmp/.
Новые meaningful tests — IPC/runtime/package installed behavior; не подменять
их historical Streamlit AppTest. Если старое ядро и зависимости не менялись,
достаточно доказать их сохранность. Если меняется версия runtime/зависимость
поставляемого ядра, провести подходящую прежнюю регрессию/контракты/CLI и
честно сохранить несовместимость, не подгонять старые pinned SHA.

Обновить STATUS/decisions/README сохранными префиксами, Windows roadmap по
факту результата02; дальнейшие задачи не помечать выполненными. Сохранить
allowlisted commits/push/PR/technical tag, публичную git-publication и финальную
локальную квитанцию с фактическими SHA/base/PR/tag/свежим main, без merge.
Подготовить подробный самостоятельный промт **только следующего логичного этапа**
с реальным результатом02 и незакрытыми gates. После промта остановиться.
