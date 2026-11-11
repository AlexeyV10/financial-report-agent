# Возобновление WIN-02B после появления чистой Windows

Это промт **исполнения уже подготовленного сценария**, а не новый круг подготовки.
Пользователь11.11.2026 подтвердил: готовой чистой VM/отдельного ПК пока нет.
Не начинать WIN-03/04, академические КП3-18/19/20 или новый GUI. Общаться по-русски,
понятно первокурснику. Проект делает пользователь с Codex; чужие формальные
подписи/запуски/согласования не нужны.

Если конкретная чистая среда всё ещё не появилась, кратко назвать неизменившийся
блокер и остановиться: kit уже готов, повторно создавать такой же kit/ветку/PR
или повторять опрос о его отсутствии не надо. Не переименовывать host test в VM.

## Где лежит готовое

Root: `C:\Users\Value\OneDrive\Документы\ChatGPT\Проектная практика`.
Dirty-root `codex/kp3-01-02-scope-baseline`, старый UI/venv, неопубликованные01/02,
КП1 и архивы сохранить. Канонический WIN-02B worktree:
`tmp/windows-02b-worktree`, ветка `codex/windows-02b-clean-vm-acceptance`,
проверенная зависимая база WIN-02
`656424de05aeb81e33c5432b3c2c9530e49b0563` / `codex/windows-02-private-runtime-installer`.
PR21 был открыт при начале02B. Реальные итоговые head/base/PR/tag взять из
`evaluation/windows_02b_2026-11-11/git-publication.json` и root
`tmp/windows-02b-final-local-receipt.json`; не путать tested tag с поздним receipt head.
Свежие fetch/API обязательны. Merge не поручен, main защищена без bypass.

Прочитать AGENTS.md, workflow/github_collaboration, рабочий HANDOFF до настоящего
BEGIN_SOURCE_ARCHIVE, последние STATUS/README/decisions root и проверенной базы,
Windows roadmap, `docs/windows/clean_vm_acceptance_02b.md`, `spikes/windows_02b/README.md`
и полный **spikes/windows_02b/RUNBOOK_RU.md**, evidence02B report/kit/tests/environment/
resource-blocker/preservation. Перед значимым исполнением/исправлением создать
отдельную codex/ветку и worktree в исключённой tmp, сохранить исходные байты/хеши.
Не reset/clean/stash/force push/прямой push main, не добавлять весь root.

Локальный готовый ZIP (не в Git):
`tmp/windows-02b-worktree/tmp/kit-v2/WIN02B-guest-kit.zip`,22366270байт,
SHA256 `c99bd95e771a5f8e92c442459fe6d45f96cd7f44ead59cf5ed655cc4599a0fbb`.
Внутри тот же installer22434104байт, SHA256
`f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf`.
Он не пересобирался в02B. Private `host-guard.private.json` содержит salted
comparison hash исходного компьютера, raw ID отсутствует. Не публиковать kit,
private guard, сырые checkpoints/VM exports в Git. Перед передачей сверить hash.

Сборщик требует системный .NET Framework4.8+, без Python/pip/SDK/смены PowerShell
policy; не устанавливает/не удаляет приложение, не запускает модель и не посылает
сеть. На исходном хосте реально отказывает exit21 до guest-инвентаризации.
Не обходить это правкой config. `provenance.json` изначально не подтверждён;
source/context вводятся только по реальным сведениям. Различие machine fingerprint
и декларация не являются независимым доказательством чистоты. Даже eligible
snapshot всегда `guest_accepted=false`; приёмка требует наблюдаемого полного цикла.

## Что именно выполнить при доступном ресурсе

Нужны Windows11x64 guest/отдельная чистая машина с разрешённым образом ОС,
обычный пользователь без Administrators, способ управления и разрешённая передача
только собственного kit. Не включать BIOS/гипервизор/защиту и не устанавливать
глобальные средства на хост без существенного отдельного решения. Использовать
подходящие доступные инструменты; для настоящего UI читать computer-use skill и
после наблюдённого исхода выполнить completion_summary.

Следовать готовому RUNBOOK_RU полностью:

1. Зафиксировать provenance чистого guest, OS/build/.NET/обычную учётку, отсутствие
   известных global Python/Ollama; сохранить исходные настройки guest. Сверить kit
   и installer SHA после передачи. WindowsApps aliases не выдавать за установленный
   Python и не исполнять для проверки. Существующий Qwen на хосте не трогать.
2. Отключить сеть только guest разрешённым способом; выполнить GuestEvidence.exe
   preflight. Ни сеть/защита хоста, ни guards не меняются. Любой blocker сохранить.
3. Пройти **интерактивные** install → созданный shortcut → первый экран до кликов
   → native own PDF/page1/exact green outline/profit18 → маржа15,00%/доступный текст
   → прогресс/cancel до конца с пустым ответом → crash/no false success/recovery.
   Unicode/space path вне Git/OneDrive, private runtime/no console/no global setup.
4. Проверить фиксированный установленный ProjectPractice.exe --diagnose из
   постороннего cwd и GuestEvidence.exe installed; сравнить actual private paths/
   runtime/source SHA/read-only payload. Collector сохраняет только evidence,
   положительный guest-путь самого collector раньше ещё не испытывался: первые
   ошибки исправлять узко новой версией, не подгонять старые receipt SHA.
5. Keyboard/UIA/Narrator **с реально слышимым чтением**, OS125–200, крупные русские
   подписи, OS high contrast. Менять/восстанавливать только тестовые настройки
   guest; render zoom/DPI и отправка команды не заменяют фактическую проверку.
   Если часть недоступна, оставить exact gate, не создавать фиктивный pass.
6. Измерить startup/idle/peak/cancel/close на конкретной guest; first-process/warm
   не подменять cold boot, описать sampling/shared RSS. Сохранить закрытие/no orphan,
   before-uninstall checkpoint, обычный wizard uninstall, data hashes/unknown-file
   preservation/no shortcuts/HKCU entry/processes. Не удалять чужие данные; частные
   логи/снимки/полный UIA/audio только tmp, не автоматическая публикация.

Own demo внутри installer:2327байт,420×360, SHA
`c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451`.
Вымышленная группа, МСФО, полный2025, млнRUB, revenue120/profit18 положительные,
unknown publication/human_reviewer=null. Только это своё demo, не новые issuer PDF.

## Границы и завершение

WIN-02 до этого host_validated_clean_vm_pending;02B resource_blocked_kit_prepared.
17 synthetic gate controls, реальный host refusal, invalid-command/wrong-installer/
ZIP integrity — preparation proof, не guest tests. Host10 package checks/69
original-root tests остаются прежними.25 installed cross-root path errors сохраняются;
guards/gold не менять, full installed parity/WIN-03/04 не объявлять.
Private CPython3.12.10 — лабораторный кандидат, не утверждённый maintained public
runtime. Собственная code-license/подпись/сертификат/публичный релиз/обновления/
полная Windows matrix и WIN-54 не закрываются этим guest smoke test.

Qwen не запускать/не опрашивать/не перенастраивать, моделей не скачивать. Нет новых
источников/OCR/формул/прогнозов/облака/сделок/доходности и выполнения кода документа.
Сохранить старые файлы/RC329/старый UI-env. Подходящие новые tests — по фактическим
исправлениям collector/runtime и реально установленному поведению; без новой
причины не гонять прежние тесты просто ради суммы.

В evaluation/windows_02b_guest_<дата>/ сохранить before/guest provenance/actual
artifact SHA/сценарий/первые ошибки/измерения/host-vs-guest/gates/сохранность.
Обновить STATUS/decisions/README сохранными префиксами и roadmap02 только по факту;
не объявлять весь02 complete без настоящего guest install/uninstall. Свежие
main/PR/conflicts/diff/подходящие tests/сквозное поведение, allowlisted commits/
push/PR/technical tag, публичная git-publication и финальная локальная квитанция.
Обычная Git-доставка разрешена заранее; merge не поручен. Подготовить промт только
следующего логичного этапа по результату и остановиться.
