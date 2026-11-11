# Самостоятельный промт WIN-02B — приёмка installer в чистой Windows

Это отдельное продолжение незакрытой приёмки WIN-02. Подготовка промта не запускает
его. Не начинать WIN-03/04, академические КП3-18/19/20, весь backlog или второй GUI.
Общаться по-русски и понятно первокурснику. Проект делают пользователь и Codex;
формальные роли не требуют чужих подписей/запусков/подтверждений.

## Место, фактическая база, сохранность

Root: `C:\Users\Value\OneDrive\Документы\ChatGPT\Проектная практика`.
Он остаётся dirty-веткой `codex/kp3-01-02-scope-baseline`; старый UI/venv,
неопубликованные01/02, КП1, архивы и чужие изменения сохранить. Не добавлять root
целиком; не reset/clean/stash/force push/прямой push main.

WIN-02 находится в `tmp/windows-02-worktree`, ветка
`codex/windows-02-private-runtime-installer`; зависимая база WIN-01
`ae59496c9e1d0fc29b833c86309c16fe63ccf0fb` / `codex/windows-01-native-spike`.
PR20 был открыт, не объединён, при начале02. Реальные итоговые head/base/PR/tag
WIN-02 брать из `evaluation/windows_02_2026-11-11/git-publication.json` и
`tmp/windows-02-final-local-receipt.json` исходной папки. Технический тег
`windows-02-host-installer-spike-v1-2026-11-11` — проверенный host-stage commit,
а финальный head может быть позднее из-за публикационной квитанции.
Не считать эти SHA одинаковыми и не считать GitHub-состояние известным без fetch/API.

Прочитать применимые AGENTS.md, docs/workflow.md, github_collaboration.md;
рабочий HANDOFF до настоящего BEGIN_SOURCE_ARCHIVE; последние STATUS/README/
decisions root и проверенной базы; Windows roadmap; `docs/windows/installer_spike_02.md`,
`spikes/windows_02/README.md`, evidence02 `{report,build,environment,licenses,tests,
remaining-gates,first-errors,ui-observations,preservation}.json`.

До значимых правок создать отдельную codex/ветку и изолированный worktree в
исключённой tmp/. При открытом предыдущем PR допустима явная зависимая база.
Сохранить branch/head/status/хеши и исходные байты обновляемых документов;
проверенный предыдущий worktree не изменять. Commit/push/PR/technical tag в рамках
задачи заранее разрешены; merge не поручен. Защиту main без bypass не обходить.

## Что выполнено и что осталось

WIN-02 статус **host_validated_clean_vm_pending**, не complete. WPF выбран в01
по фактическим Qt pause/build DLL failures; Qt не развивается. Собран полный
NSIS3.13 installer WPF + private official CPython3.12.10 embeddable x64 +
pypdfium2 5.15.2 / PDFium159.0.8149.0@sourcebuild-toolchained + Pillow13.0.0.
Из старого ядра9 собственных файлов копируются побайтово, формулы не переписаны.
Исходный WPF01 не менялся; builder правит только доверенный worker CLI в
generated copy: `-I -B -u`. `._pth` ограничен внутренними путями, без site/pip.
Qt/psutil/PyInstaller/ReportLab/Ollama/weights/issuer PDF в payload нет.

Локальный **проверенный** артефакт (не загружен в Git):
`tmp/windows-02-worktree/tmp/build-v4/ProjectPractice-WIN02-setup.exe` относительно root.
Размер22434104байт, SHA256
`f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf`.
Payload271файлов/46157740байт до служебных install/uninstall файлов.
Проверить этот SHA перед передачей. Новая сборка может дать другой PE SHA:
bit-identical build не заявлен, подставлять старый SHA в новую квитанцию нельзя.

На существующем Windows11Pro10.0.26200/i7-14700HX/16873545728байтRAM обычный
пользователь действительно установил `/S` без admin в
`LocalAppData/Programs/Проектная практика WIN02`, открыл созданный .lnk,
увидел native окно/собственный PDF/page1/точную зелёную рамку18/результат15,00%.
Собственный PDF WIN-01,2327байт,420×360, SHA
`c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451`:
вымышленная группа/МСФО/полный2025/млнRUB/выручка120/операционная прибыль18,
оба положительные, publication unknown, human_reviewer=null. Только этот own demo
разрешён для передачи; не заменять его первичными8PDF/новыми фактами.

Фактически проверены private Python при PATH=System32 и неподходящих
PYTHONHOME/PYTHONPATH, все sys.path внутри install, isolated/no_user_site, assets
read-only и отсутствие cache writes. Worker crash/cancel/recovery и Job Object
работают на хосте; при hard kill GUI реальный worker исчез через500мс.
Uninstall `/S` удалил program files/ярлыки/HKCU entry, сохранил46 файлов данных
по SHA и неизвестный install file, PATH user/machine сохранился. Наш известный
контрольный файл после доказательства перенесён в tmp, пустой install folder
убран нерекурсивно; пользовательские данные оставлены. Реальной установки сейчас
на хосте нет, installer сохранён. Интерактивный wizard click-through отдельно не принят.

10 новых package checks прошли в окончательной установленной копии v4 — это10
уникальных случаев; повторения на ранних payload/v3 не добавляют новых случаев.3 actual full GUI component runs
отдельно подтверждают по2 расчёта/5renders/cancel/crash23/recovery.
69 прежних calculator/retrieval tests на private CPython в оригинальном repo-root
прошли69/69. При preload **shipped core с чужим repo-root test context** было
вначале v3:41pass/28errors (25 path guards +3 отсутствующего legacy contracts.py).
Модуль добавлен побайтово; final v4:44pass/25errors только path guards. Это сохранённая граница,
не причина выключать guards или править gold. Полная installed parity и WIN-03/04
не выполнены.799unit/18AppTest — исторические данные, не проверки native installer.

Медиана6 startup на хосте≈0,371с, первый≈0,350с; OS cold boot не измерен.
Сумма RSS повторно считает shared pages; это tiny own demo без модели, не требования
RAM будущей программы и не benchmark финансового качества.

Реальные UI действия: native file picker, calculate, source/result UIA, progress,
Escape cancellation с пустым ответом, crash/recovery,19px при системных125%,
закрытие. Narrator запускался, фокус/result read command наблюдён, но звук недоступен
инструменту: успешное слышимое чтение НЕ подтверждено. SystemSettings.exe не дал
targetable window, поэтому OS200 и OS high contrast не менялись/не проверялись.
Render DPI2/zoom200 не равны OS200. Ранние captures были белыми при UIA дереве,
после file-open окно отображалось. В окончательном v4 первая capture показала
контролы до взаимодействия; причина раннего белого кадра не доказана.

## Задача только WIN-02B

1. Сначала проверить наличие **реальной доступной чистой Windows11x64 guest или
   отдельной чистой машины**, обычного пользователя, разрешённого образа ОС и
   способа передачи/управления. На предыдущем хосте SandboxExe=false, vmms/
   vmcompute/Hyper-V module отсутствовали, известные VM CLI не найдены,
   admin token=false. HypervisorPresent=true не доказывает доступную clean VM.
   Не выдавать venv/новую папку/этот же хост за чистую среду. Не включать BIOS/
   виртуализацию, не менять защиту и не устанавливать глобальный hypervisor
   автоматически. Если ресурса нет, завершить независимую подготовку конкретного
   артефакта/сценария и назвать именно недостающее средство/существенное решение.
2. При доступной чистой среде зафиксировать OS/build/учётку/отсутствие global
   Python/Ollama/admin, фактический .NET Framework. Installer требует4.8+,
   Release≥528040; на хосте был4.8.1/533509. Не ослаблять precondition. Если guest
   не подходит, сохранить честный блокер и обосновать минимальное решение;
   не превращать это в полную новую runtime migration без существенного основания.
3. Передать только собственный проверенный installer разрешённым способом,
   сверить SHA в guest и практически пройти install → shortcut → первый запуск
   **до взаимодействия** → own PDF/view/exact outline/calc15,00% → progress/cancel/
   crash/recovery → close → uninstall. Проверить Unicode/space path, no console,
   отсутствие Git/OneDrive/cwd/dev-env зависимости, private runtime, readonly
   assets отдельно от userdata, data preservation и отсутствие own orphan workers.
   Для настоящего offline-теста отключить сеть именно гостевой среды разрешённым
   способом; не менять сеть/защиту хоста. Проверить actual interactive wizard,
   не только `/S`; данные при uninstall сохранять по умолчанию.
4. Проверить оставшиеся keyboard/UIA/Narrator/system125–200%/большой русский
   шрифт/OS high contrast в доступной guest. Менять и восстанавливать только
   явно выбранные тестовые настройки guest; исходные значения сохранить.
   Реально прослушанное чтение отличать от UIA Value/отправленной команды;
   OS contrast — от собственной палитры; OS200 — от render zoom. Если звук или
   настройка недоступны, сохранить exact remaining gate, не проставлять pass.
   Перед настоящими окнами читать computer-use skill; после наблюдённого исхода
   завершить CUA completion_summary. Снимки/полный UIA/VM exports только tmp/.
5. Измерить размер полного artifact, setup/startup/idle/peak/cancel/close на
   конкретной guest. First-process/warm не подменять OS cold boot; описать кэш,
   sampling и shared RSS. Малый собственный пример не доказывает общее качество
   финансовых документов или минимумы8/16/32GB.
6. Сохранить лицензионные/runtime границы. CPython3.12.10 official ZIP SHA
   совпал с PSF SPDX, python.exe подпись Valid; это последний готовый maintenance
   Windows3.12 пакет, более новые security source releases существуют. Не считать
   его утверждённым поддерживаемым runtime публичного продукта. Оценка/выбор
   поддерживаемой сборки — отдельное содержательное решение/следующий scoped
   этап, без скрытой подмены baseline. PDFium BUILD_LICENSES, Pillow/CPython/
   NSIS notices сохранить. Собственную code-license/сертификат/платный договор
   не назначать/не покупать. .NET Framework не объявлять MIT modern .NET.
   Подпись/public release/upgrade/rollback/полная Windows-матрица не закрываются
   успехом этого clean-VM smoke test; WIN-54 не считать выполненным.

Существующий **Qwen не запускать, не опрашивать и не перенастраивать**. Моделей
не скачивать. Нет новых документов эмитентов/OCR/формул/прогнозов/облака/сделок/
обещаний доходности. Не исполнять код из документа/модели; worker получает только
закрытые команды, не произвольные paths/URL/SQL. Первые ошибки сохранять.

## Завершение

Сохранить `evaluation/windows_02b_<дата>/`: before/env/guest provenance/точный
artifact SHA/действия/первые ошибки/измерения/host-vs-guest различия/гейты/
сохранность. Не публиковать binaries/первичные PDF/полный текст/индекс/weights/
VM exports/секреты. Если меняется код/runtime, выполнить подходящие meaningful
checks и честно новую квитанцию; frozen gold/manifests не переписывать.

Обновить STATUS/decisions/README сохранными префиксами и roadmap02 только по
факту. Не объявлять весь02 complete при отсутствии настоящего guest install/
uninstall; не требовать приёмки формальными участниками. Сделать fresh fetch/API,
проверить main/conflicts/diff/подходящие тесты и сквозное поведение. Сохранить
allowlisted commits/push/PR/technical tag, публичную git-publication и финальную
локальную квитанцию с фактическими SHA/base/PR/tag, без merge. Подготовить
самостоятельный промт только следующего логичного этапа по реальному результату
и оставшимся gates. После промта остановиться.
