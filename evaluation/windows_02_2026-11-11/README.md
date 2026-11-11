# WIN-02 — private runtime/installer, 11.11.2026

**host_validated_clean_vm_pending**: полный локальный WPF/private Python/PDFium
installer установлен/проверен/удалён на текущем компьютере; чистая VM не проверена.
[Подробный результат](../../docs/windows/installer_spike_02.md),
[код и рецепт](../../spikes/windows_02/README.md),
[следующий WIN-02B](../../prompts/windows_02b_clean_vm_acceptance.md).

- `before`, `parent-before`, `root-before`, `github-before` — исходная база,
  статусы и byte hashes; `environment` — доступные инструменты/точная среда.
- `downloads`, `build`, `licenses` — источники/SHA/реальный состав/notice inventory.
- `host-install`, `host-diagnostic`, `host-measurements`, `measurement-summary`,
  `host-parent-crash`, `host-uninstall` — фактический цикл на хосте.
- `tests`, `ui-observations`, `first-errors`, `remaining-gates`, `report` — результаты
  с честными границами; full installed parity отсутствует.
- `commands`, `local-evidence-index` — рецепт и хеши локальных сырых доказательств.
  Они, PDF, binaries и снимки не загружаются в Git.
- `validate_stage.py`, `preservation.json` — сохранность прежнего кода/данных,
  исторических суффиксов,329RCpins и старого UI-окружения.
- `git-publication.json` — фактические PR/тег/tested stage после доставки;
  финальный receipt head — в root `tmp/windows-02-final-local-receipt.json`.

10 package checks прошли в окончательной установленной копии.69 старых tests
прошли на private Python в прежнем repo-root context;25 shipped cross-root
path errors сохранены, guards не ослаблены. Существующий Qwen не опрашивался.
WIN-03/04 не начаты, merge и публичная binary release не поручены.
