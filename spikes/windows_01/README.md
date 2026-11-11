# WIN-01: короткая практическая проверка native UI

Два экспериментальных окна на одном Python worker. Основной UI для следующего
spike выбран в [ADR](../../docs/windows/adr_001_native_ui.md): **WPF + Python worker**.
Это исходники стенда, не готовая программа и не установщик. Все зависимости,
PDF, снимки окон, логи и собственные сборки остаются в исключённой `tmp/`.
Старые `src/`, каталоги и формулы не изменены. Qwen не используется.

`generate_demo.py` создаёт оригинальный вымышленный PDF: МСФО, группа,
2025 год, млн RUB, выручка 120 и операционная прибыль 18. Он создаёт новый
synthetic admission с прежними определениями. `adapter.py` проверяет SHA,
заголовки и обе ячейки PDF, затем вызывает неизменный `operating_margin_v1`.
Независимый `expected.json` используется только проверками. Дата публикации
неизвестна; `human_reviewer=null`; данные не относятся к эмитенту.

`worker.py` принимает один ограниченный JSONL запрос, а путь workspace задаёт
доверенный launcher. `slow` и `crash` — явные тестовые команды разработчика.
Отдельный процесс облегчает отмену, но не является защитной песочницей.
Финансовая логика в GUI отсутствует. Поддержан только собственный PDF с тем же SHA.

Для повторения нужен stock CPython 3.12 x64 и отдельное окружение. Точные
версии и SHA колёс: [environment.json](../../evaluation/windows_01_2026-11-11/environment.json),
[wheels.json](../../evaluation/windows_01_2026-11-11/wheels.json).
ReportLab нужен только генератору (в этой проверке использована отдельная
поставляемая среда документов), не worker или native окнам.

Команды из корня проверяемого worktree (`PY` — Python нового окружения,
`DOC_PY` — среда с ReportLab; это обозначения, а не команды изменения PATH):

```text
DOC_PY spikes/windows_01/generate_demo.py tmp/demo
powershell -NoProfile -File spikes/windows_01/build_wpf.ps1
PY spikes/windows_01/launch.py wpf --label new-wpf-run
PY spikes/windows_01/launch.py qt --label new-qt-run
PY spikes/windows_01/test_slice.py
PY spikes/windows_01/test_qt.py
PY spikes/windows_01/measure.py --prefix new-measurement
PY spikes/windows_01/verify_runs.py new-measurement-qt-1 new-measurement-wpf-1
```

Каждый label должен быть новым. Замеры идут последовательно; первый запуск
процесса не равен запуску после очистки кэша Windows. Табличные 10000 строк —
только техническая нагрузка. Сумма RSS процессов повторно считает общие страницы.

PyInstaller onedir Qt собран, но **не запустился**: импорт QtCore завершился
DLL load failure на этой машине. WPF EXE запущен практически, но опирается на
системный .NET Framework 4.8.1 и внешний Python worker. Размеры этих файлов
нельзя считать размерами сопоставимых полных установщиков. WIN-02 ещё не начат.
Собственная лицензия проекта не выбрана; бинарные зависимости не публикуются.
