# КП3-05 — проверка подготовки корпуса

Результат:8 exact-PDF-версий,48 Fact/Evidence (46 новых ячеек,2 прежние),39 экономических контекстов без версии. Каталог и bindings — `../../data/catalogs/kp3_corpus_v1/`, объяснение — `../../docs/kp3/corpus_v1.md`.

- `candidates.json`: отбор/исключения, технические состояния отдельно от пригодности фактов.
- `source-checks.json`:48 минимальных записей фактической визуальной сверки. SHA/локатор/строка/колонка/исходная запись/digest/контекст. Не подтверждение человеком.
- `source-technical-record.json`: байты/страницы/хеши локальных рендеров и ограничения текстового слоя; сами рендеры/полный текст/HTML/PDF остаются только tmp/.
- `version-observations.json`: реальные варианты и отсутствующие в каталоге исходные документы; причина CFO-разницы не присвоена.
- `publication-investigation.json`: исследованные источники без выдуманной exact-публикации. Восемь unknown/unproven, historical block.
- `control-calculations.json`:8 открытых контрольных маржей Fraction/integer против Decimal80; checker воспроизводит их независимо от production.32 source bridge controls — в bindings и checker. Это не gold ответов модели.
- `check-runs.json` и собственные `.txt`: финальные334 unit-теста/03-04-05 checker/5 legacy CLI, exit0; первый успешный прогон сохранён в attempt-01. Никаких новых модельных ответов.
- `before.json`, `root-preservation-before.json`, `final-audit.json`: сохранность прежних файлов и dirty-root; единственное изменение runtime-src — явная строгая нотация с пробелами.
- `preparation-manifest.json`: хеши этой версии подготовки, **не итоговый eval freeze14**. Все данные известны разработчику, reserved unseen real=0.
- `github-prepublication.json`, `git-publication.json`: фактически проверенные main/родительские PR/защита и доставка. Последний receipt-only commit может быть новее технического тега; точный финальный head — также в локальной квитанции.

Без первичных PDF можно повторить публичные проверки `python -I scripts/check_kp3_corpus.py`. С локальной картой `--resource-map tmp/local-resources.json` отдельно проверяются байты. Missing/hash_mismatch/error не являются отсутствием показателя; prepared facts и результаты автоматического извлечения оцениваются раздельно. UI неизменён, общий extractor06/калькулятор07/parser08/сервис/агент и финальный benchmark не начаты.
