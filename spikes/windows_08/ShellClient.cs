using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Xml.Linq;

internal sealed class ShellReply
{
    internal string Error, WorkspaceId, Display, SourceId, SourceSha256;
    internal int DocumentCount, RevisionCount, MatchCount, SourcePage;
    internal readonly string[] Documents;

    internal ShellReply(string[] documents = null) { Documents = documents ?? new string[0]; }

    internal static ShellReply Failure(string code) { return new ShellReply {Error = code}; }
}

// The window supplies the selected vault and the search text, never an executable,
// script, SQL fragment or operation name. Each invocation uses the installed entry point.
internal sealed partial class ShellClient : IDisposable
{
    private const string VaultEntry = @"app\spikes\windows_07\vault_cli.py";
    private const string ServiceEntry = @"app\spikes\windows_05\service_cli.py";
    private readonly string install, appData;
    private readonly CancellationTokenSource lifetime = new CancellationTokenSource();
    private readonly CancellationToken token;
    private int disposed;

    internal ShellClient(string installRoot, string appData)
    {
        install = TypedHost.LocalPath(installRoot);
        this.appData = TypedHost.LocalPath(appData);
        TypedHost.CheckDisjoint(install, this.appData);
        token = lifetime.Token;
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref disposed, 1) == 0)
        {
            lifetime.Cancel();
            lifetime.Dispose();
        }
    }

    internal ShellReply Inspect(string vault) { return CallVault(vault, "inspect", Inspection); }

    internal ShellReply Import(string vault) { return CallVault(vault, "import-own", Imported); }

    internal ShellReply Search(string vault, string query)
    {
        if (!ValidText(query, 4096)) return ShellReply.Failure("invalid_query");
        return CallVault(vault, "search " + QueryArgument("--query=" + query), Matches);
    }

    internal ShellReply Analyze(string vault, string runId)
    {
        if (!TypedHost.RunId(runId)) return ShellReply.Failure("invalid_run_id");
        var worker = Run(vault, ServiceEntry, "--run-id " + TypedHost.Quote(runId) + " --supervised");
        if (worker.Error != null) return ShellReply.Failure(worker.Error);
        try
        {
            var result = TypedHost.Interpret(worker.Frame, runId, worker.ExitCode, false);
            if (result.ExitCode != 0) return ShellReply.Failure(result.error);
            return new ShellReply {WorkspaceId = result.WorkspaceId, Display = result.display,
                SourcePage = result.source_page.Value, SourceId = result.SourceId, SourceSha256 = result.SourceSha256};
        }
        catch (Exception) { return ShellReply.Failure("worker_protocol"); }
    }

    private ShellReply CallVault(string vault, string command, Func<XElement, ShellReply> read)
    {
        var worker = Run(vault, VaultEntry, command);
        if (worker.Error != null) return ShellReply.Failure(worker.Error);
        if (worker.ExitCode != 0 && worker.ExitCode != 3) return ShellReply.Failure("worker_exit");
        try
        {
            var frame = TypedHost.ReadFrame(worker.Frame, false, 32);
            if (worker.ExitCode == 0) return read(frame);
            TypedHost.Shape(frame, "object", "error");
            string code = Text(frame, "error");
            TypedHost.Require(Regex.IsMatch(code, @"\A[a-z][a-z0-9_]{0,63}\z"));
            return ShellReply.Failure(code);
        }
        catch (Exception) { return ShellReply.Failure("worker_protocol"); }
    }

    private TypedHost.WorkerOutcome Run(string vault, string entry, string command, int maxOutput = 65536)
    {
        if (token.IsCancellationRequested) return new TypedHost.WorkerOutcome {Error = "worker_cancelled"};
        string selected;
        try
        {
            selected = TypedHost.LocalPath(vault);
            TypedHost.CheckDisjoint(install, selected);
            TypedHost.CheckDisjoint(appData, selected);
        }
        catch (Exception) { return new TypedHost.WorkerOutcome {Error = "invalid_vault_path"}; }

        string python = Path.Combine(install, @"runtime\python.exe");
        string script = Path.Combine(install, entry);
        try
        {
            if (!PlainFile(python) || !PlainFile(script)) return new TypedHost.WorkerOutcome {Error = "worker_missing"};
        }
        catch (Exception) { return new TypedHost.WorkerOutcome {Error = "worker_missing"}; }
        string args = "-I -B -X utf8 " + TypedHost.Quote(script)
            + " --install-root " + TypedHost.Quote(install) + " --app-data " + TypedHost.Quote(appData)
            + " --vault " + TypedHost.Quote(selected) + " " + command;
        return TypedHost.InvokeFixed(python, args, install, token, maxOutput);
    }

    private static bool PlainFile(string path)
    {
        if (!File.Exists(path) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) return false;
        for (var directory = new DirectoryInfo(Path.GetDirectoryName(path)); directory != null; directory = directory.Parent)
            if (!directory.Exists || (directory.Attributes & FileAttributes.ReparsePoint) != 0) return false;
        return true;
    }

    // Windows argv quoting, only for one bounded literal query argument. Supplying
    // --query= as part of the same argument also prevents an option-looking value.
    private static string QueryArgument(string value)
    {
        var quoted = new StringBuilder("\"");
        int slashes = 0;
        foreach (char ch in value)
        {
            if (ch == '\\') { slashes++; continue; }
            if (ch == '"') quoted.Append('\\', slashes * 2 + 1);
            else quoted.Append('\\', slashes);
            quoted.Append(ch);
            slashes = 0;
        }
        return quoted.Append('\\', slashes * 2).Append('"').ToString();
    }

    private static bool ValidText(string value, int limit)
    {
        if (String.IsNullOrWhiteSpace(value) || value.Length > limit || value.IndexOf('\0') >= 0) return false;
        try { return TypedHost.Utf8.GetByteCount(value) <= limit; }
        catch (EncoderFallbackException) { return false; }
    }

    private static string Text(XElement parent, string name)
    {
        return TypedHost.Scalar(parent.Element(name), "string");
    }

    private static string Id(XElement parent, string name)
    {
        string value = Text(parent, name);
        TypedHost.Require(Regex.IsMatch(value, @"\A[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\z"));
        return value;
    }

    private static int Number(XElement parent, string name) { return TypedHost.Integer(parent.Element(name)); }

    private static ShellReply Inspection(XElement frame)
    {
        TypedHost.Shape(frame, "object", "workspace_id", "counts");
        var counts = frame.Element("counts");
        TypedHost.Shape(counts, "object", "documents", "originals", "versions", "revisions", "fts_rows");
        int docs = Number(counts, "documents"), originals = Number(counts, "originals");
        int versions = Number(counts, "versions"), revisions = Number(counts, "revisions");
        TypedHost.Require(docs <= versions && originals <= versions && versions <= revisions
                           && Number(counts, "fts_rows") == revisions);
        return new ShellReply {WorkspaceId = Id(frame, "workspace_id"), DocumentCount = docs, RevisionCount = revisions};
    }

    private static string RevisionLabel(string id, int version, int revision)
    {
        TypedHost.Require(version > 0 && revision > 0);
        return id + " · версия " + version.ToString(CultureInfo.InvariantCulture)
            + " · ревизия " + revision.ToString(CultureInfo.InvariantCulture);
    }

    private static ShellReply Imported(XElement frame)
    {
        TypedHost.Shape(frame, "object", "workspace_id", "stored", "display", "source_page", "source_sha256",
                        "source_highlight", "model_calls");
        var stored = frame.Element("stored");
        TypedHost.Shape(stored, "object", "document_id", "version", "revision", "sha256", "duplicate");
        string id = Id(stored, "document_id"), digest = Text(stored, "sha256");
        string display = Text(frame, "display"), duplicate = TypedHost.Scalar(stored.Element("duplicate"), "boolean");
        int page = Number(frame, "source_page");
        TypedHost.Require(id == TypedHost.SourceId && digest == TypedHost.SourceSha && Text(frame, "source_sha256") == digest
            && display == "15.00" && page == 1 && Number(frame, "model_calls") == 0
            && (duplicate == "true" || duplicate == "false"));
        TypedHost.RequireHighlight(frame.Element("source_highlight"));
        string label = RevisionLabel(id, Number(stored, "version"), Number(stored, "revision"));
        return new ShellReply(new[] {label}) {WorkspaceId = Id(frame, "workspace_id"), Display = display,
            SourcePage = page, SourceId = id, SourceSha256 = digest};
    }

    private static ShellReply Matches(XElement frame)
    {
        TypedHost.Shape(frame, "object", "workspace_id", "matches");
        var matches = frame.Element("matches");
        var items = matches.Elements().ToArray();
        TypedHost.Require((string)matches.Attribute("type") == "array" && matches.Attributes().Count() == 1
                           && items.Length <= 20 && items.All(item => item.Name == "item"));
        string[] labels = items.Select(item => {
            TypedHost.Shape(item, "object", "document_id", "version", "revision", "sha256", "extractor");
            TypedHost.Require(Regex.IsMatch(Text(item, "sha256"), @"\A[0-9a-f]{64}\z")
                && ValidText(Text(item, "extractor"), 256));
            return RevisionLabel(Id(item, "document_id"), Number(item, "version"), Number(item, "revision"));
        }).ToArray();
        return new ShellReply(labels) {WorkspaceId = Id(frame, "workspace_id"), MatchCount = labels.Length};
    }
}
