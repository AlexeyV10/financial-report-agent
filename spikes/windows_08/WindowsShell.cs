using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;

internal sealed class WindowsShell : Window
{
    private enum Page { Projects, Documents, Analysis }

    private sealed class Options
    {
        internal string Install, AppData, VaultA, VaultB;
        internal bool Probe;

        internal static Options Parse(string[] args)
        {
            if ((args.Length != 6 && args.Length != 7) || args[0] != "--app-data"
                || args[2] != "--vault-a" || args[4] != "--vault-b"
                || (args.Length == 7 && args[6] != "--probe"))
                throw new ArgumentException("startup_arguments");
            var options = new Options {
                Install = TypedHost.LocalPath(AppDomain.CurrentDomain.BaseDirectory), AppData = TypedHost.LocalPath(args[1]),
                VaultA = TypedHost.LocalPath(args[3]), VaultB = TypedHost.LocalPath(args[5]), Probe = args.Length == 7
            };
            string[] roots = {options.Install, options.AppData, options.VaultA, options.VaultB};
            for (int left = 0; left < roots.Length; left++)
                for (int right = left + 1; right < roots.Length; right++)
                    TypedHost.CheckDisjoint(roots[left], roots[right]);
            return options;
        }
    }

    private sealed class ActionButton : Button
    {
        internal void ProbeClick()
        {
            if (!IsEnabled || !IsVisible) throw new InvalidOperationException("control_unavailable");
            OnClick();
        }
    }

    [DataContract]
    private sealed class ProbeReceipt
    {
        [DataMember] public string schema = "win08-shell-probe-1";
        [DataMember] public bool ok, scope_isolated, failure_result_empty, high_contrast;
        [DataMember] public double dpi_scale;
        [DataMember] public int? source_page;
        [DataMember] public string display, source_sha256, failure_error, incomplete_step;
        [DataMember] public List<string> steps = new List<string>();
    }

    private readonly Options options;
    private readonly ShellClient client;
    private readonly ActionButton[] tabs = new ActionButton[3];
    private readonly FrameworkElement[] pages = new FrameworkElement[3];
    private readonly TextBlock scope, projectSummary, documentSummary, status;
    private readonly Border statusBar;
    private readonly ActionButton selectA, selectB, importDocument, searchDocuments, runAnalysis;
    private readonly TextBox query, result;
    private readonly ListBox documents;
    private readonly ScrollViewer contentArea;
    private Page page;
    private string selectedVault, selectedName, workspaceId;
    private bool workspaceUsable;
    private bool busy, closing, probeStarted, statusIsError;
    private int scopeGeneration;
    private Task<ShellReply> worker;
    private Task operation = Task.FromResult(0);
    private ShellReply lastReply;

    private WindowsShell(Options launch)
    {
        options = launch;
        client = new ShellClient(launch.Install, launch.AppData);
        Title = "Финансовый ассистент · Рабочий стол";
        MinWidth = 340;
        MinHeight = 270;
        Width = Math.Max(MinWidth, Math.Min(920, SystemParameters.WorkArea.Width - 26));
        Height = Math.Max(MinHeight, Math.Min(660, SystemParameters.WorkArea.Height - 26));
        FontSize = 15;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        SetResourceReference(BackgroundProperty, "Canvas");
        SetResourceReference(ForegroundProperty, "Ink");

        var layout = new Grid();
        layout.RowDefinitions.Add(new RowDefinition {Height = GridLength.Auto});
        layout.RowDefinitions.Add(new RowDefinition {Height = new GridLength(1, GridUnitType.Star)});
        layout.RowDefinitions.Add(new RowDefinition {Height = GridLength.Auto});
        Content = layout;

        var header = new StackPanel {Margin = new Thickness(22, 18, 22, 8)};
        header.Children.Add(Label("Финансовые документы", 25, bold: true));
        scope = Label("Проект не выбран", 14, muted: true);
        scope.Margin = new Thickness(0, 3, 0, 12);
        header.Children.Add(scope);
        var navigation = new WrapPanel();
        tabs[(int)Page.Projects] = AddTab(navigation, "Проекты", "projectsTab", Page.Projects);
        tabs[(int)Page.Documents] = AddTab(navigation, "Документы", "documentsTab", Page.Documents);
        tabs[(int)Page.Analysis] = AddTab(navigation, "Анализ", "analysisTab", Page.Analysis);
        header.Children.Add(navigation);
        layout.Children.Add(header);

        var layer = new Grid {Margin = new Thickness(22, 0, 22, 10)};
        contentArea = new ScrollViewer {Content = layer, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled};
        Grid.SetRow(contentArea, 1);
        layout.Children.Add(contentArea);

        var projects = Section("Проекты", "Выберите хранилище для документов и расчётов.");
        var choices = new WrapPanel {Margin = new Thickness(0, 4, 0, 4)};
        selectA = Button("Выбрать проект А", "selectVaultA");
        selectA.Click += (sender, args) => SelectVault(options.VaultA, "Проект А");
        selectB = Button("Выбрать проект Б", "selectVaultB");
        selectB.Click += (sender, args) => SelectVault(options.VaultB, "Проект Б");
        choices.Children.Add(selectA);
        choices.Children.Add(selectB);
        projects.Children.Add(choices);
        projectSummary = Label("После выбора здесь появятся сведения о хранилище.", 14, muted: true);
        projects.Children.Add(projectSummary);
        pages[(int)Page.Projects] = Card(projects);

        var docs = Section("Документы", "Сохраните собственный учебный PDF в выбранном хранилище.");
        importDocument = Button("Импортировать учебный документ", "importDocument");
        importDocument.Click += ImportDocument;
        docs.Children.Add(importDocument);
        documentSummary = Label("Выберите проект, чтобы увидеть его документы.", 14, muted: true);
        documentSummary.Margin = new Thickness(0, 4, 0, 18);
        docs.Children.Add(documentSummary);
        docs.Children.Add(Label("Поиск по тексту документа", 15, bold: true));
        query = new TextBox {MinHeight = 42, MaxLength = 120, Padding = new Thickness(8),
            Margin = new Thickness(0, 6, 0, 8), VerticalContentAlignment = VerticalAlignment.Center};
        Identify(query, "documentQuery", "Поиск по тексту документа");
        query.SetResourceReference(BackgroundProperty, "Surface");
        query.SetResourceReference(ForegroundProperty, "Ink");
        query.SetResourceReference(BorderBrushProperty, "Line");
        docs.Children.Add(query);
        searchDocuments = Button("Найти в документах", "searchDocuments");
        searchDocuments.Click += SearchDocuments;
        query.TextChanged += (sender, args) => UpdateControls();
        query.KeyDown += (sender, args) => {
            if (args.Key == Key.Enter && searchDocuments.IsEnabled) { SearchDocuments(sender, args); args.Handled = true; }
        };
        docs.Children.Add(searchDocuments);
        documents = new ListBox {MinHeight = 46, MaxHeight = 178, HorizontalContentAlignment = HorizontalAlignment.Stretch};
        documents.SetResourceReference(BackgroundProperty, "Surface");
        documents.SetResourceReference(ForegroundProperty, "Ink");
        documents.SetResourceReference(BorderBrushProperty, "Line");
        Identify(documents, "documentResults", "Найденные версии документов");
        ScrollViewer.SetHorizontalScrollBarVisibility(documents, ScrollBarVisibility.Disabled);
        var wrapped = new FrameworkElementFactory(typeof(TextBlock));
        wrapped.SetValue(TextBlock.TextWrappingProperty, TextWrapping.Wrap);
        wrapped.SetBinding(TextBlock.TextProperty, new Binding());
        documents.ItemTemplate = new DataTemplate {VisualTree = wrapped};
        docs.Children.Add(documents);
        pages[(int)Page.Documents] = Card(docs);

        var analysis = Section("Анализ", "Операционная маржа по собственному учебному документу.");
        runAnalysis = Button("Рассчитать операционную маржу", "runAnalysis");
        runAnalysis.Click += RunAnalysis;
        analysis.Children.Add(runAnalysis);
        analysis.Children.Add(Label("Результат анализа", 15, bold: true));
        result = new TextBox {IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap,
            MinHeight = 88, Padding = new Thickness(9), Margin = new Thickness(0, 6, 0, 0)};
        result.SetResourceReference(BackgroundProperty, "ResultSurface");
        result.SetResourceReference(ForegroundProperty, "Ink");
        result.SetResourceReference(BorderBrushProperty, "Line");
        Identify(result, "analysisResult", "Результат анализа");
        analysis.Children.Add(result);
        pages[(int)Page.Analysis] = Card(analysis);
        foreach (FrameworkElement panel in pages) layer.Children.Add(panel);

        status = Label("Выберите проект для работы с документами.", 14);
        Identify(status, "shellStatus", status.Text);
        AutomationProperties.SetLiveSetting(status, AutomationLiveSetting.Polite);
        statusBar = new Border {Child = status, Padding = new Thickness(22, 9, 22, 10),
            BorderThickness = new Thickness(0, 1, 0, 0)};
        statusBar.SetResourceReference(BorderBrushProperty, "Line");
        Grid.SetRow(statusBar, 2);
        layout.Children.Add(statusBar);

        ApplyPalette();
        SystemParameters.StaticPropertyChanged += SystemParametersChanged;
        ShowPage(Page.Projects, moveFocus: false);
        UpdateControls();
        ContentRendered += (sender, args) => {
            if (options.Probe && !probeStarted)
            {
                probeStarted = true;
                Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(Probe));
            }
        };
        Closing += (sender, args) => {
            closing = true;
            SystemParameters.StaticPropertyChanged -= SystemParametersChanged;
            client.Dispose();
        };
    }

    private static void Identify(DependencyObject control, string id, string name)
    {
        AutomationProperties.SetAutomationId(control, id);
        AutomationProperties.SetName(control, name);
    }

    private static TextBlock Label(string text, double size, bool bold = false, bool muted = false)
    {
        var label = new TextBlock {Text = text, FontSize = size, TextWrapping = TextWrapping.Wrap,
            FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal};
        label.SetResourceReference(TextBlock.ForegroundProperty, muted ? "Muted" : "Ink");
        return label;
    }

    private static StackPanel Section(string heading, string helper)
    {
        var panel = new StackPanel();
        panel.Children.Add(Label(heading, 22, bold: true));
        var text = Label(helper, 15, muted: true);
        text.Margin = new Thickness(0, 4, 0, 12);
        panel.Children.Add(text);
        return panel;
    }

    private static Border Card(FrameworkElement panel)
    {
        var card = new Border {Child = panel, Padding = new Thickness(18), BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(8), VerticalAlignment = VerticalAlignment.Top};
        card.SetResourceReference(Border.BackgroundProperty, "Surface");
        card.SetResourceReference(Border.BorderBrushProperty, "Line");
        return card;
    }

    private static ActionButton Button(string text, string id)
    {
        var caption = new TextBlock {Text = text, TextWrapping = TextWrapping.Wrap};
        var button = new ActionButton {Content = caption, MinHeight = 42, MaxWidth = 270,
            Padding = new Thickness(12, 7, 12, 7), Margin = new Thickness(0, 0, 8, 8),
            HorizontalAlignment = HorizontalAlignment.Left, FontWeight = FontWeights.SemiBold};
        Identify(button, id, text);
        button.SetResourceReference(BackgroundProperty, "ActionSurface");
        button.SetResourceReference(ForegroundProperty, "ActionInk");
        button.SetResourceReference(BorderBrushProperty, "Line");
        var focus = new FrameworkElementFactory(typeof(Border));
        focus.SetValue(Border.BorderThicknessProperty, new Thickness(2));
        focus.SetResourceReference(Border.BorderBrushProperty, "Focus");
        focus.SetValue(Border.MarginProperty, new Thickness(-3));
        var focusStyle = new Style(typeof(Control));
        focusStyle.Setters.Add(new Setter(TemplateProperty, new ControlTemplate(typeof(Control)) {VisualTree = focus}));
        button.FocusVisualStyle = focusStyle;
        return button;
    }

    private ActionButton AddTab(Panel navigation, string text, string id, Page destination)
    {
        var button = Button(text, id);
        button.Click += (sender, args) => ShowPage(destination, moveFocus: true);
        navigation.Children.Add(button);
        return button;
    }

    private void ShowPage(Page destination, bool moveFocus)
    {
        page = destination;
        for (int index = 0; index < tabs.Length; index++)
        {
            bool active = index == (int)destination;
            pages[index].Visibility = active ? Visibility.Visible : Visibility.Collapsed;
            MarkActive(tabs[index], active, "Открыто");
        }
        contentArea.ScrollToTop();
        if (moveFocus)
        {
            Control[] firstActions = {selectA, importDocument, runAnalysis};
            FocusWhenReady(firstActions[(int)destination]);
        }
    }

    private static void MarkActive(Button button, bool active, string state)
    {
        button.SetResourceReference(BackgroundProperty, active ? "ActiveSurface" : "ActionSurface");
        button.SetResourceReference(ForegroundProperty, active ? "ActiveInk" : "ActionInk");
        AutomationProperties.SetItemStatus(button, active ? state : "");
    }

    private void FocusWhenReady(Control control)
    {
        Dispatcher.BeginInvoke(DispatcherPriority.Input, new Action(() => {
            if (!closing && control.IsEnabled && control.IsVisible)
            {
                control.Focus();
                control.BringIntoView();
            }
        }));
    }

    private static Brush ColorBrush(byte red, byte green, byte blue)
    {
        var brush = new SolidColorBrush(Color.FromRgb(red, green, blue));
        brush.Freeze();
        return brush;
    }

    private void ApplyPalette()
    {
        bool contrast = SystemParameters.HighContrast;
        Resources["Canvas"] = contrast ? SystemColors.WindowBrush : ColorBrush(243, 248, 244);
        Resources["Surface"] = contrast ? SystemColors.WindowBrush : Brushes.White;
        Resources["Ink"] = contrast ? SystemColors.WindowTextBrush : ColorBrush(20, 52, 38);
        Resources["Muted"] = contrast ? SystemColors.WindowTextBrush : ColorBrush(56, 80, 68);
        Resources["Line"] = contrast ? SystemColors.WindowTextBrush : ColorBrush(157, 181, 166);
        Resources["ResultSurface"] = contrast ? SystemColors.WindowBrush : ColorBrush(241, 248, 243);
        Resources["ActionSurface"] = contrast ? SystemColors.ControlBrush : ColorBrush(228, 241, 231);
        Resources["ActionInk"] = contrast ? SystemColors.ControlTextBrush : ColorBrush(16, 65, 40);
        Resources["ActiveSurface"] = contrast ? SystemColors.HighlightBrush : ColorBrush(22, 98, 61);
        Resources["ActiveInk"] = contrast ? SystemColors.HighlightTextBrush : Brushes.White;
        Resources["Focus"] = contrast ? SystemColors.HighlightBrush : ColorBrush(25, 114, 70);
        Resources["ErrorSurface"] = contrast ? SystemColors.WindowBrush : ColorBrush(254, 240, 237);
        statusBar.SetResourceReference(Border.BackgroundProperty, statusIsError ? "ErrorSurface" : "Surface");
    }

    private void SystemParametersChanged(object sender, System.ComponentModel.PropertyChangedEventArgs args)
    {
        if (args.PropertyName == "HighContrast" && !closing)
            Dispatcher.BeginInvoke(DispatcherPriority.Render, new Action(ApplyPalette));
    }

    private void SetStatus(string text, bool error = false)
    {
        status.Text = text;
        statusIsError = error;
        statusBar.SetResourceReference(Border.BackgroundProperty, error ? "ErrorSurface" : "Surface");
        AutomationProperties.SetName(status, text);
        var peer = UIElementAutomationPeer.FromElement(status);
        if (peer != null) peer.RaiseAutomationEvent(AutomationEvents.LiveRegionChanged);
    }

    private void UpdateControls()
    {
        bool scoped = workspaceUsable && !busy && !closing;
        selectA.IsEnabled = selectB.IsEnabled = !busy && !closing;
        importDocument.IsEnabled = runAnalysis.IsEnabled = scoped;
        searchDocuments.IsEnabled = scoped && query.Text.Trim().Length > 0;
    }

    private void ApplyWorkspaceId(ShellReply reply)
    {
        if (!String.IsNullOrEmpty(reply.WorkspaceId)) workspaceId = reply.WorkspaceId;
        scope.Text = workspaceId == null ? selectedName : selectedName + " · " + workspaceId;
    }

    private void SelectVault(string root, string name)
    {
        if (busy || closing) return;
        scopeGeneration++;
        selectedVault = root;
        selectedName = name;
        workspaceUsable = false;
        MarkActive(selectA, root == options.VaultA, "Выбран");
        MarkActive(selectB, root == options.VaultB, "Выбран");
        workspaceId = null;
        scope.Text = name;
        result.Clear();
        documents.Items.Clear();
        query.Clear();
        projectSummary.Text = "Проверяем хранилище…";
        documentSummary.Text = "Проверяем документы…";
        Start("Проверяем хранилище…", () => client.Inspect(root), reply => {
            if (reply.Error == null)
            {
                workspaceUsable = true;
                ApplyWorkspaceId(reply);
                projectSummary.Text = String.Format(CultureInfo.InvariantCulture,
                    "Документы: {0}  ·  Ревизии: {1}", reply.DocumentCount, reply.RevisionCount);
                documentSummary.Text = reply.DocumentCount == 0
                    ? "В проекте пока нет сохранённых документов." : projectSummary.Text;
                SetStatus("Проект открыт.");
            }
            else if (reply.Error == "storage_missing")
            {
                workspaceUsable = true;
                projectSummary.Text = "Проект выбран. Хранилище будет создано при импорте.";
                documentSummary.Text = "В проекте пока нет сохранённых документов.";
                SetStatus("Проект выбран.");
            }
            else
            {
                projectSummary.Text = "Сведения о хранилище недоступны.";
                documentSummary.Text = "Не удалось проверить документы.";
                SetStatus("Не удалось открыть хранилище.", error: true);
            }
        });
    }

    private void ImportDocument(object sender, RoutedEventArgs args)
    {
        if (!importDocument.IsEnabled) return;
        string root = selectedVault;
        result.Clear();
        documents.Items.Clear();
        Start("Проверяем и сохраняем учебный документ…", () => client.Import(root), reply => {
            if (reply.Error != null) { SetStatus("Не удалось импортировать учебный документ.", error: true); return; }
            ApplyWorkspaceId(reply);
            projectSummary.Text = documentSummary.Text = "Учебный документ сохранён в хранилище.";
            SetStatus("Учебный документ сохранён.");
        });
    }

    private void SearchDocuments(object sender, RoutedEventArgs args)
    {
        if (!searchDocuments.IsEnabled) return;
        string root = selectedVault, search = query.Text.Trim();
        documents.Items.Clear();
        Start("Ищем текст в сохранённых документах…", () => client.Search(root, search), reply => {
            if (reply.Error != null) { SetStatus("Не удалось выполнить поиск.", error: true); return; }
            ApplyWorkspaceId(reply);
            foreach (string row in reply.Documents) documents.Items.Add(row);
            SetStatus(reply.MatchCount == 0 ? "Совпадений нет." :
                "Найдено совпадений: " + reply.MatchCount.ToString(CultureInfo.InvariantCulture) + ".");
        });
    }

    private void RunAnalysis(object sender, RoutedEventArgs args)
    {
        if (!runAnalysis.IsEnabled) return;
        string root = selectedVault, run = Guid.NewGuid().ToString("N");
        result.Clear();
        Start("Проверяем источник и рассчитываем маржу…", () => client.Analyze(root, run), reply => {
            if (reply.Error != null)
            {
                string error = reply.Error == "source_missing" ? "Учебный документ не найден." : "Не удалось выполнить расчёт.";
                SetStatus(error, error: true);
                return;
            }
            ApplyWorkspaceId(reply);
            result.Text = "Операционная маржа: " + reply.Display + "%\nСобственный учебный PDF, страница "
                + reply.SourcePage.ToString(CultureInfo.InvariantCulture) + ".";
            SetStatus("Расчёт завершён.");
            if (page == Page.Analysis) FocusWhenReady(result);
        });
    }

    private void Start(string waiting, Func<ShellReply> request, Action<ShellReply> present)
    {
        if (busy || closing) return;
        busy = true;
        lastReply = null;
        SetStatus(waiting);
        UpdateControls();
        worker = Task.Run(request);
        operation = Finish(worker, scopeGeneration, present);
    }

    private async Task Finish(Task<ShellReply> activity, int generation, Action<ShellReply> present)
    {
        ShellReply reply;
        try { reply = await activity; }
        catch (Exception) { reply = null; }
        if (closing || generation != scopeGeneration) return;
        lastReply = reply;
        busy = false;
        if (lastReply == null) SetStatus("Не удалось выполнить операцию.", error: true);
        else present(lastReply);
        UpdateControls();
    }

    private static void Expect(bool satisfied)
    {
        if (!satisfied) throw new InvalidOperationException("unexpected_probe_state");
    }

    private void Mark(ProbeReceipt receipt, string step)
    {
        receipt.steps.Add(step);
        receipt.incomplete_step = null;
    }

    private async void Probe()
    {
        var visual = PresentationSource.FromVisual(this);
        var receipt = new ProbeReceipt {high_contrast = SystemParameters.HighContrast,
            dpi_scale = visual == null || visual.CompositionTarget == null ? 0.0 : visual.CompositionTarget.TransformToDevice.M11};
        int exit = 0;
        try
        {
            receipt.incomplete_step = "empty_project_a";
            tabs[(int)Page.Projects].ProbeClick();
            selectA.ProbeClick();
            await operation;
            Expect(lastReply != null && (lastReply.Error == "storage_missing"
                || (lastReply.Error == null && lastReply.DocumentCount == 0)));
            Mark(receipt, "empty_project_a");

            receipt.incomplete_step = "import_own_document";
            tabs[(int)Page.Documents].ProbeClick();
            importDocument.ProbeClick();
            await operation;
            Expect(lastReply != null && lastReply.Error == null);
            string firstWorkspace = lastReply.WorkspaceId;
            Mark(receipt, "import_own_document");

            receipt.incomplete_step = "search_one_match";
            query.Text = "operating";
            searchDocuments.ProbeClick();
            await operation;
            Expect(lastReply != null && lastReply.Error == null && lastReply.WorkspaceId == firstWorkspace
                && lastReply.MatchCount == 1 && documents.Items.Count == 1);
            Mark(receipt, "search_one_match");

            receipt.incomplete_step = "supervised_margin_a";
            tabs[(int)Page.Analysis].ProbeClick();
            runAnalysis.ProbeClick();
            await operation;
            Expect(lastReply != null && lastReply.Error == null && lastReply.WorkspaceId == firstWorkspace
                && lastReply.Display == "15.00" && lastReply.SourcePage == 1 && result.Text.Contains("15.00%"));
            receipt.display = lastReply.Display;
            receipt.source_page = lastReply.SourcePage;
            receipt.source_sha256 = lastReply.SourceSha256;
            Mark(receipt, "supervised_margin_a");

            receipt.incomplete_step = "separate_project_b";
            tabs[(int)Page.Projects].ProbeClick();
            selectB.ProbeClick();
            await operation;
            Expect(lastReply != null && (lastReply.Error == "storage_missing"
                || (lastReply.Error == null && lastReply.WorkspaceId != firstWorkspace))
                && documents.Items.Count == 0 && result.Text.Length == 0);
            receipt.scope_isolated = true;
            Mark(receipt, "separate_project_b");

            receipt.incomplete_step = "failed_margin_without_stale_value";
            tabs[(int)Page.Analysis].ProbeClick();
            runAnalysis.ProbeClick();
            await operation;
            receipt.failure_error = lastReply == null ? null : lastReply.Error;
            receipt.failure_result_empty = result.Text.Length == 0;
            Expect(lastReply != null && lastReply.Error == "source_missing" && receipt.failure_result_empty);
            Mark(receipt, "failed_margin_without_stale_value");

            receipt.incomplete_step = "reopen_project_a";
            tabs[(int)Page.Projects].ProbeClick();
            selectA.ProbeClick();
            await operation;
            Expect(lastReply != null && lastReply.Error == null && lastReply.WorkspaceId == firstWorkspace
                && lastReply.DocumentCount == 1 && lastReply.RevisionCount == 1 && result.Text.Length == 0);
            Mark(receipt, "reopen_project_a");

            receipt.incomplete_step = "fresh_margin_after_reopen";
            tabs[(int)Page.Analysis].ProbeClick();
            runAnalysis.ProbeClick();
            await operation;
            Expect(lastReply != null && lastReply.Error == null && lastReply.WorkspaceId == firstWorkspace
                && lastReply.Display == receipt.display && lastReply.SourcePage == receipt.source_page
                && lastReply.SourceSha256 == receipt.source_sha256 && result.Text.Contains("15.00%"));
            Mark(receipt, "fresh_margin_after_reopen");
            receipt.ok = true;
        }
        catch (Exception) { exit = 4; }
        if (closing) return;
        try { SaveProbe(receipt); }
        catch (Exception) { exit = 5; }
        ScheduleShutdown(exit);
    }

    private void SaveProbe(ProbeReceipt receipt)
    {
        for (var folder = new DirectoryInfo(options.AppData); folder != null; folder = folder.Parent)
            if (!folder.Exists || (folder.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("probe_directory_unavailable");
        using (var stream = new FileStream(Path.Combine(options.AppData, "win08-shell-probe.json"),
                 FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            new DataContractJsonSerializer(typeof(ProbeReceipt)).WriteObject(stream, receipt);
            stream.Flush(true);
        }
    }

    private void ScheduleShutdown(int code)
    {
        Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(() => Application.Current.Shutdown(code)));
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Options launch;
        try { launch = Options.Parse(args); }
        catch (ArgumentException) { return 64; }
        catch (IOException) { return 64; }
        if (!Environment.Is64BitProcess) return 64;

        var app = new Application();
        var shell = new WindowsShell(launch);
        int exit = app.Run(shell);
        if (shell.worker != null)
        {
            try { shell.worker.Wait(2500); }
            catch (AggregateException) { }
        }
        return exit;
    }
}
