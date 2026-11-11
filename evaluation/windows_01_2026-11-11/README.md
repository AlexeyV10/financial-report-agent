# WIN-01 — сравнительный native feasibility, 11.11.2026

Итог: **WPF + общий Python worker** выбран для следующего spike.
Qt из исходников работает, но его паузы и неуспешный запуск onedir остаются
конкретными ограничениями. [ADR](../../docs/windows/adr_001_native_ui.md) объясняет
выбор, лицензии, измерения и оставшиеся проверки. Это не готовый installer.

- `before.json`, `root-before.json`, `parent-before.json`, `github-before.json` —
  фактическая исходная база/статусы/хеши, без содержимого первичных документов.
- `environment.json`, `wheels.json`, `builds.json`, `commands.json` — версии,
  хеши, состав собственного артефакта и команды. Установка только в новом tmp/.
- `demo.json`, `tests.json`, `component-runs.json` — происхождение собственного
  PDF и проверяемые результаты. Сами PDF/снимки/бинарники не публикуются.
- `measurements.json`, `ui-observations.json`, `first-errors.json` — измерения,
  реальные действия, первые неуспехи и точные пределы выводов.
- `local-evidence-index.json` — хеши локальных снимков/логов/сырых отсчётов.
- `validate_stage.py`, `preservation.json` — проверка неизменности старых файлов,
  329RCpins и сохранённых исторических суффиксов документов.
- `git-publication.json` — фактические PR/тег/проверенный stage commit после доставки.
  Финальный head после receipt commit — в локальной квитанции исходной папки
  `tmp/windows-01-final-local-receipt.json`; не путать его с target тега.

15 новых tests и8 component runs — известные developer controls, не независимая
оценка качества на новых эмитентах и не полная accessibility acceptance.
Narrator speech, системный контраст, WPF OS200 и настоящий cold boot не приняты.
Существующий Qwen не опрашивался и не запускался. WIN-02 не начат; merge не поручен.
