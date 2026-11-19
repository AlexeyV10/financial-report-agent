// Reads UI Automation properties for one exact, test-owned WIN-08 shell window.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

internal static class ShellUiAObserver
{
    private const string WindowTitle = "Финансовый ассистент · Рабочий стол";
    private const string CompletedStatus = "Расчёт завершён.";
    private const string ExpectedResult = "Операционная маржа: 15.00%\nСобственный учебный PDF, страница 1.";

    private static readonly string[] Navigation = {"projectsTab", "documentsTab", "analysisTab"};
    private static readonly string[] Projects = {"selectVaultA", "selectVaultB"};
    private static readonly string[] Documents = {"importDocument", "documentQuery", "searchDocuments", "documentResults"};
    private static readonly string[] Analysis = {"runAnalysis", "analysisResult"};
    private static readonly string[] KnownIds = Navigation.Concat(Projects).Concat(Documents).Concat(Analysis)
        .Concat(new[] {"shellStatus"}).ToArray();
    private static readonly Dictionary<string, string> StableNames = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        {"projectsTab", "Проекты"}, {"documentsTab", "Документы"}, {"analysisTab", "Анализ"},
        {"documentQuery", "Поиск по тексту документа"}, {"documentResults", "Найденные версии документов"},
        {"analysisResult", "Результат анализа"},
    };

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(IntPtr window);

    private sealed class Arguments
    {
        internal int Pid;
        internal string Image;
        internal string Output;
        internal string Screen;
        internal string Status;
    }

    private sealed class ObservationError : Exception
    {
        internal readonly string Code;
        internal ObservationError(string code) { Code = code; }
    }

    private sealed class Control
    {
        internal AutomationElement Element;
        internal bool Unique;
        internal bool Visible;
        internal bool Enabled;
        internal bool Focusable;
        internal bool Named;
        internal string Name;
        internal ControlType Type;

        internal bool IsVisibleNamed(ControlType expected)
        {
            return Unique && Visible && Named && Type == expected;
        }
    }

    private static string LocalAbsolutePath(string value)
    {
        if (String.IsNullOrEmpty(value) || value.Length < 3 || value[1] != ':'
            || (value[2] != '\\' && value[2] != '/')
            || value.IndexOf(':', 2) >= 0
            || !((value[0] >= 'A' && value[0] <= 'Z') || (value[0] >= 'a' && value[0] <= 'z')))
            throw new ArgumentException();
        return Path.GetFullPath(value);
    }

    private static Arguments Parse(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        if (args.Length % 2 != 0) throw new ArgumentException();
        for (int i = 0; i < args.Length; i += 2)
        {
            string flag = args[i];
            if (flag != "--pid" && flag != "--expected-exe" && flag != "--output"
                && flag != "--expect-screen" && flag != "--expect-status")
                throw new ArgumentException();
            values.Add(flag, args[i + 1]);
        }
        int pid;
        string rawPid, image, output, screen, status;
        if (!values.TryGetValue("--pid", out rawPid)
            || !Int32.TryParse(rawPid, NumberStyles.None, CultureInfo.InvariantCulture, out pid) || pid <= 0
            || !values.TryGetValue("--expected-exe", out image) || !values.TryGetValue("--output", out output))
            throw new ArgumentException();

        values.TryGetValue("--expect-screen", out screen);
        values.TryGetValue("--expect-status", out status);
        if ((screen != null && screen != "projects" && screen != "documents" && screen != "analysis")
            || (status != null && (status.Length == 0 || status.Length > 512)))
            throw new ArgumentException();
        image = LocalAbsolutePath(image);
        output = LocalAbsolutePath(output);
        if (!File.Exists(image) || !String.Equals(Path.GetExtension(image), ".exe", StringComparison.OrdinalIgnoreCase)
            || !String.Equals(Path.GetExtension(output), ".json", StringComparison.OrdinalIgnoreCase)
            || !Directory.Exists(Path.GetDirectoryName(output)))
            throw new ArgumentException();
        return new Arguments {Pid = pid, Image = image, Output = output, Screen = screen, Status = status};
    }

    private static Control ReadControl(AutomationElement window, int pid, string id)
    {
        var condition = new AndCondition(new PropertyCondition(AutomationElement.ProcessIdProperty, pid),
            new PropertyCondition(AutomationElement.AutomationIdProperty, id));
        var found = window.FindAll(TreeScope.Descendants, condition);
        if (found.Count != 1) return new Control();
        var element = found[0];
        var value = element.Current;
        return new Control {
            Element = element, Unique = true, Visible = !value.IsOffscreen && !value.BoundingRectangle.IsEmpty,
            Enabled = value.IsEnabled, Focusable = value.IsKeyboardFocusable, Name = value.Name,
            Named = !String.IsNullOrWhiteSpace(value.Name), Type = value.ControlType,
        };
    }

    private static bool HasButton(IDictionary<string, Control> controls, string id)
    {
        Control button = controls[id];
        return button.IsVisibleNamed(ControlType.Button) && button.Enabled && button.Focusable;
    }

    private static bool? MatchesStableName(string id, Control control)
    {
        string expected;
        return StableNames.TryGetValue(id, out expected) ? (bool?)(control.Name == expected) : null;
    }

    private static object ReadFocus(AutomationElement window, int pid)
    {
        var focus = AutomationElement.FocusedElement;
        if (focus == null || focus.Current.ProcessId != pid) return null;
        var ancestor = focus;
        for (int depth = 0; depth < 64 && ancestor != null && ancestor.Current.ProcessId == pid; depth++)
        {
            if (Automation.Compare(ancestor, window))
            {
                var value = focus.Current;
                if (value.IsOffscreen || value.BoundingRectangle.IsEmpty || !value.HasKeyboardFocus) return null;
                string knownId = KnownIds.Contains(value.AutomationId) ? value.AutomationId : null;
                return new {
                    automation_id = knownId, control_type = value.ControlType.ProgrammaticName,
                    named = !String.IsNullOrWhiteSpace(value.Name), keyboard_focusable = value.IsKeyboardFocusable,
                    visible = true, has_keyboard_focus = true,
                };
            }
            ancestor = TreeWalker.RawViewWalker.GetParent(ancestor);
        }
        return null;
    }

    private static string Route(IDictionary<string, Control> controls)
    {
        var visible = new List<string>();
        if (Projects.Any(id => controls[id].Visible)) visible.Add("projects");
        if (Documents.Any(id => controls[id].Visible)) visible.Add("documents");
        if (Analysis.Any(id => controls[id].Visible)) visible.Add("analysis");
        return visible.Count == 1 ? visible[0] : null;
    }

    private static bool ControlsMatch(string screen, IDictionary<string, Control> controls)
    {
        if (screen == "projects") return Projects.All(id => HasButton(controls, id));
        if (screen == "documents")
            return HasButton(controls, "importDocument") && HasButton(controls, "searchDocuments")
                && controls["documentQuery"].IsVisibleNamed(ControlType.Edit) && controls["documentQuery"].Focusable
                && MatchesStableName("documentQuery", controls["documentQuery"]) == true
                && controls["documentResults"].IsVisibleNamed(ControlType.List)
                && MatchesStableName("documentResults", controls["documentResults"]) == true;
        if (screen == "analysis")
            return HasButton(controls, "runAnalysis") && controls["analysisResult"].IsVisibleNamed(ControlType.Edit)
                && MatchesStableName("analysisResult", controls["analysisResult"]) == true;
        return false;
    }

    private static object Observe(Arguments args, out bool ok)
    {
        using (Process process = Process.GetProcessById(args.Pid))
        {
            if (process.HasExited || !String.Equals(Path.GetFullPath(process.MainModule.FileName),
                                                    args.Image, StringComparison.OrdinalIgnoreCase))
                throw new ObservationError("target_process_mismatch");
            DateTime creation = process.StartTime;
            IntPtr handle = process.MainWindowHandle;
            if (handle == IntPtr.Zero || !IsWindowVisible(handle)) throw new ObservationError("target_window_unavailable");
            var window = AutomationElement.FromHandle(handle);
            var windowData = window.Current;
            if (windowData.ProcessId != args.Pid || windowData.NativeWindowHandle != unchecked((int)handle.ToInt64())
                || windowData.ControlType != ControlType.Window || windowData.IsOffscreen
                || windowData.Name != WindowTitle || process.MainWindowTitle != WindowTitle)
                throw new ObservationError("target_window_mismatch");

            var controls = KnownIds.ToDictionary(id => id, id => ReadControl(window, args.Pid, id), StringComparer.Ordinal);
            string screen = Route(controls);
            bool navigation = Navigation.All(id => HasButton(controls, id) && MatchesStableName(id, controls[id]) == true);
            bool matchedControls = ControlsMatch(screen, controls);
            Control status = controls["shellStatus"];
            bool statusVisible = status.IsVisibleNamed(ControlType.Text);
            bool statusMatches = args.Status == null || (statusVisible && status.Name == args.Status);
            bool screenMatches = args.Screen == null || args.Screen == screen;

            bool valuePattern = false, readOnly = false, resultHasText = false, exactDemoResult = false;
            if (screen == "analysis" && controls["analysisResult"].Visible)
            {
                object pattern;
                if (controls["analysisResult"].Element.TryGetCurrentPattern(ValuePattern.Pattern, out pattern))
                {
                    valuePattern = true;
                    var value = ((ValuePattern)pattern).Current;
                    readOnly = value.IsReadOnly;
                    string text = (value.Value ?? "").Replace("\r\n", "\n").Trim();
                    resultHasText = text.Length > 0;
                    exactDemoResult = text == ExpectedResult;
                }
            }
            bool analysisMatches = screen != "analysis" || (valuePattern && readOnly
                && (status.Name != CompletedStatus || exactDemoResult));
            object focus = ReadFocus(window, args.Pid);

            process.Refresh();
            if (process.HasExited || process.StartTime != creation || process.MainWindowHandle != handle
                || !IsWindowVisible(handle)) throw new ObservationError("target_changed_during_observation");
            ok = navigation && matchedControls && statusVisible && screenMatches && statusMatches && analysisMatches;
            return new {
                schema = "win08-shell-uia-1", ok = ok, image_matches = true, window_title_matches = true,
                process_scope_verified = true, screen = screen, expected_screen_matched = screenMatches,
                expected_status_matched = statusMatches, status_visible_named = statusVisible,
                completed_status_observed = status.Name == CompletedStatus, navigation_keyboard_focusable = navigation,
                active_controls_match = matchedControls, analysis_result_value_pattern = valuePattern,
                analysis_result_read_only = readOnly, analysis_result_has_text = resultHasText,
                exact_demo_result_observed = exactDemoResult, focused_element = focus, input_performed = false,
                controls = KnownIds.Select(id => new { automation_id = id, visible = controls[id].Visible,
                    unique = controls[id].Unique, named = controls[id].Named,
                    stable_name_matched = MatchesStableName(id, controls[id]),
                    keyboard_focusable = controls[id].Focusable, enabled = controls[id].Enabled }).ToArray(),
            };
        }
    }

    private static object Failure(string code)
    {
        return new {schema = "win08-shell-uia-1", ok = false, error = code, input_performed = false};
    }

    private static int Main(string[] args)
    {
        Arguments parsed;
        try { parsed = Parse(args); }
        catch (ArgumentException) { Console.Error.WriteLine("invalid_observer_arguments"); return 2; }
        catch (IOException) { Console.Error.WriteLine("invalid_observer_arguments"); return 2; }
        catch (NotSupportedException) { Console.Error.WriteLine("invalid_observer_arguments"); return 2; }

        object receipt = null;
        bool passed = false;
        // A blocked provider must not prevent the observer process from exiting.
        var observer = new Thread(delegate()
        {
            try { receipt = Observe(parsed, out passed); }
            catch (ObservationError error) { receipt = Failure(error.Code); }
            catch (ArgumentException) { receipt = Failure("target_unavailable"); }
            catch (InvalidOperationException) { receipt = Failure("target_unavailable"); }
            catch (System.ComponentModel.Win32Exception) { receipt = Failure("target_unavailable"); }
            catch (ElementNotAvailableException) { receipt = Failure("uia_element_unavailable"); }
            catch (COMException) { receipt = Failure("uia_provider_unavailable"); }
            catch (Exception) { receipt = Failure("observer_failed"); }
        });
        observer.IsBackground = true;
        observer.SetApartmentState(ApartmentState.MTA);
        observer.Start();
        bool joined = observer.Join(TimeSpan.FromSeconds(8));
        object result = joined ? (receipt ?? Failure("observer_no_result")) : Failure("observer_timeout");
        try
        {
            using (var stream = new FileStream(parsed.Output, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
                writer.Write(new JavaScriptSerializer().Serialize(result));
        }
        catch (IOException) { Console.Error.WriteLine("observer_output_unavailable"); return 3; }
        catch (UnauthorizedAccessException) { Console.Error.WriteLine("observer_output_unavailable"); return 3; }
        return joined && passed ? 0 : 1;
    }
}
