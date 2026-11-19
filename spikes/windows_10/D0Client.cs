using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml.Linq;

internal sealed class D0Reply
{
    internal string Status, Operation, RunId, Display, Reason, SourceSha256;
    internal int? SourcePage;
    internal string[] Trace = new string[0];

    internal static D0Reply Failure(string operation, string run, string reason)
    {
        return new D0Reply {Status = "error", Operation = operation, RunId = run, Reason = reason};
    }
}

internal sealed partial class ShellClient
{
    private const string D0Entry = @"app\spikes\windows_10\d0_cli.py";
    internal const int D0QuestionLimit = 4000;
    private static readonly Encoding D0Utf8 = new UTF8Encoding(false, true);
    private static readonly HashSet<string> D0Operations = new HashSet<string>(StringComparer.Ordinal) {
        "direct", "delta", "relative", "scale", "margin"
    };
    private static readonly HashSet<string> D0Stages = new HashSet<string>(StringComparer.Ordinal) {
        "input", "catalog_filters", "search", "fact_resolution", "source_validation", "calculation", "result_validation", "answer"
    };

    internal D0Reply AnalyzeD0(string vault, string run, string operation, bool historical, string question)
    {
        if (!TypedHost.RunId(run) || !D0Operations.Contains(operation)
            || (question != null && (historical || !ValidD0Question(question))))
            return D0Reply.Failure(operation, run, "invalid_request");

        string arguments = "--run-id " + TypedHost.Quote(run) + " --operation " + operation;
        if (historical) arguments += " --historical";
        if (question != null) arguments += " " + QueryArgument("--question=" + question);
        var worker = Run(vault, D0Entry, arguments);
        if (worker.Error != null) return D0Reply.Failure(operation, run, worker.Error);
        if (worker.ExitCode != 0 && worker.ExitCode != 3) return D0Reply.Failure(operation, run, "worker_exit");
        try { return ReadD0Reply(worker.Frame, worker.ExitCode, run, operation); }
        catch (Exception) { return D0Reply.Failure(operation, run, "worker_protocol"); }
    }

    private static bool ValidD0Question(string question)
    {
        try { return ValidText(question, D0QuestionLimit) && D0Utf8.GetByteCount(question) <= 4096; }
        catch (EncoderFallbackException) { return false; }
    }

    private static D0Reply ReadD0Reply(byte[] bytes, int exitCode, string run, string operation)
    {
        var frame = TypedHost.ReadFrame(bytes, allowCrLf: false, maximumArrayLength: 16);
        TypedHost.Shape(frame, "object", "schema", "status", "operation", "run_id", "display", "reason", "trace",
                        "source_sha256", "source_page");
        var reply = new D0Reply {Status = Text(frame, "status"), Operation = Text(frame, "operation"),
            RunId = Text(frame, "run_id"), Reason = Text(frame, "reason"), Display = D0OptionalString(frame.Element("display")),
            SourceSha256 = D0OptionalString(frame.Element("source_sha256"))};
        var page = frame.Element("source_page");
        if ((string)page.Attribute("type") == "null") TypedHost.Scalar(page, "null");
        else reply.SourcePage = TypedHost.Integer(page);

        var trace = frame.Element("trace");
        var steps = trace.Elements().ToArray();
        TypedHost.Require((string)trace.Attribute("type") == "array" && trace.Attributes().Count() == 1
            && steps.Length <= 16 && steps.All(item => item.Name == "item"));
        reply.Trace = steps.Select(item => TypedHost.Scalar(item, "string")).ToArray();
        TypedHost.Require(reply.Trace.All(D0Stages.Contains)
            && Text(frame, "schema") == "win10-d0-1" && reply.Operation == operation && reply.RunId == run
            && Regex.IsMatch(reply.Reason, @"\A[a-z][a-z0-9_]{0,63}\z"));
        if (reply.Status == "answered")
        {
            TypedHost.Require(exitCode == 0 && reply.Reason == "ok" && reply.Trace.Length > 0
                && reply.Display != null && Regex.IsMatch(reply.Display, @"\A-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?\z")
                && reply.SourceSha256 == D0SourceSha && reply.SourcePage == 1);
        }
        else
        {
            bool domain = reply.Status == "clarify" || reply.Status == "blocked";
            TypedHost.Require((domain && exitCode == 0 || reply.Status == "error" && exitCode == 3)
                && reply.Reason != "ok" && reply.Display == null && reply.SourceSha256 == null && reply.SourcePage == null);
        }
        return reply;
    }

    private static string D0OptionalString(XElement node)
    {
        if ((string)node.Attribute("type") != "null") return TypedHost.Scalar(node, "string");
        TypedHost.Scalar(node, "null");
        return null;
    }
}
