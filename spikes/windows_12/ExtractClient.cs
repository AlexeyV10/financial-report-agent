using System;
using System.Linq;
using System.Text.RegularExpressions;
using System.Xml.Linq;

internal sealed class ExtractReply
{
    internal string Status, Error, ExtractionState, SemanticState;
    internal int TableCount, ParagraphCount;
    internal string[] Preview = new string[0];

    internal bool Completed { get { return Status == "extracted" || Status == "reused"; } }
    internal bool RequiresOcr { get { return Status == "unsupported" && Error == "pdf_ocr_pending"; } }

    internal static ExtractReply Failure(string error)
    {
        return new ExtractReply {Status = "error", Error = error, ExtractionState = "failed",
            SemanticState = "not_reviewed"};
    }
}

internal sealed partial class ShellClient
{
    private const string ExtractEntry = @"app\spikes\windows_12\extract_cli.py";
    private const int ExtractFrameLimit = 32768;
    private const int MaxPreviewRows = 16;
    private const int MaxPreviewChars = 256;
    private const int MaxExtractedItems = 3000;

    internal static bool CanExtractType(string type)
    {
        return type == "csv" || type == "xlsx" || type == "docx" || type == "txt" || type == "pdf";
    }

    internal ExtractReply ExtractAsset(string vault, ImportReply asset)
    {
        if (asset == null || !asset.Accepted || !CanExtractType(asset.FileType) || asset.WorkspaceId == null
            || asset.AssetSha256 == null || !Regex.IsMatch(asset.AssetSha256, @"\A[a-f0-9]{64}\z"))
            return ExtractReply.Failure("invalid_asset_selection");
        var outcome = Run(vault, ExtractEntry, "--asset-sha " + TypedHost.Quote(asset.AssetSha256), ExtractFrameLimit);
        if (outcome.Error != null) return ExtractReply.Failure(outcome.Error);
        try { return ReadExtractReply(outcome.Frame, outcome.ExitCode, asset); }
        catch (Exception) { return ExtractReply.Failure("worker_protocol_error"); }
    }

    private static ExtractReply ReadExtractReply(byte[] bytes, int exitCode, ImportReply asset)
    {
        TypedHost.Require(bytes != null && bytes.Length <= ExtractFrameLimit);
        var frame = TypedHost.ReadFrame(bytes, true, MaxPreviewRows, MaxPreviewChars);
        TypedHost.Shape(frame, "object", "schema", "status", "error", "workspace_id", "asset_sha256", "file_type",
            "extraction_state", "semantic_state", "table_count", "paragraph_count", "preview");
        TypedHost.Require(Text(frame, "schema") == "win12-extraction-1");

        string workspace = ImportOptionalString(frame.Element("workspace_id"));
        string sha = ImportOptionalString(frame.Element("asset_sha256"));
        string fileType = ImportOptionalString(frame.Element("file_type"));
        var preview = frame.Element("preview");
        XElement[] rows = preview.Elements().ToArray();
        TypedHost.Require((string)preview.Attribute("type") == "array" && preview.Attributes().Count() == 1
            && rows.Length <= MaxPreviewRows && rows.All(row => row.Name == "item"));
        var reply = new ExtractReply {
            Status = Text(frame, "status"), Error = ImportOptionalString(frame.Element("error")),
            ExtractionState = Text(frame, "extraction_state"), SemanticState = Text(frame, "semantic_state"),
            TableCount = Number(frame, "table_count"), ParagraphCount = Number(frame, "paragraph_count"),
            Preview = rows.Select(row => TypedHost.Scalar(row, "string")).ToArray()
        };
        TypedHost.Require(reply.SemanticState == "not_reviewed"
            && reply.TableCount <= MaxExtractedItems && reply.ParagraphCount <= MaxExtractedItems
            && (workspace == null || workspace == asset.WorkspaceId)
            && (sha == null || sha == asset.AssetSha256) && (fileType == null || fileType == asset.FileType));
        if (reply.Completed)
        {
            TypedHost.Require(exitCode == 0 && reply.Error == null && reply.ExtractionState == "extracted"
                && workspace != null && sha != null && fileType != null
                && reply.Preview.All(row => row.Length > 0 && row.Length <= MaxPreviewChars && !row.Any(char.IsControl)));
        }
        else
        {
            TypedHost.Require(((reply.Status == "unsupported" && exitCode == 0 && reply.ExtractionState == "pending")
                || (reply.Status == "error" && exitCode == 3 && reply.ExtractionState == "failed"))
                && reply.Error != null && Regex.IsMatch(reply.Error, @"\A[a-z][a-z0-9_]{0,63}\z")
                && reply.TableCount == 0 && reply.ParagraphCount == 0 && reply.Preview.Length == 0);
            if (reply.Error == "pdf_ocr_pending")
                TypedHost.Require(reply.RequiresOcr && fileType == "pdf" && workspace != null && sha != null);
        }
        return reply;
    }
}
