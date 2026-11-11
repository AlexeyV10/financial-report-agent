# WIN-02: локальный private runtime и per-user installer

Проверена установленная WPF-копия с собственным Python/PDFium и удаление на
текущем Windows11 компьютере. **Чистая VM недоступна, приёмка WIN-02 не закрыта.**
[Результат и границы](../../docs/windows/installer_spike_02.md),
[доказательства](../../evaluation/windows_02_2026-11-11/README.md),
[следующий WIN-02B](../../prompts/windows_02b_clean_vm_acceptance.md).

`build.py` создаёт полный локальный payload и NSIS installer. Нужны явные входы:
официальные CPython3.12.10 embeddable x64 + NSIS3.13 ZIP, колёса
pypdfium2 5.15.2/Pillow13.0.0 с зафиксированными SHA и собственный demo WIN-01.
Зависимости не устанавливаются в глобальную среду; код не скачивает их автоматически.
CPython3.12.10 — последний full-maintenance Windows пакет ветки3.12, уже есть
более новые security source releases. Это кандидат для опыта упаковки, а не
утверждённый поддерживаемый runtime публичного выпуска.

Пример из отдельного worktree (`DEV_PY` — существующий Python инструментов;
обозначение не является командой изменения PATH):

```text
DEV_PY -X utf8 spikes/windows_02/build.py --downloads tmp/downloads --wheels ../windows-01-wheels --demo ../windows-01-worktree/tmp/demo --out tmp/new-build
DEV_PY -X utf8 spikes/windows_02/test_package.py --payload tmp/new-build/payload
```

Выходная папка должна быть новой и находиться внутри исключённой `tmp/`.
Исходные URL/SHA — `evaluation/windows_02_2026-11-11/downloads.json`, SHA колёс —
предыдущий `evaluation/windows_01_2026-11-11/wheels.json`.
Фактические команды/состав/SHA сборки — `evaluation/windows_02_2026-11-11/build.json`.
Сборка включает временные PE-данные: побайтовая идентичность повторных EXE не заявлена.

`RuntimeHost.cs` выбирает runtime/readonly assets относительно установленного EXE,
а пользовательские данные — через Windows LocalApplicationData. Никаких
Value/OneDrive/Git/cwd defaults в установленном entry point нет. `.NET Framework4.8+`
проверяется, не устанавливается автоматически; на хосте фактически4.8.1.
Worker запускается с `-I -B`, `._pth` задаёт только внутренние пути, site/pip нет.
Из старого ядра копируются9 собственных файлов побайтово. Прежний WPF-source не
меняется: builder применяет единственную CLI-правку `-u` → `-I -B -u` к временной
копии для компиляции. UI-финансовая арифметика не добавляется.

Windows Job Object завершает собственных workers при аварийном выходе GUI.
`payload.json` проверяет целостность файлов, но **не аутентифицирует** неподписанную
поставку. Не надо считать checksum заменой подписи.

`installer.nsi` устанавливает только для текущего пользователя в
`LocalAppData/Programs/Проектная практика WIN02`, создаёт Start-menu shortcuts и
HKCU uninstall entry. Устанавливаемые assets получают read-only атрибут;
uninstaller снимает его только со списка собственных файлов. Данные отдельно:
`LocalAppData/ProjectPractice/WIN02`. Удаление сохраняет данные и неизвестные файлы
в install folder; рекурсивного удаления нет. Повторную установку в занятую папку
стенд отклоняет. Обновление/откат/low-disk recovery не реализованы как продукт.

`--diagnose` и `--probe` — фиксированные developer controls собственного EXE,
без свободных путей/кода/URL. `check_host.py` — явные автоматизированные команды
установки/измерения/аварии/удаления **на хосте**. Они меняют только указанную
per-user установку и создают свои контрольные данные; это не тесты на чистой VM.
Не применять их к чужой существующей установке.

В Git нет installer/ZIP/колёс/PDF/DLL/снимков. Локальный проверенный installer:
`tmp/build-v4/ProjectPractice-WIN02-setup.exe`,22434104байт,
SHA256 `f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf`.
Собственная лицензия проекта и подпись не выбраны. Qwen не запускался и не опрашивался.
