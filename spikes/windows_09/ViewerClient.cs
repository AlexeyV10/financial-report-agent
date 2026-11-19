using System;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;
using System.Xml.Linq;

internal sealed class ViewerReply
{
    internal string Error, ResourceId, SourceSha256, PrintedPage, PdfPageLabel, PageText, TableText;
    internal int PageIndex, PageCount, ZoomPercent, Rotation, DpiPercent, Width, Height;
    internal bool CropToSource;
    internal int[] Highlight;
    internal byte[] Png;

    internal static ViewerReply Failure(string code) { return new ViewerReply {Error = code}; }
}

internal sealed partial class ShellClient
{
    private const string ViewerEntry = @"app\spikes\windows_09\viewer_cli.py";
    private const int ViewerMaxOutput = 2 * 1024 * 1024;
    private const int ViewerMaxDimension = 4096;
    private const string ViewerSchema = "win09-viewer-1";

    internal ViewerReply View(string vault, string runId, string resourceId, string sha256, int pageIndex,
                              int zoomPercent, int rotation, int dpiPercent, bool cropToSource)
    {
        if (!TypedHost.RunId(runId) || resourceId != TypedHost.SourceId || sha256 != TypedHost.SourceSha)
            return ViewerReply.Failure("viewer_untrusted_source");
        if (pageIndex < 0 || pageIndex >= 100 || zoomPercent < 50 || zoomPercent > 200
            || dpiPercent < 50 || dpiPercent > 200 || rotation < 0 || rotation > 270 || rotation % 90 != 0)
            return ViewerReply.Failure("viewer_options");

        string arguments = String.Format(CultureInfo.InvariantCulture,
            "--run-id {0} --resource-id {1} --page-index {2} --zoom-percent {3} --rotation {4} --dpi-percent {5}{6}",
            TypedHost.Quote(runId), TypedHost.Quote(resourceId), pageIndex, zoomPercent, rotation, dpiPercent,
            cropToSource ? " --crop-to-source" : "");
        var worker = Run(vault, ViewerEntry, arguments, ViewerMaxOutput);
        if (worker.Error != null) return ViewerReply.Failure(worker.Error);
        if (worker.ExitCode != 0 && worker.ExitCode != 3) return ViewerReply.Failure("worker_exit");
        try
        {
            var frame = TypedHost.ReadFrame(worker.Frame, false, 4, ViewerMaxOutput);
            if (worker.ExitCode == 3)
            {
                TypedHost.Shape(frame, "object", "schema", "status", "error");
                string code = Text(frame, "error");
                TypedHost.Require(Text(frame, "schema") == ViewerSchema && Text(frame, "status") == "error"
                                  && Regex.IsMatch(code, @"\A[a-z][a-z0-9_]{0,63}\z"));
                return ViewerReply.Failure(code);
            }

            var reply = ReadViewerPage(frame);
            TypedHost.Require(reply.ResourceId == resourceId && reply.SourceSha256 == sha256
                && reply.PageIndex == pageIndex && reply.ZoomPercent == zoomPercent && reply.Rotation == rotation
                && reply.DpiPercent == dpiPercent && reply.CropToSource == cropToSource);
            return reply;
        }
        catch (Exception) { return ViewerReply.Failure("viewer_protocol"); }
    }

    private static ViewerReply ReadViewerPage(XElement frame)
    {
        TypedHost.Shape(frame, "object", "schema", "status", "resource_id", "source_sha256", "page_index",
            "page_count", "printed_page", "pdf_page_label", "zoom_percent", "rotation", "dpi_percent",
            "crop_to_source", "width", "height", "highlight", "page_text", "table_text", "png");
        TypedHost.Require(Text(frame, "schema") == ViewerSchema && Text(frame, "status") == "ok");
        var reply = new ViewerReply {
            ResourceId = Text(frame, "resource_id"), SourceSha256 = Text(frame, "source_sha256"),
            PageIndex = Number(frame, "page_index"), PageCount = Number(frame, "page_count"),
            PrintedPage = OptionalText(frame.Element("printed_page"), 256),
            PdfPageLabel = OptionalText(frame.Element("pdf_page_label"), 256),
            ZoomPercent = Number(frame, "zoom_percent"), Rotation = Number(frame, "rotation"),
            DpiPercent = Number(frame, "dpi_percent"), Width = Number(frame, "width"), Height = Number(frame, "height"),
            PageText = ViewerText(frame.Element("page_text"), 32768), TableText = ViewerText(frame.Element("table_text"), 8192)
        };
        var crop = TypedHost.Scalar(frame.Element("crop_to_source"), "boolean");
        TypedHost.Require((crop == "true" || crop == "false")
            && reply.PageIndex < reply.PageCount && reply.PageCount <= 100
            && reply.Width > 0 && reply.Width <= ViewerMaxDimension && reply.Height > 0
            && reply.Height <= ViewerMaxDimension && reply.Width * reply.Height <= 8000000);
        reply.CropToSource = crop == "true";
        reply.Highlight = ReadViewerHighlight(frame.Element("highlight"), reply.Width, reply.Height);
        string encoded = Text(frame, "png");
        reply.Png = Convert.FromBase64String(encoded);
        TypedHost.Require(Convert.ToBase64String(reply.Png) == encoded
            && ValidPngHeader(reply.Png, reply.Width, reply.Height));
        return reply;
    }

    private static string OptionalText(XElement element, int limit)
    {
        if ((string)element.Attribute("type") != "null") return ViewerText(element, limit);
        TypedHost.Require(TypedHost.Scalar(element, "null").Length == 0);
        return null;
    }

    private static string ViewerText(XElement element, int limit)
    {
        string value = TypedHost.Scalar(element, "string");
        TypedHost.Require(value.Length <= limit
            && !value.Any(ch => char.IsControl(ch) && ch != '\r' && ch != '\n' && ch != '\t'));
        return value;
    }

    private static int[] ReadViewerHighlight(XElement element, int width, int height)
    {
        if ((string)element.Attribute("type") == "null")
        {
            TypedHost.Require(TypedHost.Scalar(element, "null").Length == 0);
            return null;
        }
        var items = element.Elements().ToArray();
        TypedHost.Require((string)element.Attribute("type") == "array" && element.Attributes().Count() == 1
            && items.Length == 4 && items.All(item => item.Name == "item"));
        var rect = items.Select(TypedHost.Integer).ToArray();
        TypedHost.Require(rect[0] < rect[2] && rect[1] < rect[3] && rect[2] <= width && rect[3] <= height);
        return rect;
    }

    private static bool ValidPngHeader(byte[] bytes, int width, int height)
    {
        byte[] prefix = {137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82};
        return bytes.Length >= 33 && bytes.Take(prefix.Length).SequenceEqual(prefix)
            && BigEndian(bytes, 16) == width && BigEndian(bytes, 20) == height;
    }

    private static int BigEndian(byte[] bytes, int offset)
    {
        return (bytes[offset] << 24) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3];
    }
}
