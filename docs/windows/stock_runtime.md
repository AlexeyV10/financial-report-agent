# WIN-03 · Частная среда CPython для Windows x64

Для дальнейшей Windows-разработки выбран официальный embeddable CPython 3.14.10.
Он относится к той же ветке 3.14, что и прежний MSYS2 CPython 3.14.7. Архив
`python-3.14.10-embed-amd64.zip` взят по ссылке публикации Python.org. В сценарии
подготовки был указан 3.14.9, к моменту скачивания его заменил 3.14.10. Pillow
13.0.0 закреплён с ABI `cp314` и тегом `win_amd64`. pypdfium2 5.15.2 использует
свой `py3-none-win_amd64` wheel с PDFium DLL. [CPython](https://www.python.org/downloads/release/python-31410/),
[Pillow](https://pypi.org/pypi/pillow/13.0.0/json), [pypdfium2](https://pypi.org/pypi/pypdfium2/5.15.2/json).

В [закреплённых входах](../../spikes/windows_03/runtime_lock.json) указаны точные
имена, размеры и SHA-256. [Сборщик](../../spikes/windows_03/build_runtime.py)
проверяет все входы до извлечения. Каждый запуск создаёт новый каталог под
`tmp/`, включая `runtime` и манифест всех извлечённых файлов. `python314._pth`
оставляет только stdlib, каталог runtime и локальные wheels. Для потребителя
пути приложения и данных передаются отдельно. Установка pip или изменение PATH
не требуются.

## Повторить на локальных входах

Сохранить четыре файла из lock в `tmp/windows-03-inputs/` своей копии проекта.
Имена `runtime-a` и `runtime-b` должны быть свободны.

```powershell
python -X utf8 -B spikes/windows_03/build_runtime.py --downloads tmp/windows-03-inputs --out tmp/runtime-a
python -X utf8 -B spikes/windows_03/build_runtime.py --downloads tmp/windows-03-inputs --out tmp/runtime-b
Get-FileHash -Algorithm SHA256 tmp/runtime-a/runtime-manifest.json,tmp/runtime-b/runtime-manifest.json
```

В обеих сборках совпали все 248 файлов и манифест. 42 `.exe`, `.dll` и `.pyd`
проверены по заголовкам AMD64 PE. Манифест описывает байты содержимого. Время
создания каталогов и файлы, возникающие при исполняемом тесте, в сравнение не входят.

Для диагностического испытания использовать существующий собственный комплект
WIN-02. Папка `tmp/own-demo/` должна содержать его `own-demo-v1.pdf`, `manifest.json`,
`catalog.json`, `dictionary.json` и `admission.json`. Допускается передать путь
к уже подготовленной папке от штатной сборки WIN-02. Проверяется SHA PDF и
разметка источника. Код и входы диагностики следует указывать полным путём,
если команда запускается с другим рабочим каталогом.

```powershell
& tmp/runtime-a/runtime/python.exe -I -B -X utf8 spikes/windows_03/probe_runtime.py --demo tmp/own-demo
& tmp/runtime-a/runtime/python.exe -I -B -X utf8 -m unittest discover -s tests -v
```

Оба runtime подтвердили `isolated=1`, `no_user_site=1`, SQLite 3.50.4 с реальным
FTS5 MATCH и OpenSSL 3.5.9. Проверка зафиксировала происхождение DLL загруженного
процесса. Python, PDFium, SQLite, libssl, libcrypto и обе vcruntime DLL загружены
из private runtime. `ucrtbase.dll` взята из Windows System32. На штатном PDF
подтвердились `15.00`, SHA источника и четыре прежние рамки с поворотами 0°, 90°,
180° и 270°. Это диагностика среды на хосте, отдельная от прогона старого
установщика внутри гостя. Модель не участвовала.

## Регрессия

На stock CPython 3.14.10 прошли 799 из 799 тестов ядра за 210,380 с. На MSYS2
CPython 3.14.7 в повторном прогоне прошли те же 799 тестов за 234,268 с. Первый
прогон MSYS2 в песочнице получил 27 отказов создания жёсткой ссылки, один отказ
тестового loopback-порта и два падения проверок с ограничением времени. Результаты
обоих прогонов записаны в [квитанции](../../evaluation/windows_03_2026-11-19/report.json).

Отдельно 18 из 18 прежних Streamlit AppTest прошли в подготовленной копии КП3-17
с теми же файлами UI, ядра, тестов и данных. Её CPython 3.12.14 и локальный
`service-context.json` относятся к прежней оболочке. В поставку stock runtime
Streamlit не включён. Новый Windows-установщик на этом этапе не собирался.
Перенос независимых рабочих хранилищ и старые `private_path_required` относятся
к [WIN-04](../../prompts/windows_04_application_paths.md).

## Сведения о составе

В локальной сборке сохраняются LICENSE и SPDX CPython, лицензия и SBOM Pillow,
все уведомления pypdfium2 и PDFium из wheel. Windows и её системный UCRT относятся
к среде выполнения. .NET Framework требуется прежнему WPF приложению. Бинарные
артефакты остаются локальными учебными сборками. [Лицензия CPython](https://docs.python.org/3.14/license.html),
[лицензия Pillow](https://pillow.readthedocs.io/en/stable/about.html),
[уведомления pypdfium2](https://pypdfium2.readthedocs.io/en/stable/readme.html).
