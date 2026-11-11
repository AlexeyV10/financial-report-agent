# Windows desktop: независимое архитектурное исследование

Дата проверки источников: 11.11.2026. Это исследование и предлагаемый ADR, без установки, сборки, изменения продукта или замеров новых стеков. Текущий запрос пользователя: универсальнее финансовые документы, сначала только локальный ИИ Qwen; облако не является runtime-зависимостью. Нет основания обещать одинаковые возможности любой Windows-машине или считать 4B-модель достаточной для произвольного сложного финансового анализа.

## 1. Основной вывод

**Моя рекомендация для данного проекта: PySide6 + Qt Widgets, отдельное Python application core и изолированные OCR/LLM workers.** UI не загружает Streamlit и не открывает localhost. На первом этапе интерфейс получает типизированные Python DTO через application-service слой; тяжёлые/недоверенные операции выполняются в отдельных процессах. Позже Qt Quick/QML можно добавить там, где оправдана сложная визуализация, но не следует сразу делать весь интерфейс custom-canvas.

Это проектный вывод, а не сравнительный benchmark. Аргументы: уже есть значительный Python core и проверенные контракты; Qt — официальный Python GUI toolkit, обычные widgets, model/view таблицы, встроенная доступность и PDF module; для пользователя можно поставлять подписанный установщик с собственным Python. Не нужны Rust/TypeScript/C# для первого desktop-пути. Визуальный стиль уже принят: светлый фон/белые карточки/зелёный акцент — его можно перенести нативными layouts/styles, не сохраняя Streamlit как hidden server.

**Главная альтернатива: .NET WPF + Python worker через локальный IPC.** Для Windows-only продукта это очень сильная долгосрочная архитектура: XAML, стандартные контролы и Windows UI Automation. Цена — два языка, межпроцессный контракт и две цепочки сборки/дистрибуции. Если небольшой вертикальный spike докажет, что Qt не даёт требуемых PDF/table/accessibility/installer характеристик, либо команда выбирает C# как основной UI-язык, WPF предпочтительнее дальнейших обходов Qt. WinUI 3 стоит проверить как современный native Windows вариант, но не выбирать автоматически только потому, что Microsoft рекомендует его новым приложениям.

Tauri и Electron — полноценные desktop-приложения, а не обязательно сайты на localhost. Однако их UI остаётся HTML/CSS/WebView, и об этом нужно говорить прямо. У пользователя здесь есть понятная потребность в самостоятельном установленном приложении; такой UX возможен в обоих классах. Предложение PySide устраняет и браузерный UI, и UI HTTP-server.

## 2. Что подтверждено первичными источниками

| ID | Источник | Что подтверждает | Что не подтверждает |
|---|---|---|---|
| W01 | https://doc.qt.io/qtforpython-6/ | PySide6 — официальные Python bindings Qt; варианты LGPLv3/GPLv3/commercial | Не гарантирует качество нашего GUI и не разрешает любую комбинацию модулей без проверки |
| W02 | https://doc.qt.io/qt-6/accessible.html | Масштабирование, keyboard navigation, assistive APIs; готовые Qt controls несут семантику | Не заменяет Narrator/UIA тесты кастомных карточек/PDF overlays |
| W03 | https://doc.qt.io/QT-6/accessible-qwidget.html | Qt реализует accessibility для собственных widgets, custom widgets требуют интерфейсов/событий | Custom-painted plot/ячейки не становятся доступными автоматически |
| W04 | https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html | pyside6-deploy — wrapper над Nuitka; deployment mode standalone/onefile; build dependencies | Не означает, что пользователь должен устанавливать компилятор или pip |
| W05 | https://www.qt.io/development/open-source-lgpl-obligations | Условия LGPL и необходимость выполнять обязательства по распространению/замене библиотек | Публичный GitHub проекта сам по себе не заменяет лицензионную проверку |
| W06 | https://doc.qt.io/qt-6.8/qtpdf-index.html | Qt PDF: render/navigation/search/text selection; документирует LGPLv3/GPLv2/commercial | Не доказывает поддержку всех повреждённых/зашифрованных PDF |
| W07 | https://learn.microsoft.com/en-us/dotnet/desktop/wpf/overview | WPF — Windows-only .NET UI, XAML/data binding/layout/vector rendering | Не доказывает меньшую стоимость разработки для нашей Python-команды |
| W08 | https://learn.microsoft.com/windows/apps/get-started/windows-developer-faq | Microsoft рекомендует WinUI 3 новым general-purpose Windows apps; Windows App SDK APIs доступны и существующим desktop frameworks | Не делает WPF непригодным и не заменяет наш ADR |
| W09 | https://learn.microsoft.com/windows/win32/winauto | UI Automation/MSAA — Windows accessibility и automation APIs | Автотесты не равны пользовательскому исследованию |
| W10 | https://learn.microsoft.com/windows/apps/package-and-deploy/deploy-overview | Framework-dependent/self-contained Windows App SDK deployment — отдельное от packaging решение | Нельзя обещать один EXE без проверки выбранной версии SDK/модели упаковки |
| W11 | https://v2.tauri.app/develop/sidecar/ | Tauri может включать external binaries, в том числе упакованный Python CLI | Sidecar не обязан быть HTTP-server; его protocol проектируем сами |
| W12 | https://v2.tauri.app/concept/inter-process-communication/ | Tauri Events/Commands и JSON-RPC-like сериализация invoke | Автоматически не валидирует финансовые полномочия наших tool commands |
| W13 | https://v2.tauri.app/security/capabilities/ | Tauri capability scopes ограничивают разрешения windows/webviews | Не изолируют автоматически произвольный Python subprocess |
| W14 | https://learn.microsoft.com/microsoft-edge/webview2/concepts/working-with-local-content | WebView2 поддерживает local files, HTML strings, virtual host mapping; mapping разрешается локально без TCP web-server | HTTPS-looking virtual origin не означает выгрузку документа в интернет |
| W15 | https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution | Evergreen и fixed runtime distribution; dependency надо учитывать при доставке | Нельзя рассчитывать на установленный runtime на всякой машине без проверки |
| W16 | https://www.electronjs.org/docs/latest | Electron включает Chromium+Node и делает cross-platform desktop UI на JS/HTML/CSS | Не гарантирует конкретное потребление RAM/размер нашего приложения |
| W17 | https://github.com/electron/electron/blob/main/docs/tutorial/security.md | Context isolation, process sandboxing, ограничение IPC/navigation/remote content — необходимые рекомендации Electron | «Это desktop» не отменяет риски внедрения web content |
| W18 | https://www.electronjs.org/docs/latest/tutorial/distribution-overview | Packaging/signing/publishing/updating — отдельные этапы desktop-доставки | Не выполняет их автоматически за наш проект |
| W19 | https://pywebview.flowrl.com/api/ | JS↔Python bridge и настройки HTTP-server; относительные local paths могут автоматически включать сервер | Нельзя назвать любую pywebview-обёртку архитектурой без localhost, не проверив фактический режим |
| W20 | https://docs.python.org/3.13/using/windows.html#the-embeddable-package | Embeddable Python предназначен как часть приложения; private runtime и vendored dependencies, без обычного user pip | Не надо навязывать пользователю существующий MSYS2/venv |
| W21 | https://pyinstaller.org/en/stable/operating-mode.html | onedir/onefile, включённый interpreter; onefile распаковывает во временную папку и медленнее стартует | Onefile не является самоцелью; он не делает продукт безопасным и не скрывает надёжно код |
| W22 | https://nuitka.net/user-documentation/user-manual.html | Compiler/toolchain требования Nuitka, самостоятельная Windows сборка | Не означает обязательного ускорения самого financial/OCR/LLM алгоритма |
| W23 | https://learn.microsoft.com/windows/win32/ipc/named-pipes | Named pipes локальные/сетевые, нужны ACL/запрет NETWORK при local-only | Имя pipe не является authentication mechanism |
| W24 | https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects | Job Objects управляют группой процессов, termination/resource limits | Это lifecycle/resource boundary, а не полноценный security sandbox |
| W25 | https://learn.microsoft.com/windows/win32/secauthz/app-isolation-overview | Win32 App Isolation/AppContainer — отдельная Windows isolation возможность | Нельзя считать обычный child process полноценной security boundary |
| W26 | https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/packaging/ | Packaged MSIX, external-location и unpackaged — разные модели | MSIX не единственный вариант для настоящего desktop приложения |
| W27 | https://learn.microsoft.com/en-us/windows/msix/app-installer/auto-update-and-repair--overview | App Installer даёт управляемые update/repair механизмы вне Store с OS-version ограничениями | Не отменяет миграции БД и rollback-план приложения |
| W28 | https://jrsoftware.org/ishelp/topic_admininstallmode.htm | Inno Setup поддерживает non-administrative install | Не доказывает необходимость admin для обычного пользователя |
| W29 | https://jrsoftware.org/ishelp/topic_setup_signeduninstaller.htm | Подпись установщика/uninstaller настраивается отдельно | «Подписан setup» не означает автоматически подписаны все workers/DLL |
| W30 | https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation | Signature и SmartScreen reputation — разные вещи; новый signed download может получать предупреждение | Нельзя обещать мгновенное исчезновение предупреждений от покупки сертификата |
| W31 | https://learn.microsoft.com/windows/msix/package/signing-package-overview | Production/dev signing варианты, Store signing; региональная/identity eligibility требует проверки | Не подтверждает доступность конкретной платной signing-службы пользователю из любой страны |
| W32 | https://learn.microsoft.com/en-us/dotnet/standard/security/how-to-use-data-protection | Windows DPAPI/ProtectedData применим к данным/секретам пользователя | SQLite не становится encrypted просто от помещения в AppData |
| W33 | https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid | Known folders для корректных пользовательских путей Windows | Не надо строить пути из имени пользователя Value или root OneDrive |
| W34 | https://github.com/ollama/ollama/blob/master/LICENSE | Код Ollama под MIT | Лицензия inference engine не является лицензией любых weights |
| W35 | https://github.com/ggml-org/llama.cpp/blob/master/LICENSE | llama.cpp под MIT | Отдельно учитывать библиотеки GPU/backend и их redistribution |
| W36 | https://huggingface.co/Qwen/Qwen3-4B | Официальная model card Qwen3-4B Apache2.0 | Не переносить эту лицензию автоматически на любую модель с названием Qwen |
| W37 | https://huggingface.co/Qwen/Qwen3-4B-GGUF | Официальный GGUF Qwen3-4B Apache2.0, llama.cpp deployment examples | Другой quantizer/template/revision не равен прежней оценённой версии |
| W38 | https://docs.ollama.com/faq | Local-only с OLLAMA_NO_CLOUD/disable_ollama_cloud; управление bind/context; CPU/GPU placement | Local-only надо проверять настройками и сетевыми тестами, не только названием модели |
| W39 | https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md | Разные CPU/GPU backend paths, включая Vulkan | Нельзя обещать ускорение на каждом драйвере/GPU без теста |
| W40 | https://pymupdf.readthedocs.io/en/latest/about.html | PyMuPDF/MuPDF AGPL или commercial | Нельзя включать в будущий closed продукт как заведомо permissive компонент |
| W41 | https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE | Tesseract Apache2.0; отдельно учитывать dependencies | Лицензия не доказывает OCR accuracy на финансовых таблицах |

Веб-страницы могут показывать evolving latest/snapshot docs. Это не рекомендация перейти на упомянутую latest-версию. Конкретные supported versions/lockfiles/redistributables выбираются только после build spike и снова сверяются перед выпуском. Числа затрат/бинарных размеров/производительности не измерялись.

## 3. Сравнение стеков для этого продукта

| Вариант | UI без localhost | Перенос существующего core | Сильные стороны | Основная цена/риски | Вывод |
|---|---|---|---|---|---|
| PySide6 + Qt Widgets | Да, не HTML UI | Python остаётся Python | Таблицы/model-view, desktop dialogs, native PDF module, единый основной язык | Packaging Qt plugins, high-DPI/accessibility custom widgets, LGPL/module audit | Предлагаемый default |
| PySide6 + QML/Qt Quick | Да, не браузер | Python model/service bridge | Богатые transitions/cards/графика, адаптивность | Два способа UI, QML binding/lifecycle, accessibility custom items, сложнее таблицы | Добавлять адресно после proof |
| WPF + .NET + Python worker | Да, Windows desktop XAML | Через IPC, не переписывать математику | Windows UIA/data binding, mature desktop controls, Windows-only фокус | C#+Python build/release, DTO/IPC, PDF renderer integration | Предпочтительная запасная архитектура |
| WinUI 3 + Python worker | Да, WinUI/Windows App SDK | Через IPC | Современные Windows controls/Fluent/platform APIs | SDK/runtime/packaging choices, bridge, отдельная экосистема | Проверить маленьким spike, не full rewrite по моде |
| Tauri2 + web UI + Python sidecar | Да, можно custom protocol + IPC | Python sidecar; Streamlit view всё равно переписывается | Малый native shell, web-дизайн, scoped capabilities | Rust+TS+Python, WebView2 distribution, security/API bridge | Подходит если embedded HTML UI осознанно принят |
| Electron + Python worker | Да, file/custom protocol+IPC | Sidecar, новый view | JS-компоненты/таблицы/экосистема, управляемый Chromium | Chromium+Node distribution/update/security, baseline ресурсы | Нужна веская причина, не default для этой базы |
| pywebview | Возможно, зависит от режима | Простая Python↔JS связь | Быстрый desktop proof | Поведение local content/http_server, меньше структурных guards, web UI остаётся | Только короткий прототип, не стратегическая «обёртка ST» |
| Streamlit в скрытом браузере/local server | Фактически нет | Высокий reuse старого view | Быстро упаковать прежний demo | Не решает поставленную архитектурную задачу | Сохранить как legacy/reference, не целевой продукт |

Ни «Qt native», ни «WPF native» не означают, что все элементы — системные WinUI controls. Здесь native означает standalone desktop GUI/runtime без браузерной страницы/HTTP UI. Tauri/Electron тоже standalone desktop, но rendering web-based. Это различие надо сохранить в выборе с пользователем.

## 4. IPC и границы процесса

### Начальная структура

`Windows GUI -> ApplicationService -> existing financial domain`.

Отдельно `ApplicationService -> Document/OCR worker` и `ApplicationService -> LocalModel worker`. GUI thread не выполняет PDF parsing/OCR/LLM. В первом PySide пути лёгкие обращения могут быть прямыми Python calls, но DTO/события сразу проектируются сериализуемыми, чтобы перенос worker в процесс не менял финансовую семантику.

Для .NET UI используем parent-owned child Python process и framed UTF8 JSON-RPC/stdio. Для background/reconnect/multi-window — named pipes с ACL только текущего пользователя, remote clients запрещены, handshake protocol/worker build/version/capabilities, случайный session nonce; не считать pipe name секретом. Нужны bounded length-prefixed frames (или строго ограниченный JSONL), request_id/run_id, cancel, progress, completion receipt, timeout, heartbeat, stderr отдельно от protocol stdout, backpressure и перезапуск только как новая явная попытка.

Команды приложения: importSelectedFile(token), getDocument(document_id), searchEvidence(spec), calculateRegistered(operation, factrefs), buildScenario(spec), exportAnalysis(run_id, destinationToken), cancelJob(job_id). LLM не получает API произвольного shell/Python/SQL/openURL/readFile(path). Системный file dialog/явный импорт дают trusted handles/IDs, а пользовательский финансовый вопрос — только данные. Полный JSON answer/schema не смешивать с процентным форматированием GUI.

Job Objects нужны для завершения дерева собственных workers, CPU/RAM accounting и отсутствия сирот/late writes. Это не полноценная песочница. Для PDF/OCR добавлять restricted token/AppContainer после совместимого spike, минимальные разрешения/temp-folder, отсутствие сети, лимиты страниц/декомпрессии/размера/DPI/времени, проверку output schema/hash. Обычный subprocess с timeout не должен называться «безопасным sandbox».

### Удаление старых серверных маршрутов

Новый viewer принимает document_id/version/SHA/page и локальные render buffers/immutable files через application API. Ссылки SourceViewer13 localhost/page и HistoryDownloads13 localhost/export остаются legacy-compatible путём для прежних тестов, но desktop UI их не использует. «Открыть источник» открывает встроенную страницу с подсветкой и точным source locator; «Сохранить» использует системный save dialog и атомарную запись. Нельзя просто открыть произвольный URL/path из model output в native shell.

## 5. Непереносимые предположения текущего проекта

Текущие ServiceContext/ScenarioContext/RunStore/retrieval guards привязаны к `ROOT/tmp`, UI запускается из worktree, основной Python MSYS2 и UI venv3.12 существуют у разработчика отдельно. Это не end-user deployment contract.

Нужен явный `ApplicationPaths/WorkspaceContext`:

- install resources/code — immutable versioned app directory, не пользовательские документы;
- `%LocalAppData%/Product/workspaces/...` — vault/DB/index/jobs/model-cache, либо явно выбранная папка workspace;
- никакого имени Value, абсолютной OneDrive директории разработчика или зависимости от git;
- прежний ROOT/tmp — только explicit legacy adapter/profile для сохранения 799 regression и исходных artifacts;
- отдельно versioned DB schema/migrations/source admission/formula definitions; не копировать старые gold/expected в runtime;
- в core новый путь вводится отдельной версией с compatibility adapter, а не monkeypatch ROOT/globals или ослаблением path guards;
- migration report показывает перенесённые verified snapshots и отдельно исходные публикации/права/provenance; неизвестное не повышается автоматически.

База: single-writer application service, SQLite transactions/WAL по проверенному режиму, immutable source blobs с SHA, индексы пересоздаваемые/версионированные, резервная копия через consistent DB snapshot, а не копирование живого sqlite-файла без WAL. Секреты — OS-protected storage/DPAPI, но само размещение DB в AppData не шифрует документы. Для шифрования vault нужен отдельный recovery/key-rotation дизайн. Cloud sync не включать по умолчанию, особенно для выбранных confidential financial documents.

## 6. Локальный Qwen: два допустимых deployment режима

### Переходный: управляемая Ollama

Приложение поставляет/проверяет отдельный pinned engine и контролирует только собственный процесс: executable SHA, модель revision/digest/template/parameters, loopback binding, cloud disabled, отдельная model directory, ограничения concurrency/context/output, cancellation и диагностический экран. Пользователю не нужен терминал или ручной запуск сервера. Доступный чужой Ollama endpoint не считать автоматически своим процессом, не останавливать его. Нельзя принуждать к установке глобальной Ollama/службы для basic mode.

Здесь UI полностью native, а **inference использует loopback HTTP**. Это допустимая архитектура desktop, но не «вообще ни одного localhost endpoint». Если пользователь требует отсутствие всех listening TCP endpoints, этот режим не соответствует более строгому требованию.

### Целевой кандидат: llama.cpp worker без HTTP

Qwen GGUF загружается отдельным own inference worker через C API/binding; запросы идут по локальному IPC. Это убирает TCP model-server и позволяет управлять жизненным циклом/памятью приложения. Нужен spike: Windows CPU/CUDA/Vulkan binaries, Unicode paths, streaming/cancel/grammar/tool JSON, prompt template equivalence и повторные developer-known+new holdout оценки. Замена Ollama на llama.cpp **меняет оцениваемую inference implementation**, и старые227nativechat/latencies нельзя приписать новому стеку.

До spike не выбирать runtime по «он быстрее» без measured quality/latency/RAM. Не использовать CLI interactive stdout как готовый стабильный production protocol, если там смешаны token stream и diagnostic text: нужен контролируемый versioned worker wrapper.

### Лицензии и model distribution

Официальные Qwen3-4B и Qwen3-4B-GGUF model cards маркируют Apache2.0; Ollama и llama.cpp — MIT. Это пригодная основа для локальной дистрибуции при выполнении условий конкретных licenses, notices, attribution и third-party dependencies. Нельзя распространять вывод на все модели семейства Qwen, все quantized derivatives или чужие OCR/VLM weights.

Model catalog должен содержать model_id/revision/sha256/byte_length/license source/license copy/NOTICE/tokenizer/chat template/quantization/compatible runtime/context/support profile. Загрузка — явное действие пользователя, размер/free space до старта, resumable download, подпись каталога+SHA, staged verify before atomic activation, offline import того же approved model pack. AI модель не должна загружаться автоматически при первом документе. Offline core functions остаются полезными без weights.

## 7. Аппаратная доступность

Не обещать «любой пользователь получит full reasoning на любом ПК». Предлагаемый product-level split:

1. Basic CPU mode без LLM: импорт/read/view/OCR-compatible path, поиск, проверенные таблицы/числа, зарегистрированные коэффициенты, графики, история, экспорт. Возможность полноценного отключения AI.
2. Local small-model mode: Qwen небольшого размера для bounded extraction proposals/классификации/объяснения выбранных verified facts; не скрывать ограничение качества. Подбирать модель автоматически по измеренному свободному RAM/VRAM и короткому consented diagnostic, а не по одному объёму файла weights.
3. Recommended local4B mode: существующий Qwen3:4b — стартовая контрольная точка, а не модель, доказанная для всех типов документов. На каждом поддержанном CPU/GPU нужно измерить batch/page latency, tokens/s, time to first token, peak commit/RAM/VRAM, cancellation, thermal behaviour.
4. Advanced local model pack — optional, только после отдельного качества/ресурсов/лицензии. Можно хранить provider seam для будущего облака, но cloud пока не включать и не требовать.

Ориентиры8GB basic/16GB recommended/32GB advanced можно рассматривать как **кандидаты требований для измерения**, а не проверенные минимумы. На текущей машине16GB работал узкий known-corpus сценарий; это не доказательство универсального PDF/OCR/LLM pipeline. Память PDF images, KV cache, reranker/embedding/OCR weights и UI нужно считать совместно. Один GPU-heavy job одновременно, ленивые thumbnails, ограниченный page cache, page-at-a-time OCR, stop/load model по явному job lifecycle. GPU/сеть не должны быть условием открытия документа или просмотра уже проверенных результатов.

## 8. Установка, обновление и поддержка «обычного пользователя»

Первый публичный канал — один подписанный installer, Start menu shortcut, uninstall entry, double-click, no terminal/no git/no MSYS/no pip/no model server setup. App хранит код отдельно от данных. Для developer-known closed pilot можно ограничиться onedir+installer; onefile не является критерием качества: PyInstaller сам описывает распаковку/дополнительное время старта и советует сначала проверить onedir.

Разделить сборку Python runtime, GUI shell, OCR/language packs, model packs и источники данных. Основной installer не должен содержать гигабайты всех моделей и автоматически скачивать unknown assets. Installer также должен работать при прерванной загрузке, без admin для per-user варианта, с Unicode/space usernames, low disk, controlled folder access, корпоративным proxy/offline mode и обновлением с rollback.

MSIX/Store — желательный последующий канал: package identity, упорядоченная установка/обновление, но надо проверить bundled workers/GPU libs/user-data permissions/current Store rules/region eligibility. Signed EXE/InnoSetup — более гибкая первая доставка; автоматические обновления тогда нужно реализовать отдельно с signed manifest, immutable version directories, загрузкой во staging, проверкой SHA/signature, переключением после закрытия jobs и схемой rollback данных.

Не считать self-signed cert production trust. Не обещать, что OV/EV/подпись сразу уберут SmartScreen. Не обучать пользователя отключать SmartScreen/Defender. Нужны реальная проверка скачанного installer с Mark-of-the-Web в clean VM, trusted publisher path, документация/канал поддержки и подписанные executable/worker/DLL/installer/uninstaller по выбранной схеме. Возможность приобрести подходящую signing-службу/сертификат конкретным владельцем и регионом проверяется отдельно; исследование не подтверждает этого.

Набор release gates: чистая VM без Python/Ollama, ограниченный пользователь, установка/первый запуск/basic offline/import/view/calc/export; optional model download/import; обновление N→N+1 с открытой БД и rollback; восстановление backup; удаление приложения с отдельным явным выбором удаления пользовательских данных; отсутствие orphan workers/служб; подписи и license/NOTICE inventory. Диагностика выгружается только с preview/redaction, без автоматической отправки confidential docs.

## 9. UI/доступность и тестирование

Предпочитать стандартные accessible widgets и table models; каждому действию дать устойчивый AutomationId/accessibleName, отдельные роли для sum/percent/pp, label/value/unit/source. Фокус после завершения job и ошибки управляется явно, tab-order не скачет. Keyboard-only/Narrator/high contrast/125–200% DPI/large font — release requirements, а не финальная косметика. У status есть текст, не только цвет. Руководящий режим «что это значит» не заменяет точный источник.

PDF overlays должны совпадать с crop/rotation/page coordinates при всех DPI/zoom; текст/таблица доступны как альтернативная accessible view, не только raster screenshot. Для источника отображать страницуPDF и печатную, исходный знак/скобки/валюту/масштаб, отдельный показатель доверия для OCR/структуры/смысла. Background progress показывает реальную стадию и cancel, а не вечный spinner.

Тесты: domain regression независимо от GUI, contract tests IPC/version/oversized messages/cancel/deadline/stale run, component/view-model tests, Windows UIA automation, реальные clean-VM installer workflows и внешнее usability testing с начинающими аналитиками/обычными пользователями. Старые18AppTest остаются proof legacy Streamlit, не считаются тестами Qt/WPF. Текущие143developer probes включают mocks и не доказывают sandbox/безопасность нового desktop.

## 10. Предлагаемые ADR и spikes

ADR-D01 (proposed): Native desktop PySide6/QtWidgets; WPF fallback. Критерий пересмотра: PDF/table/UIA/high-DPI/packaging spike не проходит либо обнаруживается неприемлемая лицензионная/дистрибуционная проблема.

ADR-D02 (proposed): `ApplicationService`/DTO отделён от GUI, отдельные document/LLM processes; readonly renderer. Финансовый engine не переписывать на C#/Rust ради смены UI.

ADR-D03 (proposed): App-local private CPython, per-user workspace, own process lifecycle; никакого обязательного глобального Python/Ollama/администратора.

ADR-D04 (proposed): Local-only by default and in initial release; versioned model-pack catalog. Managed Ollama transitional compatibility, llama.cpp no-TCP candidate after measured parity. Не обещать binary-identical ответы при смене runtime.

ADR-D05 (proposed): Signed installer/updates, no security bypass. Дистрибуция отдельна от выбораUI.

Ранние spikes перед большой реализацией:

- S1 — Qt против WPF на одном идентичном vertical slice: открыть own fixture PDF, native table10000rows, sourcehighlight, одна старая07операция, progress/cancel, keyboard+Narrator+200%DPI. Измерять startup/RAM/installer size, не оценивать по screenshot.
- S2 — Packaging на чистой Windows11 x64 VM без Python/Ollama и обычным пользователем: pinned runtime/plugins/PDF renderer, no PATH changes/no console. Результат installer+inventory+reproducible build receipt.
- S3 — Workspace migration: перенос Root/tmp к AppData через явный path context; сохранять snapshots/unknownpublication, duplicate/rollback/cancel; не ослаблять source/path guards.
- S4 — IPC/job hardening: partial/oversized/bad UTF8 JSON, worker crash/latewrite, doubleclick, stalecontext, close/reopen. UI не зависает, существующий ответ не становится текущим.
- S5 — Local inference A/B proof Ollama vs llama.cpp на заранее заданных русских extraction/summary/tool tasks и hardware tiers; source evidence и финансовая арифметика вне LLM. Сохранять первые неуспехи/новуюверсию, не менять gold по output.
- S6 — License/signing/distribution inventory: Qt modules/PDF/OCR/weights/GPUredistributables, собственная лицензия проекта, publisher identity и доступный signing path, installer rollback. До выбора closed/open commercial distribution нельзя считать audit закрытым.
- S7 — PDF scaling/coordinates/accessibility на born-digital/scan/mixed/rotation/multipage/oversized/encrypted examples, без новых обещаний unsupported inputs. OCR/extraction accuracy отдельно от viewer success.

Spikes должны иметь критерии остановки и фиксированный короткий timebox, не превращаться в две полноценные реализации UI. Оценки срока пока качественные; фактический календарь строить после spikes и доступной мощности одного разработчика+Codex, а signing/Store approval и внешняя пользовательская проверка — отдельные внешние зависимости.

## 11. Дополнительные выборы без неподтверждённых рекомендаций

Qt module licenses проверяются по конкретной версии и каждой используемой библиотеке; не считать любой charts/webengine/pdf module равнозначным PySide license. PyMuPDF/MuPDF требуют AGPL/commercial проверки; текущий Poppler нельзя автоматически переносить в closed installer без соответствующих обязательств. Для plotting кандидат — permissive PyQtGraph/MIT или собственные простые plots, но выбрать по доступности/performance/export tests. Для OCR Tesseract Apache2.0 — только лицензионный факт, не сравнительная точность; language packs/dependencies требуют отдельной проверки.

Вариант Qt PDF подтверждён для конкретной документированной6.8ветки; не брать автоматом latest snapshot. Renderer должен быть под сменным интерфейсом, чтобы лицензия/уязвимость/сбой не заставили переписать финансовый engine. Выбранный PDF и текст остаются локальными данными пользователя, отдельными от public code/updates/models.
