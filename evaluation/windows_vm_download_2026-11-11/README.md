# Подготовка файлов для виртуальной Windows

Этап11.11.2026: по запросу пользователя скачаны два официальных дистрибутива
для создания чистой Windows11x64. Это не installed VM и не приёмка WIN-02B.

- `before.json`: зависимая база PR22, свежая main/защита при начале;
- `host-resources.json`: минимальные сведения о ресурсах без hostname/MachineGuid;
- `downloads.json`: фактические URLs/размеры/SHA/источники сверки;
- `checks.json`: офлайн-пересчёт SHA, PE/ISO headers, подпись Oracle;
- `verify_downloads.py`: повторяемая проверка только локальных файлов;
- `preservation.json`: прежние файлы, ветки и оригинальный installer/kit сохранены;
- `report.json`: что получено, что не выполнялось, следующий шаг;
- `first-errors.json`: ограничения обнаружения ссылок, отдельно от успешной загрузки;
- `git-publication.json`: фактическая Git-доставка, без merge.

EXE/ISO, upstream HTML/checksum file, частные before snapshots и загрузочные
квитанции остаются в исключённой tmp. Тесты приложения/guest/UI не выполнялись.
Регистрация Microsoft/вход/активация/системная установка не выполнялись.

Описание и следующие действия: `docs/windows/virtual_machine_download.md` и
`prompts/windows_vm_installation_next.md`. Прежний WIN-02B kit не пересобран.
