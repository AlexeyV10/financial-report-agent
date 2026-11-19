using System;
using System.Text.RegularExpressions;
using System.Xml.Linq;

internal sealed class ImportReply
{
    internal string Status, Error, WorkspaceId, AssetSha256, FileType;
    internal string FileState, ExtractionState, SemanticState;
    internal int? ByteCount;

    internal bool Accepted { get { return Status == "captured" || Status == "duplicate"; } }

    internal static ImportReply Failure(string error)
    {
        return new ImportReply {Status = "error", Error = error, FileState = "unavailable",
            ExtractionState = "not_started", SemanticState = "not_started"};
    }
}

internal sealed partial class ShellClient
{
    private const string ImportEntry = @"app\spikes\windows_11\import_cli.py";
    private const int ImportFrameLimit = 4096;
    private const int MaxImportBytes = 16 * 1024 * 1024;
    private static readonly string[] ImportTypes = {"pdf", "xlsx", "docx", "png", "jpeg", "tiff", "csv", "txt"};

    internal ImportReply CaptureFile(string vault, string selectedPath)
    {
        string candidate;
        try
        {
            TypedHost.LocalPath(selectedPath);
            // Preserve the exact selection for the worker's path checks.
            candidate = TypedHost.Quote(selectedPath);
        }
        catch (Exception) { return ImportReply.Failure("invalid_candidate_path"); }

        var outcome = Run(vault, ImportEntry, "--path " + candidate, ImportFrameLimit);
        if (outcome.Error != null) return ImportReply.Failure(outcome.Error);
        try { return ReadImportReply(outcome.Frame, outcome.ExitCode); }
        catch (Exception) { return ImportReply.Failure("worker_protocol_error"); }
    }

    private static ImportReply ReadImportReply(byte[] bytes, int exitCode)
    {
        TypedHost.Require(bytes != null && bytes.Length <= ImportFrameLimit);
        var frame = TypedHost.ReadFrame(bytes, true, 16, 128);
        TypedHost.Shape(frame, "object", "schema", "status", "error", "workspace_id",
            "asset_sha256", "file_type", "byte_count", "file_state", "extraction_state", "semantic_state");
        TypedHost.Require(Text(frame, "schema") == "win11-import-1");

        var reply = new ImportReply {
            Status = Text(frame, "status"), Error = ImportOptionalString(frame.Element("error")),
            WorkspaceId = ImportNull(frame.Element("workspace_id")) ? null : Id(frame, "workspace_id"),
            AssetSha256 = ImportOptionalString(frame.Element("asset_sha256")),
            FileType = ImportOptionalString(frame.Element("file_type")),
            ByteCount = ImportNull(frame.Element("byte_count")) ? (int?)null : Number(frame, "byte_count"),
            FileState = Text(frame, "file_state"), ExtractionState = Text(frame, "extraction_state"),
            SemanticState = Text(frame, "semantic_state")
        };
        if (reply.Accepted)
        {
            TypedHost.Require(exitCode == 0 && reply.Error == null && reply.WorkspaceId != null
                && reply.AssetSha256 != null && Regex.IsMatch(reply.AssetSha256, @"\A[a-f0-9]{64}\z")
                && Array.IndexOf(ImportTypes, reply.FileType) >= 0 && reply.ByteCount.HasValue
                && reply.ByteCount.Value > 0 && reply.ByteCount.Value <= MaxImportBytes && reply.FileState == "accepted"
                && reply.ExtractionState == "pending" && reply.SemanticState == "not_reviewed");
        }
        else
        {
            TypedHost.Require(((reply.Status == "rejected" && exitCode == 0 && reply.FileState == "rejected")
                || (reply.Status == "error" && exitCode == 3 && reply.FileState == "unavailable"))
                && reply.Error != null && Regex.IsMatch(reply.Error, @"\A[a-z][a-z0-9_]{0,63}\z")
                && reply.AssetSha256 == null && reply.FileType == null && reply.ByteCount == null
                && reply.ExtractionState == "not_started" && reply.SemanticState == "not_started");
        }
        return reply;
    }

    private static bool ImportNull(XElement node)
    {
        if ((string)node.Attribute("type") != "null") return false;
        TypedHost.Require(TypedHost.Scalar(node, "null").Length == 0);
        return true;
    }

    private static string ImportOptionalString(XElement node)
    {
        return ImportNull(node) ? null : TypedHost.Scalar(node, "string");
    }
}
