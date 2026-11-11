# WIN-02 — private runtime и installer: хост проверен, clean VM ожидается

11.11.2026. Статус: **host_validated_clean_vm_pending**.
Собран полный локальный NSIS installer WPF + private CPython + PDFium, проверены
настоящая per-user установка, запуск созданного ярлыка, расчёт/источник и удаление.
Это положительный результат на текущем компьютере. WIN-02 целиком не принят:
доступной чистой Windows11 VM нет. Следующий отдельный этап — только WIN-02B.

## Поставка и решение runtime

Сохранён выбор WPF из ADR-D01; второй GUI не развивается. В установленном пакете
нет Qt, PySide, PyInstaller, MSYS2, Ollama, psutil или ReportLab. Собственное ядро
и07 формулы не переписаны:9 файлов копируются побайтово. Компиляция прежнего WPF
дополнена новым entry point и одной явной правкой доверенного запуска worker
`-I -B -u`; исходник WIN-01 остаётся прежним. Generated source/delta hash записаны.

Private runtime — **официальный CPython3.12.10 embeddable x64**, скачанный с
python.org, не из защищённого runtime Codex. SHA ZIP проверен по официальному
SPDX SBOM; Authenticode python.exe на хосте Valid, издатель PSF. Проверка подписи
самого ZIP/Sigstore отдельно не выполнялась. `python312._pth` включает только
runtime/packages и собственные app-пути, без `import site`; pip/venv пользователю
не нужны. `-I -B` игнорирует внешнее Python-окружение и не пишет cache в установку.
[Официальный embeddable подход](https://docs.python.org/3.12/using/windows.html#the-embeddable-package),
[правила ._pth](https://docs.python.org/3.12/using/windows.html#finding-modules).

3.12.10 — последняя full-maintenance версия с готовым Windows3.12 пакетом;
последующие выпуски ветки содержат security fixes. На дату чтения страница
указывает3.12.16 как более новый выпуск. Поэтому выбранный пакет годится для
**ограниченного опыта упаковки**, но поддерживаемый runtime публичного продукта
не утверждён. Следующий выбор не должен скрыто менять старый baseline.
[Страница PSF](https://www.python.org/downloads/release/python-31210/),
[официальный SBOM](https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip.spdx.json).

WPF target — системный **.NET Framework4.8+**, installer и entry point проверяют
Release≥528040. Фактически проверен только хост4.8.1/Release533509. Runtime не
вкладывается, не переименовывается в MIT modern .NET и не устанавливается с
повышением прав. Если guest не удовлетворяет precondition, проверка прекращается;
условие нельзя ослаблять ради красивого результата. Microsoft отделяет Framework
от новых .NET и требует admin для его установки.
[Deployment guide](https://learn.microsoft.com/en-us/dotnet/framework/deployment/deployment-guide-for-developers).

Renderer: pypdfium2 5.15.2 / фактический PDFium159.0.8149.0@sourcebuild-toolchained,
Pillow13.0.0, те же проверенные wheel SHA из WIN-01. Build-only NSIS3.13 скачан из
официального проекта SourceForge и распакован в tmp; выбран zlib compressor.
Модели/новые финансовые источники не скачивались.
[NSIS release](https://nsis.sourceforge.io/Main_Page),
[NSIS licenses](https://nsis.sourceforge.io/License).

## Что реально установлено и проверено

Installer: **22434104 байт (21,40MiB)**,
SHA256 `f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf`.
Payload:271 файлов/**46157740 байт (44,02MiB)** до служебных install/uninstall
файлов. Это обе части и runtime, а не размер одного frontend EXE.
Исходники сборки: `spikes/windows_02/build.py`, `RuntimeHost.cs`, `installer.nsi`.
Точные состав/команды/хеши — `build.json`. Повторный рецепт фиксирует входы;
bit-identical повторный PE-build не заявлен.

На Windows11Pro10.0.26200/i7-14700HX/16873545728байтRAM процесс с обычным токеном
пользователя установил пакет за6,10с через `/S`. Путь вне репозитория:
`LocalAppData/Programs/Проектная практика WIN02`. Созданы Start-menu .lnk и HKCU
uninstall entry. Программа открыта через созданный .lnk, собственный PDF выбран
в native диалоге. Увидены страница1, точная зелёная рамка вокруг Operating profit18,
маржа15,00%, полный текст источника/результата и UIA Value.
Собственный PDF/SHA/период/единицы/admission сохраняют WIN-01 происхождение;
публикация неизвестна, `human_reviewer=null`, фактов эмитента не добавлено.

Установленные assets имеют read-only атрибут. Данные/логи отдельно через Windows
LocalApplicationData (`ProjectPractice/WIN02`); никакой зависимости от Git/OneDrive/
Value/cwd нет. Проверка с PATH только System32 и заведомо неподходящими
PYTHONHOME/PYTHONPATH выполнила15,00% своим python.exe; все sys.path внутри install,
isolated=1/no_user_site=1/Qt absent. Полный пакет не требует настройки Python.
На хосте сеть оставалась подключена: отсутствие реализованного network/model пути
не выдаётся за испытание физически отключённой чистой VM.

Прогресс, Escape-cancel с пустым ответом, worker crash и восстановление наблюдены
в настоящем окне;3 component runs отдельно дали по2 расчёта/5 render состояний/
cancel+gone300ms/crash23/recovery. Windows Job Object дополнительно проверен
реальным hard kill GUI во время собственного slow worker: worker отсутствовал
через500мс. Это управление своими процессами, не защитная песочница документов.

Удаление `/S` убрало собственные program files/ярлыки/HKCU запись и не оставило
own workers. Все46 существовавших файлов данных сохранили SHA. Неизвестный файл
в install folder также сохранился; recursive delete отсутствует. После доказательства
перенесён только этот наш известный контрольный файл в tmp, пустая собственная
install directory удалена нерекурсивно. Данные оставлены. User/machine PATH хеши
до и после совпали. Интерактивный click-through мастера установки отдельно не принят.

## Измерения и проверки

6 последовательных запусков установленного EXE:3 idle и3 полных component runs,
без параллельных тестов. Медиана startup до внешнего ready около0,371с;
первый0,350с, повторные около0,372с. Настоящий OS cold boot/очистка кэша не выполнены.
Опрос20мс плюс scheduling. Idle RSS медиана около128,4MiB (29–30 отсчёта в окне
ready+0,3…1,1с), peak RSS дерева полного прогона около270,7MiB. RSS повторно считает
shared pages, private bytes приведены отдельно. Gap UI полного прогона137–139мс.
Это один компьютер, маленький собственный PDF и техническая таблица10000строк,
без модели; не требования памяти всей будущей программы и не качество рынка.

10 новых package checks прошли на окончательной установленной копии v4. Это10
уникальных проверок; ранние повторения на payload/v3 не увеличивают число случаев. Два новых
negative host controls действительно отвергли повреждённый/выходящий за install
manifest до запуска Python. Проверены IPC malformed/oversize/path rejection,
source mutation, private runtime/isolation, byte identity core, crash/cancel,
8 комбинаций rotation/200% page zoom/125–200% render DPI и целостность/no cache.

Существенный предел переноса сохранён:69 старых calculator/retrieval tests с
**shipped core и чужим repo-root test context** в v3 дали41 pass/28 errors:25 path
guards и3 missing legacy contracts.py. Модуль добавлен побайтово; final v4 дал
44 pass/25 errors только на `private_path_required`. Guards не менялись. Те же
неизменённые69 tests на том же private CPython, но в их исходном repo-root
контексте, прошли69/69. Это разделяет работоспособность интерпретатора и ещё
не выполненную миграцию старых путей. Полная совместимость установленных прежних
workflow и WIN-03/04 не заявлена;799unit/18AppTest остаются историческим baseline.

## Доступность, лицензии и открытые условия

Реально проверены Ctrl+O, Escape, source/result UIA, русский19px шрифт при системных
125% и доступность нижнего результата через внешний scroll. Narrator запустился,
фокус результата наблюдён, команда чтения отправлена, но звук инструменту недоступен:
успешное слышимое чтение не подтверждено. Полный keyboard-only путь не принят.
SystemSettings.exe не открыл управляемое окно, свежая инвентаризация пуста; OS200
и OS high contrast не менялись и не проверены. Render DPI2/page zoom200 не подменяют
системные200%. Первые захваты показывали белую клиентскую область при наличии
UIA дерева; после native file-open окно отрисовалось. В final v4 контролы видны в первой
capture до взаимодействия; причина раннего белого кадра не доказана. На guest
нужен отдельный запуск до первого взаимодействия.

CPython LICENSE/SBOM, полные wheel dist-info licenses и PDFium BUILD_LICENSES
сохранены в payload и перечислены по SHA. Binding Apache2/BSD3 не покрывает
лицензии всех компонентов PDFium. Pillow MIT-CMU и встроенные notices учитываются
отдельно. NSIS/zlib COPYING включён. .NET Framework остаётся компонентом ОС.
Нельзя считать inventory завершённым юридическим/безопасностным аудитом
публичной поставки: собственной code-license/подписи нет, поддерживаемый Python
ещё надо выбрать; сертификат/платный договор не приобретались.
[Условия Python](https://docs.python.org/3.12/license.html),
[PDFium binding notices](https://github.com/pypdfium2-team/pypdfium2#licensing).

Готовой clean VM/Sandbox и известных средств управления VM в короткой
инвентаризации нет. HypervisorPresent=true само по себе не означает доступную
чистую guest-среду. Привилегии/BIOS/виртуализация/защита не менялись. Для закрытия
нужна доступная чистая Windows11x64 guest/отдельная машина с обычным пользователем,
разрешённым образом ОС и способом передачи/управления. Нельзя заменить это новым
venv или второй папкой на этом хосте.

Дальше — **только WIN-02B**: приёмка того же артефакта в чистой среде и оставшиеся
gates, с отдельным решением о поддерживаемом private Python. Не начинать WIN-03/04,
OCR, новые документы/формулы/модели или подпись/публичную поставку. Qwen не запускался,
не опрашивался и не перенастраивался. Собственные binaries/PDF/снимки/сырые логи
остаются tmp; Git содержит только свои исходники/минимальные описания/хеши.
[Полный следующий промт](../../prompts/windows_02b_clean_vm_acceptance.md).
