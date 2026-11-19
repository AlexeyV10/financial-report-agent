using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Threading;
using System.Xml;
using System.Xml.Linq;

internal static class TypedHost
{
    private const string Command = "own_margin";
    internal const string SourceId = "own-demo-v1";
    internal const string SourceSha = "c749435d1d445664dd5b28f54e6fd19f5fbcdb91d505e6ac112d1ba7f4715451";
    private const int MaxPipeBytes = 65536;
    internal static readonly Encoding Utf8 = new UTF8Encoding(false, true);

    private sealed class Launch
    {
        internal string Install, AppData, Vault, Probe;

        internal static Launch Parse(string[] args)
        {
            if ((args.Length != 4 && args.Length != 6) || args[0] != "--app-data" || args[2] != "--vault"
                || (args.Length == 6 && (args[4] != "--probe" || !RunId(args[5]))))
                throw new ArgumentException("launch_arguments");
            var launch = new Launch {
                Install = LocalPath(AppDomain.CurrentDomain.BaseDirectory),
                AppData = LocalPath(args[1]), Vault = LocalPath(args[3]),
                Probe = args.Length == 6 ? args[5] : null
            };
            CheckDisjoint(launch.Install, launch.AppData);
            CheckDisjoint(launch.Install, launch.Vault);
            CheckDisjoint(launch.AppData, launch.Vault);
            return launch;
        }
    }

    internal static bool RunId(string value)
    {
        return value != null && Regex.IsMatch(value, @"\A[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\z");
    }

    internal static string LocalPath(string value)
    {
        if (!Regex.IsMatch(value, @"\A[a-zA-Z]:[\\/]") || value.IndexOf('"') >= 0
            || value.IndexOf(':', 2) >= 0 || value.Any(char.IsControl))
            throw new ArgumentException("launch_path");
        string full = Path.GetFullPath(value);
        return full.Length == 3 ? full : full.TrimEnd('\\');
    }

    internal static void CheckDisjoint(string first, string second)
    {
        string firstPrefix = first.TrimEnd('\\') + "\\";
        string secondPrefix = second.TrimEnd('\\') + "\\";
        if (firstPrefix.StartsWith(secondPrefix, StringComparison.OrdinalIgnoreCase)
            || secondPrefix.StartsWith(firstPrefix, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("launch_path_overlap");
    }

    internal static string Quote(string value)
    {
        if (value.IndexOf('"') >= 0 || value.Any(char.IsControl))
            throw new ArgumentException("launch_argument");
        int trailingSlashes = value.Length - value.TrimEnd('\\').Length;
        return "\"" + value + new string('\\', trailingSlashes) + "\"";
    }

    [DataContract]
    internal sealed class Receipt
    {
        [DataMember] public string schema = "win05-native-probe-1";
        [DataMember] public bool button_activated = true;
        [DataMember] public bool content_rendered = true;
        [DataMember] public string command = Command;
        [DataMember] public string run_id, context_id, status, display, error;
        [DataMember] public int? source_page;
        internal int ExitCode;
        internal string WorkspaceId, SourceId, SourceSha256;

        internal static Receipt Failure(string run, string context, string errorCode, int exitCode)
        {
            return new Receipt {run_id = run, context_id = context, status = "failed", error = errorCode, ExitCode = exitCode};
        }
    }

    internal static void Require(bool condition)
    {
        if (!condition) throw new InvalidDataException("worker_protocol");
    }

    // The .NET Framework JSON-to-XML reader accepts some non-JSON forms.
    // Check grammar and full-frame consumption before using its typed elements.
    private sealed class JsonGrammar
    {
        private static readonly Regex Tokens = new Regex(
            @"\G[\t ]*(""(?:[^""\\\x00-\x1f]|\\(?:[""\\/bfnrt]|u[0-9a-fA-F]{4}))*""|true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|[{}\[\],:])",
            RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(250));
        private readonly string text;
        private int offset;
        private string token;

        private JsonGrammar(string frame) { text = frame; Advance(); }

        private void Advance()
        {
            var match = Tokens.Match(text, offset);
            if (match.Success)
            {
                offset += match.Length;
                token = match.Groups[1].Value;
                return;
            }
            for (; offset < text.Length; offset++) Require(text[offset] == ' ' || text[offset] == '\t');
            token = null;
        }

        private bool Take(string expected)
        {
            if (token != expected) return false;
            Advance();
            return true;
        }

        private void ReadObject(int depth)
        {
            if (Take("}")) return;
            do
            {
                Require(token != null && token[0] == '"');
                Advance();
                Require(Take(":"));
                ReadValue(depth);
            } while (Take(","));
            Require(Take("}"));
        }

        private void ReadArray(int depth)
        {
            if (Take("]")) return;
            do { ReadValue(depth); } while (Take(","));
            Require(Take("]"));
        }

        private void ReadValue(int depth)
        {
            Require(depth < 8 && token != null);
            if (Take("{")) ReadObject(depth + 1);
            else if (Take("[")) ReadArray(depth + 1);
            else
            {
                Require(token != "}" && token != "]" && token != "," && token != ":");
                Advance();
            }
        }

        internal static void Validate(string frame)
        {
            var grammar = new JsonGrammar(frame);
            grammar.ReadValue(0);
            Require(grammar.token == null);
        }
    }

    internal static void Shape(XElement node, string kind, params string[] fields)
    {
        Require(node.Name.NamespaceName.Length == 0 && (string)node.Attribute("type") == kind
                && node.Attributes().Count() == 1);
        var children = node.Elements().ToArray();
        Require(children.Length == fields.Length
                && fields.All(field => children.Count(item => item.Name == field) == 1));
    }

    internal static string Scalar(XElement node, string kind)
    {
        Shape(node, kind);
        return node.Value;
    }

    internal static int Integer(XElement node)
    {
        int value;
        Require(int.TryParse(Scalar(node, "number"), NumberStyles.None, CultureInfo.InvariantCulture, out value));
        return value;
    }

    internal static XElement ReadFrame(byte[] bytes, bool allowCrLf, int maximumArrayLength)
    {
        Require(bytes.Length > 1 && bytes[bytes.Length - 1] == (byte)'\n');
        int frameLength = bytes.Length - 1;
        if (allowCrLf && bytes[frameLength - 1] == (byte)'\r') frameLength--;
        Require(frameLength > 0 && bytes[0] == (byte)'{'
                && Array.IndexOf(bytes, (byte)'\n', 0, frameLength) < 0
                && Array.IndexOf(bytes, (byte)'\r', 0, frameLength) < 0);
        JsonGrammar.Validate(Utf8.GetString(bytes, 0, frameLength));
        var quotas = new XmlDictionaryReaderQuotas {
            MaxDepth = 8, MaxArrayLength = maximumArrayLength, MaxBytesPerRead = 1024,
            MaxStringContentLength = 1024, MaxNameTableCharCount = 2048
        };
        using (var reader = JsonReaderWriterFactory.CreateJsonReader(bytes, 0, frameLength, quotas))
            return XDocument.Load(reader).Root;
    }

    internal static void RequireHighlight(XElement highlight)
    {
        var points = highlight.Elements().ToArray();
        Require((string)highlight.Attribute("type") == "array" && highlight.Attributes().Count() == 1
                && points.Length == 4 && points.All(point => point.Name == "item"));
        int[] rect = points.Select(Integer).ToArray();
        Require(rect[0] < rect[2] && rect[1] < rect[3] && rect[2] <= 420 && rect[3] <= 360);
    }

    internal static Receipt Interpret(byte[] bytes, string run, int exitCode, bool allowCrLf = true)
    {
        if (exitCode != 0 && exitCode != 3) return Receipt.Failure(run, null, "worker_exit", 4);
        var frame = ReadFrame(bytes, allowCrLf, 16);
        Shape(frame, "object", "schema", "run_id", "context_id", "command", "status", "result", "error");
        Require(Scalar(frame.Element("schema"), "string") == "win05-response-1"
                && Scalar(frame.Element("run_id"), "string") == run
                && Scalar(frame.Element("command"), "string") == Command);
        string context = Scalar(frame.Element("context_id"), "string");
        Require(Regex.IsMatch(context, @"\A[0-9a-f]{64}\z"));
        string status = Scalar(frame.Element("status"), "string");
        var result = frame.Element("result");
        if (exitCode == 3)
        {
            string error = Scalar(frame.Element("error"), "string");
            Require(status == "failed" && Scalar(result, "null").Length == 0
                    && Regex.IsMatch(error, @"\A[a-z][a-z0-9_]{0,63}\z"));
            return Receipt.Failure(run, context, error, 3);
        }

        Require(status == "completed" && Scalar(frame.Element("error"), "null").Length == 0);
        Shape(result, "object", "workspace_id", "source_id", "source_sha256", "source_page",
              "source_highlight", "operation", "display", "financial_status", "model_calls");
        int page = Integer(result.Element("source_page"));
        string display = Scalar(result.Element("display"), "string");
        string workspace = Scalar(result.Element("workspace_id"), "string");
        Require(Regex.IsMatch(workspace, @"\A[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\z")
                && Scalar(result.Element("source_id"), "string") == SourceId
                && Scalar(result.Element("source_sha256"), "string") == SourceSha
                && Scalar(result.Element("operation"), "string") == "operating_margin_v1"
                && Scalar(result.Element("financial_status"), "string") == "answered"
                && display == "15.00" && page == 1 && Integer(result.Element("model_calls")) == 0);
        RequireHighlight(result.Element("source_highlight"));
        return new Receipt {run_id = run, context_id = context, status = status, display = display, source_page = page,
            WorkspaceId = workspace, SourceId = SourceId, SourceSha256 = SourceSha};
    }

    private static byte[] ReadPipe(Stream stream)
    {
        using (var output = new MemoryStream())
        {
            byte[] buffer = new byte[4096];
            int bytes;
            while ((bytes = stream.Read(buffer, 0, buffer.Length)) > 0)
            {
                Require(output.Length + bytes <= MaxPipeBytes);
                output.Write(buffer, 0, bytes);
            }
            return output.ToArray();
        }
    }

    internal sealed class WorkerOutcome
    {
        internal byte[] Frame;
        internal string Error;
        internal int ExitCode;
    }

    internal static WorkerOutcome InvokeFixed(string python, string args, string directory, CancellationToken cancel)
    {
        var info = new ProcessStartInfo(python, args) {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
            RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = directory
        };
        using (var process = new Process {StartInfo = info})
        {
            bool started = false;
            Task<byte[]> stdout = null, stderr = null;
            try
            {
                cancel.ThrowIfCancellationRequested();
                var time = Stopwatch.StartNew();
                started = process.Start();
                if (!started) return new WorkerOutcome {Error = "worker_start"};
                process.StandardInput.Close();
                stdout = Task.Run(() => ReadPipe(process.StandardOutput.BaseStream));
                stderr = Task.Run(() => ReadPipe(process.StandardError.BaseStream));
                while (!process.HasExited || !stdout.IsCompleted || !stderr.IsCompleted)
                {
                    cancel.ThrowIfCancellationRequested();
                    if (time.ElapsedMilliseconds >= 15000) return new WorkerOutcome {Error = "worker_timeout"};
                    Require(!stdout.IsFaulted && !stderr.IsFaulted);
                    Thread.Sleep(20);
                }
                cancel.ThrowIfCancellationRequested();
                stderr.GetAwaiter().GetResult();
                return new WorkerOutcome {Frame = stdout.GetAwaiter().GetResult(), ExitCode = process.ExitCode};
            }
            catch (OperationCanceledException) { return new WorkerOutcome {Error = "worker_cancelled"}; }
            catch (Exception) { return new WorkerOutcome {Error = started ? "worker_protocol" : "worker_start"}; }
            finally
            {
                if (started)
                {
                    try { if (!process.HasExited) { process.Kill(); process.WaitForExit(1500); } }
                    catch (InvalidOperationException) { }
                    catch (System.ComponentModel.Win32Exception) { }
                }
                if (stdout != null && stdout.IsFaulted) GC.KeepAlive(stdout.Exception);
                if (stderr != null && stderr.IsFaulted) GC.KeepAlive(stderr.Exception);
            }
        }
    }

    private static Receipt InvokeService(Launch launch, string run, CancellationToken cancel)
    {
        string python = Path.Combine(launch.Install, @"runtime\python.exe");
        string entry = Path.Combine(launch.Install, @"app\spikes\windows_05\service_cli.py");
        if (!File.Exists(python) || !File.Exists(entry)) return Receipt.Failure(run, null, "worker_missing", 4);
        var worker = InvokeFixed(python, "-I -B -X utf8 " + Quote(entry)
            + " --install-root " + Quote(launch.Install) + " --app-data " + Quote(launch.AppData)
            + " --vault " + Quote(launch.Vault) + " --run-id " + Quote(run), launch.Install, cancel);
        if (worker.Error != null) return Receipt.Failure(run, null, worker.Error, 4);
        try { return Interpret(worker.Frame, run, worker.ExitCode); }
        catch (Exception) { return Receipt.Failure(run, null, "worker_protocol", 4); }
    }

    private static void SaveProbe(string appData, Receipt receipt)
    {
        for (var dir = new DirectoryInfo(appData); dir != null; dir = dir.Parent)
            if (!dir.Exists || (dir.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("probe_directory_unavailable");
        string path = Path.Combine(appData, "win05-native-probe.json");
        using (var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            new DataContractJsonSerializer(typeof(Receipt)).WriteObject(stream, receipt);
            stream.Flush(true);
        }
    }

    private sealed class MarginButton : Button
    {
        internal void InvokeForProbe() { OnClick(); }
    }

    private sealed class MainWindow : Window
    {
        private readonly Launch launch;
        private readonly MarginButton calculate;
        private readonly TextBlock status;
        private CancellationTokenSource cancellation;
        private Task<Receipt> pending;
        private bool closed, probeStarted;

        internal MainWindow(Launch options)
        {
            launch = options;
            Title = "Финансовый ассистент · WIN-05";
            Width = 530;
            MinWidth = 340;
            SizeToContent = SizeToContent.Height;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            var panel = new StackPanel {Margin = new Thickness(24)};
            panel.Children.Add(new TextBlock {Text = "Маржа учебной группы", FontSize = 22, TextWrapping = TextWrapping.Wrap});
            calculate = new MarginButton {Content = "Рассчитать операционную маржу", HorizontalAlignment = HorizontalAlignment.Left,
                Padding = new Thickness(12, 7, 12, 7), Margin = new Thickness(0, 16, 0, 16)};
            AutomationProperties.SetAutomationId(calculate, "calculateOwnMargin");
            panel.Children.Add(calculate);
            status = new TextBlock {Text = "Ожидается расчёт по собственному учебному документу.", TextWrapping = TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(status, "ownMarginResult");
            panel.Children.Add(status);
            Content = panel;
            calculate.Click += Calculate;
            ContentRendered += (sender, args) => {
                if (launch.Probe == null || probeStarted) return;
                probeStarted = true;
                Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(calculate.InvokeForProbe));
            };
            Closing += (sender, args) => { closed = true; if (cancellation != null) cancellation.Cancel(); };
        }

        private async void Calculate(object sender, RoutedEventArgs args)
        {
            if (closed || pending != null) return;
            calculate.IsEnabled = false;
            status.Text = "Проверяем источник и рассчитываем маржу…";
            var nativeRun = launch.Probe ?? Guid.NewGuid().ToString("N");
            cancellation = new CancellationTokenSource();
            var token = cancellation.Token;
            pending = Task.Run(() => InvokeService(launch, nativeRun, token));
            Receipt receipt = await pending;
            pending = null;
            cancellation.Dispose();
            cancellation = null;
            if (closed) return;

            status.Text = receipt.ExitCode == 0
                ? "Операционная маржа: " + receipt.display + "%\nСобственный учебный PDF, страница " + receipt.source_page + "."
                : "Расчёт не выполнен. Код: " + receipt.error;
            if (launch.Probe == null) { calculate.IsEnabled = true; return; }
            int exitCode = receipt.ExitCode;
            try { SaveProbe(launch.AppData, receipt); }
            catch (Exception) { exitCode = 5; }
            ScheduleShutdown(exitCode);
        }

        private void ScheduleShutdown(int exitCode)
        {
            Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(() => Application.Current.Shutdown(exitCode)));
        }

        internal void WaitForWorker()
        {
            if (pending != null) pending.Wait(2500);
        }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Launch launch;
        try { launch = Launch.Parse(args); }
        catch (ArgumentException) { return 64; }
        catch (IOException) { return 64; }
        if (!Environment.Is64BitProcess) return 64;
        var app = new Application();
        var window = new MainWindow(launch);
        int status = app.Run(window);
        window.WaitForWorker();
        return status;
    }
}
