using System;
using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;

internal sealed class DocumentViewerPanel : Border
{
    private sealed class ViewerButton : Button
    {
        internal void InvokeForProbe() { OnClick(); }
    }

    private static readonly int[] ZoomLevels = {50, 75, 100, 125, 150, 200};
    private readonly ViewerButton back, rotate;
    private readonly ComboBox zoom;
    private readonly CheckBox crop;
    private readonly TextBlock pageLabel;
    private readonly TextBox pageText, tableText;
    private readonly ScrollViewer viewport;
    private readonly Image image;
    private bool changing, busy;

    internal event Action ViewChanged;
    internal event Action BackRequested;
    internal int PageIndex { get; private set; }
    internal int ZoomPercent { get { return ZoomLevels[Math.Max(0, zoom.SelectedIndex)]; } }
    internal int Rotation { get; private set; }
    internal bool CropToSource { get { return crop.IsChecked == true; } }
    internal ViewerReply Frame { get; private set; }

    internal DocumentViewerPanel()
    {
        Padding = new Thickness(18);
        BorderThickness = new Thickness(1);
        CornerRadius = new CornerRadius(8);
        SetResourceReference(BackgroundProperty, "Surface");
        SetResourceReference(BorderBrushProperty, "Line");
        var panel = new StackPanel();
        Child = panel;

        back = Button("Назад к анализу", "backToAnalysis");
        back.Click += (sender, args) => { if (BackRequested != null) BackRequested(); };
        panel.Children.Add(back);
        panel.Children.Add(Label("Источник расчёта", 22));
        pageLabel = Label("Страница ещё не открыта.", 14);
        pageLabel.Margin = new Thickness(0, 4, 0, 10);
        Identify(pageLabel, "viewerPageLabel", pageLabel.Text);
        panel.Children.Add(pageLabel);

        var tools = new WrapPanel {Margin = new Thickness(0, 0, 0, 6)};
        zoom = new ComboBox {MinHeight = 42, MinWidth = 100, Margin = new Thickness(0, 0, 8, 8),
            VerticalContentAlignment = VerticalAlignment.Center};
        Identify(zoom, "viewerZoom", "Масштаб страницы PDF");
        foreach (int level in ZoomLevels) zoom.Items.Add(level.ToString(CultureInfo.InvariantCulture) + "%");
        zoom.SelectionChanged += (sender, args) => NotifyChanged();
        tools.Children.Add(zoom);
        rotate = Button("Повернуть на 90°", "viewerRotate");
        rotate.Click += (sender, args) => { Rotation = (Rotation + 90) % 360; NotifyChanged(); };
        tools.Children.Add(rotate);
        crop = new CheckBox {MinHeight = 42, MaxWidth = 245, VerticalContentAlignment = VerticalAlignment.Center,
            Content = Label("Только выделенная строка", 15)};
        Identify(crop, "viewerCrop", "Только выделенная строка");
        crop.Checked += (sender, args) => NotifyChanged();
        crop.Unchecked += (sender, args) => NotifyChanged();
        tools.Children.Add(crop);
        panel.Children.Add(tools);

        image = new Image {Stretch = Stretch.Fill, HorizontalAlignment = HorizontalAlignment.Left,
            VerticalAlignment = VerticalAlignment.Top, SnapsToDevicePixels = true};
        Identify(image, "viewerPageImage", "Страница учебного PDF");
        viewport = new ScrollViewer {Content = image, Height = 320, Focusable = true,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            Margin = new Thickness(0, 0, 0, 14)};
        Identify(viewport, "viewerViewport", "Прокрутка страницы PDF");
        AutomationProperties.SetHelpText(viewport, "Прокрутите страницу стрелками, клавишами Page Up и Page Down или полосами прокрутки.");
        viewport.PreviewKeyDown += Pan;
        panel.Children.Add(viewport);

        pageText = AddAlternative(panel, "Текст страницы", "viewerPageText");
        tableText = AddAlternative(panel, "Строки и значения", "viewerTableText");
        Reset(0);
    }

    private static void Identify(DependencyObject target, string id, string name)
    {
        AutomationProperties.SetAutomationId(target, id);
        AutomationProperties.SetName(target, name);
    }

    private static TextBlock Label(string text, double size)
    {
        var label = new TextBlock {Text = text, FontSize = size, TextWrapping = TextWrapping.Wrap};
        label.SetResourceReference(TextBlock.ForegroundProperty, "Ink");
        return label;
    }

    private static ViewerButton Button(string title, string id)
    {
        var caption = new TextBlock {Text = title, TextWrapping = TextWrapping.Wrap};
        var button = new ViewerButton {Content = caption, MinHeight = 42, MaxWidth = 245,
            HorizontalAlignment = HorizontalAlignment.Left, Padding = new Thickness(10, 6, 10, 6),
            Margin = new Thickness(0, 0, 8, 8)};
        Identify(button, id, title);
        button.SetResourceReference(Control.BackgroundProperty, "ActionSurface");
        button.SetResourceReference(Control.ForegroundProperty, "ActionInk");
        button.SetResourceReference(Control.BorderBrushProperty, "Line");
        return button;
    }

    private static TextBox AddAlternative(Panel panel, string label, string id)
    {
        panel.Children.Add(Label(label, 15));
        var entry = new TextBox {IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap,
            Padding = new Thickness(8), Margin = new Thickness(0, 5, 0, 12), MinHeight = 55, MaxHeight = 140,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto};
        entry.SetResourceReference(Control.ForegroundProperty, "Ink");
        entry.SetResourceReference(Control.BackgroundProperty, "ResultSurface");
        entry.SetResourceReference(Control.BorderBrushProperty, "Line");
        Identify(entry, id, label);
        panel.Children.Add(entry);
        return entry;
    }

    internal void Reset(int pageIndex)
    {
        changing = true;
        PageIndex = pageIndex;
        Rotation = 0;
        zoom.SelectedIndex = Array.IndexOf(ZoomLevels, 100);
        crop.IsChecked = false;
        changing = false;
        Clear("Страница ещё не открыта.");
        SetBusy(false);
    }

    internal void Clear(string message)
    {
        Frame = null;
        image.Source = null;
        image.ClearValue(WidthProperty);
        image.ClearValue(HeightProperty);
        pageText.Clear();
        tableText.Clear();
        ShowPageLabel(message);
    }

    internal void SetBusy(bool value)
    {
        busy = value;
        zoom.IsEnabled = rotate.IsEnabled = crop.IsEnabled = !busy;
    }

    private void NotifyChanged()
    {
        if (!changing && !busy && ViewChanged != null) ViewChanged();
    }

    private void ShowPageLabel(string label)
    {
        pageLabel.Text = label;
        AutomationProperties.SetName(pageLabel, label);
    }

    private static string LabelValue(string label)
    {
        return String.IsNullOrWhiteSpace(label) ? "не указан" : "«" + label + "»";
    }

    internal void Present(ViewerReply reply)
    {
        byte[] bytes = reply.Png;
        if (bytes == null || bytes.Length < 24 || reply.Width < 1 || reply.Height < 1
            || (long)reply.Width * reply.Height > 8000000 || PngInteger(bytes, 16) != reply.Width
            || PngInteger(bytes, 20) != reply.Height)
            throw new InvalidDataException("viewer_bitmap_shape");
        var bitmap = new BitmapImage();
        using (var input = new MemoryStream(bytes, writable: false))
        {
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.StreamSource = input;
            bitmap.EndInit();
        }
        if (bitmap.PixelWidth != reply.Width || bitmap.PixelHeight != reply.Height)
            throw new InvalidDataException("viewer_bitmap_shape");
        bitmap.Freeze();
        image.Source = bitmap;
        image.Width = reply.Width * 100.0 / reply.DpiPercent;
        image.Height = reply.Height * 100.0 / reply.DpiPercent;
        viewport.ScrollToHorizontalOffset(0);
        viewport.ScrollToVerticalOffset(0);
        pageText.Text = reply.PageText;
        tableText.Text = reply.TableText;
        ShowPageLabel(String.Format(CultureInfo.InvariantCulture,
            "Страница PDF: {0} из {1} (индекс {2}) · Метка PDF: {3} · Печатный номер: {4}",
            reply.PageIndex + 1, reply.PageCount, reply.PageIndex, LabelValue(reply.PdfPageLabel), LabelValue(reply.PrintedPage)));
        Frame = reply;
        SetBusy(false);
    }

    private static int PngInteger(byte[] bytes, int start)
    {
        return bytes[start] << 24 | bytes[start + 1] << 16 | bytes[start + 2] << 8 | bytes[start + 3];
    }

    private void Pan(object sender, KeyEventArgs args)
    {
        if (viewport.IsKeyboardFocused && PanByKey(args.Key)) args.Handled = true;
    }

    private bool PanByKey(Key key)
    {
        switch (key)
        {
            case Key.Up: viewport.LineUp(); break;
            case Key.Down: viewport.LineDown(); break;
            case Key.Left: viewport.LineLeft(); break;
            case Key.Right: viewport.LineRight(); break;
            case Key.PageUp: viewport.PageUp(); break;
            case Key.PageDown: viewport.PageDown(); break;
            case Key.Home: viewport.ScrollToTop(); break;
            case Key.End: viewport.ScrollToBottom(); break;
            default: return false;
        }
        return true;
    }

    internal Control BackButton { get { return back; } }
    internal bool AlternativesMatchFrame { get { return Frame != null && pageText.Text == Frame.PageText
        && tableText.Text == Frame.TableText && pageText.Text.Length > 0 && tableText.Text.Length > 0; } }
    internal bool GreenOutlineVisible()
    {
        if (Frame == null || Frame.Highlight == null || Frame.Highlight.Length != 4 || image.Source == null)
            return false;
        int x = Frame.Highlight[0], y = Frame.Highlight[1];
        var source = (BitmapSource)image.Source;
        if (x < 0 || y < 0 || x >= source.PixelWidth || y >= source.PixelHeight) return false;
        var rgb = new FormatConvertedBitmap(source, PixelFormats.Bgr32, null, 0);
        var pixel = new byte[4];
        rgb.CopyPixels(new Int32Rect(x, y, 1, 1), pixel, 4, 0);
        return pixel[0] == 65 && pixel[1] == 140 && pixel[2] == 0;
    }

    internal void ProbeZoom(int level) { zoom.SelectedIndex = Array.IndexOf(ZoomLevels, level); }
    internal double VerticalOffset { get { return viewport.VerticalOffset; } }
    internal void ProbePanDown() { PanByKey(Key.PageDown); }
    internal void ProbeRotate() { rotate.InvokeForProbe(); }
    internal void ProbeCrop() { crop.IsChecked = true; }
    internal void ProbeBack() { back.InvokeForProbe(); }
}
