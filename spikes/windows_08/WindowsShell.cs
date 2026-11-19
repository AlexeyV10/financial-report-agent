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
    private enum Page { Projects, Documents, Analysis, Viewer }

    private sealed class Options
    {
        internal string Install, AppData, VaultA, VaultB;
        internal bool Probe, ProbeViewer;

        internal static Options Parse(string[] args)
        {
            if ((args.Length != 6 && args.Length != 7) || args[0] != "--app-data"
                || args[2] != "--vault-a" || args[4] != "--vault-b"
                || (args.Length == 7 && args[6] != "--probe" && args[6] != "--probe-viewer"))
                throw new ArgumentException("startup_arguments");
            var options = new Options {
                Install = TypedHost.LocalPath(AppDomain.CurrentDomain.BaseDirectory), AppData = TypedHost.LocalPath(args[1]),
                VaultA = TypedHost.LocalPath(args[3]), VaultB = TypedHost.LocalPath(args[5]),
                Probe = args.Length == 7, ProbeViewer = args.Length == 7 && args[6] == "--probe-viewer"
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

    private sealed class SourceScope
    {
        internal string Vault, WorkspaceId, RunId, ResourceId, Sha256;
        internal int PageIndex, Generation;
    }

    [DataContract]
    private sealed class ViewerProbeReceipt
    {
        [DataMember] public string schema = "win09-viewer-probe-1";
        [DataMember] public bool ok, alternative_text_verified, scope_cleared, return_to_analysis;
        [DataMember] public bool panning_verified;
        [DataMember] public double dpi_scale, panning_offset_before, panning_offset_after;
        [DataMember] public int page_index, page_count;
        [DataMember] public string printed_page, pdf_page_label, display, source_sha256, incomplete_step;
        [DataMember] public string operation_error;
        [DataMember] public List<string> steps = new List<string>();
        [DataMember] public List<ViewerFrameReceipt> views = new List<ViewerFrameReceipt>();
    }

    [DataContract]
    private sealed class ViewerFrameReceipt
    {
        [DataMember] public int rotation, zoom_percent, dpi_percent, width, height;
        [DataMember] public int[] highlight;
        [DataMember] public bool crop_to_source, green_outline;
    }

    private readonly Options options;
    private readonly ShellClient client;
    private readonly ActionButton[] tabs = new ActionButton[3];
    private readonly FrameworkElement[] pages = new FrameworkElement[4];
    private readonly TextBlock scope, projectSummary, documentSummary, status;
    private readonly Border statusBar;
    private readonly ActionButton selectA, selectB, importDocument, searchDocuments, runAnalysis, openSource;
    private readonly DocumentViewerPanel viewer;
    private readonly TextBox query, result;
    private readonly ListBox documents;
    private readonly ScrollViewer contentArea;
    private Page page;
    private string selectedVault, selectedName, workspaceId;
    private bool workspaceUsable;
    private bool busy, closing, probeStarted, statusIsError;
    private int scopeGeneration, viewerGeneration;
    private SourceScope analysisSource;
    private Task worker;
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
        openSource = Button("Открыть источник расчёта", "openAnalysisSource");
        openSource.Margin = new Thickness(0, 12, 8, 0);
        openSource.Click += OpenSource;
        analysis.Children.Add(openSource);
        pages[(int)Page.Analysis] = Card(analysis);
        viewer = new DocumentViewerPanel();
        viewer.BackRequested += () => ShowPage(Page.Analysis, moveFocus: true);
        viewer.ViewChanged += RefreshViewer;
        pages[(int)Page.Viewer] = viewer;
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
        if (page == Page.Viewer && destination != Page.Viewer)
        {
            viewerGeneration++;
            viewer.Reset(0);
            if (analysisSource != null) SetStatus("Расчёт завершён.");
        }
        page = destination;
        foreach (FrameworkElement panel in pages) panel.Visibility = Visibility.Collapsed;
        pages[(int)destination].Visibility = Visibility.Visible;
        for (int index = 0; index < tabs.Length; index++)
        {
            bool active = index == (int)(destination == Page.Viewer ? Page.Analysis : destination);
            MarkActive(tabs[index], active, "Открыто");
        }
        contentArea.ScrollToTop();
        if (moveFocus)
        {
            Control[] firstActions = {selectA, importDocument, openSource.IsEnabled ? openSource : runAnalysis, viewer.BackButton};
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
        openSource.IsEnabled = scoped && analysisSource != null;
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
        ClearAnalysis();
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
        ClearAnalysis();
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
        ClearAnalysis();
        Start("Проверяем источник и рассчитываем маржу…", () => client.Analyze(root, run), reply => {
            if (reply.Error != null)
            {
                string error = reply.Error == "source_missing" ? "Учебный документ не найден." : "Не удалось выполнить расчёт.";
                SetStatus(error, error: true);
                return;
            }
            ApplyWorkspaceId(reply);
            analysisSource = new SourceScope {Vault = root, WorkspaceId = reply.WorkspaceId, RunId = run,
                ResourceId = reply.SourceId, Sha256 = reply.SourceSha256, PageIndex = reply.SourcePage - 1,
                Generation = scopeGeneration};
            result.Text = "Операционная маржа: " + reply.Display + "%\nСобственный учебный PDF, страница "
                + reply.SourcePage.ToString(CultureInfo.InvariantCulture) + ".";
            SetStatus("Расчёт завершён.");
            if (page == Page.Analysis) FocusWhenReady(result);
        });
    }

    private void ClearAnalysis()
    {
        analysisSource = null;
        result.Clear();
        viewerGeneration++;
        viewer.Reset(0);
    }

    private void OpenSource(object sender, RoutedEventArgs args)
    {
        if (!openSource.IsEnabled || analysisSource == null) return;
        viewerGeneration++;
        viewer.Reset(analysisSource.PageIndex);
        ShowPage(Page.Viewer, moveFocus: true);
        RefreshViewer();
    }

    private double DpiScale()
    {
        var visual = PresentationSource.FromVisual(this);
        return visual == null || visual.CompositionTarget == null ? 1.0 : visual.CompositionTarget.TransformToDevice.M11;
    }

    private void RefreshViewer()
    {
        var source = analysisSource;
        if (closing || busy || page != Page.Viewer || source == null || source.Generation != scopeGeneration
            || source.WorkspaceId != workspaceId || source.Vault != selectedVault) return;
        busy = true;
        SetStatus("Открываем страницу PDF…");
        UpdateControls();
        viewer.SetBusy(true);
        viewer.Clear("Страница загружается…");
        int zoom = viewer.ZoomPercent, rotation = viewer.Rotation;
        int dpi = Math.Max(50, Math.Min(200, (int)Math.Round(DpiScale() * 100.0)));
        bool crop = viewer.CropToSource;
        Task<ViewerReply> activity = Task.Run(() => client.View(source.Vault, source.RunId, source.ResourceId,
            source.Sha256, source.PageIndex, zoom, rotation, dpi, crop));
        worker = activity;
        operation = FinishViewer(activity, source, viewerGeneration, zoom, rotation, dpi, crop);
    }

    private async Task FinishViewer(Task<ViewerReply> activity, SourceScope source, int generation,
                                    int zoom, int rotation, int dpi, bool crop)
    {
        ViewerReply reply;
        try { reply = await activity; }
        catch (Exception) { reply = null; }
        if (closing) return;
        busy = false;
        viewer.SetBusy(false);
        UpdateControls();
        if (page != Page.Viewer || generation != viewerGeneration || source != analysisSource
            || source.Generation != scopeGeneration || source.WorkspaceId != workspaceId) return;
        try
        {
            if (reply == null || reply.Error != null || reply.ResourceId != source.ResourceId
                || reply.SourceSha256 != source.Sha256 || reply.PageIndex != source.PageIndex
                || reply.ZoomPercent != zoom || reply.Rotation != rotation || reply.DpiPercent != dpi
                || reply.CropToSource != crop)
                throw new InvalidDataException("viewer_reply_invalid");
            viewer.Present(reply);
            SetStatus("Открыт источник расчёта.");
        }
        catch (Exception)
        {
            viewer.Clear("Страница недоступна.");
            SetStatus("Не удалось открыть источник расчёта.", error: true);
        }
    }

    private void Start(string waiting, Func<ShellReply> request, Action<ShellReply> present)
    {
        if (busy || closing) return;
        busy = true;
        lastReply = null;
        SetStatus(waiting);
        UpdateControls();
        Task<ShellReply> activity = Task.Run(request);
        worker = activity;
        operation = Finish(activity, scopeGeneration, present);
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
        var viewerReceipt = options.ProbeViewer ? new ViewerProbeReceipt {dpi_scale = DpiScale(),
            incomplete_step = "analysis_setup"} : null;
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
            if (viewerReceipt != null)
            {
                viewerReceipt.display = receipt.display;
                viewerReceipt.source_sha256 = receipt.source_sha256;
                await ProbeViewer(viewerReceipt);
                viewerReceipt.incomplete_step = "scope_change_and_new_calculation";
            }

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
            if (viewerReceipt != null)
            {
                Expect(!openSource.IsEnabled && analysisSource == null && viewer.Frame == null);
                viewerReceipt.scope_cleared = true;
                viewerReceipt.steps.Add("source_cleared_for_project_b");
            }

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
            if (viewerReceipt != null)
            {
                Expect(openSource.IsEnabled && viewer.Frame == null);
                viewerReceipt.steps.Add("fresh_analysis_source_available");
                viewerReceipt.incomplete_step = null;
                viewerReceipt.ok = true;
            }
        }
        catch (Exception)
        {
            if (viewerReceipt != null && receipt.incomplete_step != null && viewerReceipt.incomplete_step != null)
            {
                viewerReceipt.incomplete_step = receipt.incomplete_step;
                viewerReceipt.operation_error = lastReply == null ? null : lastReply.Error;
            }
            exit = 4;
        }
        if (closing) return;
        try
        {
            if (viewerReceipt != null) SaveProbe("win09-viewer-probe.json", viewerReceipt);
            else SaveProbe("win08-shell-probe.json", receipt);
        }
        catch (Exception) { exit = 5; }
        ScheduleShutdown(exit);
    }

    private ViewerReply RecordFrame(ViewerProbeReceipt receipt, int zoom, int rotation, bool crop)
    {
        var frame = viewer.Frame;
        Expect(page == Page.Viewer && frame != null && frame.PageIndex == 0 && frame.PageCount == 1
            && frame.SourceSha256 == receipt.source_sha256 && frame.ZoomPercent == zoom && frame.Rotation == rotation
            && frame.CropToSource == crop && viewer.GreenOutlineVisible());
        receipt.views.Add(new ViewerFrameReceipt {rotation = frame.Rotation, zoom_percent = frame.ZoomPercent,
            dpi_percent = frame.DpiPercent, width = frame.Width, height = frame.Height, highlight = frame.Highlight,
            crop_to_source = frame.CropToSource, green_outline = true});
        return frame;
    }

    private async Task ProbeViewer(ViewerProbeReceipt receipt)
    {
        receipt.incomplete_step = "open_exact_cited_page";
        openSource.ProbeClick();
        await operation;
        var initial = RecordFrame(receipt, 100, 0, false);
        Expect(viewer.AlternativesMatchFrame && initial.PrintedPage == "1" && String.IsNullOrEmpty(initial.PdfPageLabel));
        receipt.page_index = initial.PageIndex;
        receipt.page_count = initial.PageCount;
        receipt.printed_page = initial.PrintedPage;
        receipt.pdf_page_label = initial.PdfPageLabel;
        receipt.alternative_text_verified = true;
        receipt.steps.Add("open_exact_cited_page");

        receipt.incomplete_step = "zoom_and_rotate_page";
        viewer.ProbeZoom(150);
        await operation;
        var enlarged = RecordFrame(receipt, 150, 0, false);
        Expect(enlarged.Width > initial.Width && enlarged.Height > initial.Height);
        receipt.incomplete_step = "pan_without_rerender";
        await Dispatcher.InvokeAsync(new Action(() => { }), DispatcherPriority.ApplicationIdle);
        receipt.panning_offset_before = viewer.VerticalOffset;
        Task rendered = operation;
        viewer.ProbePanDown();
        await Dispatcher.InvokeAsync(new Action(() => { }), DispatcherPriority.ApplicationIdle);
        receipt.panning_offset_after = viewer.VerticalOffset;
        Expect(receipt.panning_offset_after > receipt.panning_offset_before
            && ReferenceEquals(enlarged, viewer.Frame) && ReferenceEquals(rendered, operation));
        receipt.panning_verified = true;
        receipt.steps.Add("pan_without_rerender");

        receipt.incomplete_step = "rotate_page";
        ViewerReply full = enlarged;
        foreach (int angle in new[] {90, 180, 270})
        {
            viewer.ProbeRotate();
            await operation;
            full = RecordFrame(receipt, 150, angle, false);
            Expect(full.Width == (angle == 180 ? enlarged.Width : enlarged.Height)
                && full.Height == (angle == 180 ? enlarged.Height : enlarged.Width));
        }
        receipt.steps.Add("zoom_and_rotate_page");

        receipt.incomplete_step = "crop_to_source_rectangle";
        viewer.ProbeCrop();
        await operation;
        var cropped = RecordFrame(receipt, 150, 270, true);
        Expect(cropped.Width < full.Width && cropped.Height < full.Height && viewer.AlternativesMatchFrame);
        receipt.steps.Add("crop_to_source_rectangle");

        receipt.incomplete_step = "return_to_analysis_and_reopen";
        viewer.ProbeBack();
        Expect(page == Page.Analysis && viewer.Frame == null && openSource.IsEnabled && result.Text.Contains("15.00%"));
        receipt.return_to_analysis = true;
        openSource.ProbeClick();
        await operation;
        RecordFrame(receipt, 100, 0, false);
        receipt.steps.Add("return_to_analysis_and_reopen");
    }

    private void SaveProbe(string filename, object receipt)
    {
        for (var folder = new DirectoryInfo(options.AppData); folder != null; folder = folder.Parent)
            if (!folder.Exists || (folder.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("probe_directory_unavailable");
        using (var stream = new FileStream(Path.Combine(options.AppData, filename),
                 FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            new DataContractJsonSerializer(receipt.GetType()).WriteObject(stream, receipt);
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
