# WIN-02B — ресурс отсутствует, пакет приёмки подготовлен

11.11.2026. **resource_blocked_kit_prepared**. Пользователь ответил «Пока нет»
на вопрос о готовой чистой Windows11 VM/отдельном ПК. Повторная краткая
инвентаризация не обнаружила Windows Sandbox, vmms/vmcompute, Hyper-V module,
известных VBox/VMware/QEMU CLI/исполняемых файлов или открытого remote/VM app.
Токен не elevated. HypervisorPresent=true не доказывает доступность чистой VM.
Гипервизор/BIOS/защита/сеть/глобальные среды не менялись.

Приёмка на guest **не выполнена**. Существующий installer не пересобирался,
не устанавливался повторно на хост и не передавался во внешнюю среду.
WIN-02 остаётся **host_validated_clean_vm_pending**, WIN-03/04 не начаты.

## Конкретный подготовленный результат

Локальный переносимый ZIP22366270байт, SHA256
`c99bd95e771a5f8e92c442459fe6d45f96cd7f44ead59cf5ed655cc4599a0fbb`.
Он включает оригинальный WIN-02 v4 installer22434104байт, SHA256
`f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf`,
свой сборщик, подробный сценарий и незаполненное происхождение guest.
Побайтовое совпадение installer проверено до копирования и внутри ZIP после
проверки CRC/распаковки. PDF/модель/SDK к installer не добавлялись.

Сборщик `GuestEvidence.exe`35840байт использует имеющийся .NET Framework.
Ни Python, ни pip, ни изменение PowerShell execution policy для него не нужны.
Он только читает metadata/собственные assets и пишет частные checkpoints;
не запускает installer/uninstaller/модель и не меняет настройки.
Четыре закрытые команды: preflight/installed/before-uninstall/uninstalled.
Произвольных команд/путей/URL/SQL из документов он не исполняет.

До guest-инвентаризации сравнивается salted machine fingerprint с исходным
хостом. Здесь **реально проверен** отказ exit21/original_host_rejected,
guest_environment_collected=false. Raw machine identifier не сохраняется;
частный comparison config остаётся внутри локального kit, не Git. Это механизм
предотвращения случайного прогона на хосте, не аутентификация и не доказательство
чистоты. Не обходить его изменением config.

В госте предусмотрены OS/client build/x64/Framework, признаки elevated token и
administrator SID, известный global Python по PATH/32–64 registry, Ollama по PATH,
состояния интерфейсов без IP/MAC, manifest/readonly/shortcut/HKCU/data hashes/
own process metadata. Отсутствие известных установок не доказывает отсутствие
любой скрытой копии; нужны источник чистого образа и ручная проверка installed apps.
Операционная сетевая metadata не заменяет подтверждение отключения NIC гостя и
фактический offline workflow. Принцип текущего token описан в
[WindowsPrincipal.IsInRole](https://learn.microsoft.com/en-us/dotnet/api/system.security.principal.windowsprincipal.isinrole?view=netframework-4.8.1),
состояние интерфейса — в
[NetworkInterface.OperationalStatus](https://learn.microsoft.com/en-us/dotnet/api/system.net.networkinformation.networkinterface.operationalstatus?view=netframework-4.8.1).

Template clean_state_declared=false; provenance проверяется по закрытой схеме,
новый venv не допускается как kind. Сборщик никогда не выставляет acceptance:
даже eligible checkpoint имеет guest_accepted=false. Hash manifests и декларация
оператора не подменяют реальные GUI/offline/Narrator/source-highlight наблюдения.
Повторные checkpoints не перезаписываются; для нового опыта нужен новый session.

## Что проверено сейчас

- 17 синтетических boundary controls: исходный host, Windows/client/x64/Framework,
elevated/filtered admin, network-up, известные зависимости, provenance и path escape.
- Настоящий отказ исходного компьютера до guest-инвентаризации и без установки.
- Отказ неизвестной команды; отказ тому же размеру installer с изменённым байтом
до создания output; целостность ZIP и совпадение bytes/hash оригинального installer.

Это known developer preparation controls. Положительный путь guest-коллектора,
его snapshots на настоящей чистой Windows и сам install/uninstall cycle ещё не
испытаны. Прежние10 installed package checks/69 original-root tests остаются
evidence WIN-02, не новые guest tests; повторно без причины не запускались.
Начальные ошибки текущего этапа и ожидаемые негативные отказы отделены.

## Что требуется для продолжения

Нужна одна конкретная контролируемая чистая Windows11x64 guest/чистый ПК с
разрешённым образом ОС, ordinary account без Administrators, известным способом
передачи kit и управления. Пользователь подтвердил отсутствие этого ресурса;
чужие формальные участники и их подписи к блокеру не относятся.

После появления ресурса выполнить [готовый runbook](../../spikes/windows_02b/RUNBOOK_RU.md):
provenance/hash → offline guest preflight → интерактивный install → shortcut/
первый экран до взаимодействия → own PDF/source15,00% → cancel/crash/recovery →
keyboard/UIA/Narrator/OS125–200/contrast → before-uninstall hash → uninstall/
data preservation/no orphan → восстановить тестовые настройки guest.
Систему хоста/существующий Qwen не менять. Реально услышанное чтение и OS200
отмечать только по факту, не по команде или render zoom.

Сохраняются25 cross-root path errors, неопределённость поддерживаемого private
Python, собственной code-license/подписи/публичного выпуска и иные WIN-02 gates.
Гостевой smoke test не закрывает WIN-03/04/54 и не подтверждает общее финансовое
качество. Презентация КП1, frozen datasets,329RCpins, старый UI/venv и ядро сохранены.
Qwen не опрашивался/не запускался, новых источников/OCR/формул/моделей нет.

Следующий промт — [возобновление после готовности guest](../../prompts/windows_02b_resume_when_guest_ready.md).
До появления ресурса не нужно делать ещё один такой же kit или повторно создавать
подготовительный PR. ZIP/EXE/частный config/сырые checkpoints остаются в tmp;
публично сохранены только исходники/сценарий/минимальные hashes и доказательства.
