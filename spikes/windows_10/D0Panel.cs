using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;

internal sealed class D0Request
{
    internal readonly string Operation, Question;
    internal readonly bool Historical;

    internal D0Request(string operation, bool historical, string question)
    {
        Operation = operation;
        Historical = historical;
        Question = question;
    }
}

internal sealed class D0Panel : Border
{
    private sealed class RunButton : Button
    {
        internal void ProbeClick()
        {
            if (!IsVisible || !IsEnabled) throw new InvalidOperationException("d0_action_unavailable");
            OnClick();
        }
    }

    private static readonly string[] Operations = {"direct", "delta", "relative", "scale", "margin"};
    private static readonly string[] Labels = {"Факт: выручка за 2025 год", "Абсолютное изменение выручки",
        "Относительное изменение выручки", "Масштаб: выручка в млрд руб.", "Операционная маржа"};
    private static readonly string[] Units = {" млн руб.", " млн руб.", "%", " млрд руб.", "%"};
    private static readonly Dictionary<string, string> StageLabels = new Dictionary<string, string>(StringComparer.Ordinal) {
        {"input", "Разбор запроса"}, {"catalog_filters", "Проверка каталога и версии"},
        {"search", "Поиск подтверждённых данных"}, {"fact_resolution", "Выбор исходных показателей"},
        {"source_validation", "Сверка источника"}, {"calculation", "Расчёт"},
        {"result_validation", "Проверка результата"}, {"answer", "Ответ"}
    };

    private readonly ComboBox preset;
    private readonly CheckBox historical;
    private readonly TextBox question, result, citation, trace;
    private readonly TextBlock outcome;
    private readonly RunButton run, openSource;
    private bool enabled, sourceAvailable;

    internal event Action<D0Request> CalculationRequested;
    internal event Action SourceRequested;
    internal event Action OutputInvalidated;
    internal Control FirstControl { get { return preset; } }
    internal Control ResultControl { get { return result; } }
    internal Control SourceControl { get { return openSource; } }
    internal string FinancialText { get { return result.Text; } }
    internal string CitationText { get { return citation.Text; } }
    internal bool OutputsEmpty { get { return result.Text.Length == 0 && citation.Text.Length == 0 && trace.Text.Length == 0; } }

    internal D0Panel()
    {
        Padding = new Thickness(18);
        BorderThickness = new Thickness(1);
        CornerRadius = new CornerRadius(8);
        SetResourceReference(BackgroundProperty, "Surface");
        SetResourceReference(BorderBrushProperty, "Line");
        var stack = new StackPanel();
        Child = stack;
        stack.Children.Add(Label("Анализ", 22));
        stack.Children.Add(Label("Выберите операцию для собственного учебного отчёта.", 15));

        preset = new ComboBox {MinHeight = 42, Margin = new Thickness(0, 8, 0, 8),
            VerticalContentAlignment = VerticalAlignment.Center};
        Identify(preset, "d0Operation", "Операция расчёта");
        foreach (string title in Labels)
            preset.Items.Add(Label(title, 15));
        preset.SelectedIndex = 0;
        stack.Children.Add(preset);

        historical = new CheckBox {MinHeight = 42, VerticalContentAlignment = VerticalAlignment.Center,
            Content = Label("Исторический режим · учебная дата", 15)};
        Identify(historical, "d0Historical", "Исторический режим, учебная дата");
        stack.Children.Add(historical);
        stack.Children.Add(Label("Вопрос для текущих данных (необязательно)", 15));
        question = Box("Вопрос для текущих данных", "d0Question", readOnly: false, height: 48);
        question.MaxLength = ShellClient.D0QuestionLimit;
        stack.Children.Add(question);

        var caption = new TextBlock {Text = "Проверить и рассчитать", TextWrapping = TextWrapping.Wrap};
        run = new RunButton {Content = caption, MinHeight = 42, Margin = new Thickness(0, 2, 0, 12),
            Padding = new Thickness(12, 7, 12, 7), HorizontalAlignment = HorizontalAlignment.Left};
        run.SetResourceReference(Control.BackgroundProperty, "ActionSurface");
        run.SetResourceReference(Control.ForegroundProperty, "ActionInk");
        run.SetResourceReference(Control.BorderBrushProperty, "Line");
        Identify(run, "d0Calculate", "Проверить и рассчитать");
        run.Click += (sender, args) => Dispatch();
        stack.Children.Add(run);

        outcome = Label("", 15);
        Identify(outcome, "d0Outcome", "Состояние расчёта");
        stack.Children.Add(outcome);
        stack.Children.Add(Label("Результат", 16));
        result = Box("Результат расчёта", "d0Result", readOnly: true, height: 48);
        stack.Children.Add(result);
        stack.Children.Add(Label("Источник", 16));
        citation = Box("Ссылка на источник", "d0Citation", readOnly: true, height: 62);
        stack.Children.Add(citation);
        openSource = new RunButton {Content = "Открыть источник расчёта", MinHeight = 42,
            Padding = new Thickness(12, 7, 12, 7), HorizontalAlignment = HorizontalAlignment.Left,
            Margin = new Thickness(0, 0, 0, 12)};
        openSource.SetResourceReference(Control.BackgroundProperty, "ActionSurface");
        openSource.SetResourceReference(Control.ForegroundProperty, "ActionInk");
        openSource.SetResourceReference(Control.BorderBrushProperty, "Line");
        Identify(openSource, "d0OpenSource", "Открыть источник расчёта");
        openSource.Click += (sender, args) => { if (SourceRequested != null) SourceRequested(); };
        stack.Children.Add(openSource);
        stack.Children.Add(Label("Что проверено", 16));
        trace = Box("Этапы проверки", "d0Trace", readOnly: true, height: 75);
        stack.Children.Add(trace);

        preset.SelectionChanged += (sender, args) => ClearOutput();
        historical.Checked += (sender, args) => ModeChanged();
        historical.Unchecked += (sender, args) => ModeChanged();
        question.TextChanged += (sender, args) => ClearOutput();
        ClearOutput();
        SetEnabled(false);
    }

    private static void Identify(DependencyObject element, string id, string name)
    {
        AutomationProperties.SetAutomationId(element, id);
        AutomationProperties.SetName(element, name);
    }

    private static TextBlock Label(string text, double size)
    {
        var label = new TextBlock {Text = text, FontSize = size, TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 2, 0, 4)};
        label.SetResourceReference(TextBlock.ForegroundProperty, "Ink");
        return label;
    }

    private static TextBox Box(string label, string id, bool readOnly, double height)
    {
        var box = new TextBox {IsReadOnly = readOnly, AcceptsReturn = readOnly, TextWrapping = TextWrapping.Wrap,
            Padding = new Thickness(8), MinHeight = height, MaxHeight = 150, Margin = new Thickness(0, 2, 0, 10),
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto};
        box.SetResourceReference(Control.ForegroundProperty, "Ink");
        box.SetResourceReference(Control.BackgroundProperty, readOnly ? "ResultSurface" : "Surface");
        box.SetResourceReference(Control.BorderBrushProperty, "Line");
        Identify(box, id, label);
        return box;
    }

    internal void SetEnabled(bool value)
    {
        enabled = value;
        preset.IsEnabled = historical.IsEnabled = run.IsEnabled = value;
        question.IsEnabled = value && historical.IsChecked != true;
        openSource.IsEnabled = value && sourceAvailable;
    }

    private void ModeChanged()
    {
        SetEnabled(enabled);
        ClearOutput();
    }

    internal void ResetScope()
    {
        historical.IsChecked = false;
        question.Clear();
        ClearOutput();
    }

    private void SetOutcome(string text)
    {
        outcome.Text = text;
        AutomationProperties.SetName(outcome, text);
    }

    internal void ClearOutput()
    {
        sourceAvailable = false;
        openSource.IsEnabled = false;
        result.Clear();
        citation.Clear();
        trace.Clear();
        SetOutcome("");
        if (OutputInvalidated != null) OutputInvalidated();
    }

    private void Dispatch()
    {
        if (!enabled || preset.SelectedIndex < 0 || CalculationRequested == null) return;
        bool useHistory = historical.IsChecked == true;
        string input = useHistory || String.IsNullOrWhiteSpace(question.Text) ? null : question.Text;
        CalculationRequested(new D0Request(Operations[preset.SelectedIndex], useHistory, input));
    }

    internal string Present(D0Request request, D0Reply reply)
    {
        ClearOutput();
        trace.Text = String.Join("\n", reply.Trace.Select(step => StageLabels[step]));
        string message;
        if (reply.Status == "answered")
        {
            int index = Array.IndexOf(Operations, reply.Operation);
            result.Text = reply.Display + (request.Question == null && index >= 0 ? Units[index] : "");
            citation.Text = "Собственный учебный отчёт · страница PDF "
                + reply.SourcePage.Value.ToString(CultureInfo.InvariantCulture) + "\nSHA-256 " + reply.SourceSha256;
            sourceAvailable = true;
            message = "Расчёт завершён.";
        }
        else if (reply.Status == "clarify" && reply.Reason == "missing_organization")
            message = "Уточните, о какой группе компаний идёт речь.";
        else if (reply.Status == "clarify")
            message = "Уточните вопрос или выберите соответствующую операцию.";
        else if (reply.Status == "blocked" && reply.Reason == "publication_unknown")
            message = "Дата публикации исходной версии не подтверждена. Исторический расчёт недоступен.";
        else if (reply.Status == "blocked")
            message = "Данных для подтверждённого ответа недостаточно.";
        else
            message = "Не удалось выполнить расчёт.";
        SetOutcome(message);
        SetEnabled(enabled);
        return message;
    }

    internal void ProbeConfigure(string operation, bool useHistory, string input = null)
    {
        preset.SelectedIndex = Array.IndexOf(Operations, operation);
        historical.IsChecked = useHistory;
        question.Text = input ?? "";
    }

    internal void ProbeCalculate() { run.ProbeClick(); }
    internal void ProbeOpenSource() { openSource.ProbeClick(); }
}
