# WIN-02B: готовый kit при отсутствии чистой Windows

Статус: **resource_blocked_kit_prepared**. Пользователь подтвердил, что готовой
чистой VM/отдельного ПК нет. Здесь не запускается повторный host install и не
создаётся фиктивная guest acceptance. WIN-02 остаётся host_validated_clean_vm_pending.

[Сценарий](RUNBOOK_RU.md) · [Результат](../../docs/windows/clean_vm_acceptance_02b.md) ·
[Доказательства](../../evaluation/windows_02b_2026-11-11/README.md).

`prepare_kit.py` копирует неизменный проверенный v4 installer (SHA/размер
зафиксированы в коде), компилирует собственный `GuestEvidence.exe` системным csc
и собирает локальный ZIP. Новые зависимости не устанавливаются. Сборщик не
устанавливает/не удаляет приложение, не запускает Python/Ollama/модель, не
посылает сетевые запросы и не меняет настройки. На исходном компьютере он
реально возвращает `original_host_rejected` до guest-инвентаризации.

```text
DEV_PY -X utf8 spikes/windows_02b/prepare_kit.py --installer ../windows-02-worktree/tmp/build-v4/ProjectPractice-WIN02-setup.exe --out tmp/new-kit
DEV_PY -X utf8 spikes/windows_02b/verify_kit.py --build tmp/new-kit
```

`DEV_PY` — существующий Python инструментов, не команда изменения PATH.
Output должен быть новым внутри исключённой tmp/. В госте Python/SDK/pip для
коллектора не нужны. Сведения о происхождении guest в template по умолчанию
не подтверждены. Даже полные snapshots всегда имеют `guest_accepted=false`:
реальный цикл и визуальная/голосовая проверка оцениваются отдельно.

Тесты:17 синтетических boundary controls, настоящий отказ на исходном хосте,
отказ неизвестной команды, отказ installer того же размера с изменённым байтом,
CRC/распаковка/совпадение SHA installer внутри ZIP. Это проверки подготовки,
не17 успешных гостевых сценариев. Положительный путь коллектора в guest ещё не
испытан и не выдаётся за практический результат.

`host-guard.private.json` содержит salted comparison hash, не raw machine ID;
он остаётся только в локальном kit. Это защита от случайной ошибки среды, не
аутентификация и не доказательство чистоты. Не обходить её правкой config.
ZIP/EXE/частный guard/сырые checkpoints не включаются в публичный Git.
Собственная code-license/подпись не выбирались; runtime ограничения WIN-02 сохранены.

Подготовленный kit: `tmp/kit-v2/WIN02B-guest-kit.zip`,22366270байт,
SHA256 `c99bd95e771a5f8e92c442459fe6d45f96cd7f44ead59cf5ed655cc4599a0fbb`.
Внутри тот же installer22434104байт, SHA256
`f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf`.
Повторная компиляция/случайная соль дадут другой kit SHA; не приписывать ему старый.
