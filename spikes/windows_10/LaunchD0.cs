using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows;

internal static class LaunchD0
{
    private const string MutexName = @"Local\ProjectPracticeWIN10";
    private const string Shell = "ProjectPractice-WIN10.exe";
    private const string EmptyWorkspace =
        "{\"schema\":\"workspace-context-1\",\"workspace_id\":\"d0-empty\",\"resources\":[]}\n";
    private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);

    private static FileAttributes? Attributes(string path)
    {
        try { return File.GetAttributes(path); }
        catch (FileNotFoundException) { return null; }
        catch (DirectoryNotFoundException) { return null; }
    }

    private static bool SafeDirectory(string path)
    {
        var attributes = Attributes(path);
        if (!attributes.HasValue) return false;
        if ((attributes.Value & (FileAttributes.Directory | FileAttributes.ReparsePoint))
            != FileAttributes.Directory)
            throw new IOException("Invalid application directory");
        return true;
    }

    private static bool SafeFile(string path)
    {
        var attributes = Attributes(path);
        if (!attributes.HasValue) return false;
        if ((attributes.Value & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
            throw new IOException("Invalid application file");
        return true;
    }

    private static string ChildDirectory(string parent, string name)
    {
        var path = Path.Combine(parent, name);
        if (!SafeDirectory(path)) Directory.CreateDirectory(path);
        if (!SafeDirectory(path)) throw new IOException("Application directory could not be created");
        return path;
    }

    private static string Quote(string value)
    {
        if (value.IndexOf('"') >= 0) throw new IOException("Invalid application path");
        return "\"" + value + new string('\\', value.Length - value.TrimEnd('\\').Length) + "\"";
    }

    private static ProcessStartInfo ProcessInfo(string executable, string arguments, string workingDirectory)
    {
        if (!SafeFile(executable)) throw new IOException("Application executable is missing");
        return new ProcessStartInfo(executable, arguments)
        {
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
    }

    private static void Provision(string install, string appData, string vault)
    {
        var launcher = Path.Combine(install, @"runtime\python.exe");
        var cli = Path.Combine(install, @"app\spikes\windows_10\d0_cli.py");
        if (!SafeFile(cli)) throw new IOException("Provisioning entry is missing");
        var args = "-I -B -X utf8 " + Quote(cli) + " --install-root " + Quote(install)
            + " --app-data " + Quote(appData) + " --vault " + Quote(vault) + " --provision";
        var info = ProcessInfo(launcher, args, install);
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        using (var process = Process.Start(info))
        {
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            if (!process.WaitForExit(45000))
            {
                try { process.Kill(); }
                catch (InvalidOperationException) { }
                process.WaitForExit(5000);
                throw new IOException("Provisioning deadline expired");
            }
            if (process.ExitCode != 0) throw new IOException("Provisioning failed");
        }
    }

    private static void EnsureEmptyProject(string workspaces, string vault)
    {
        const string Marker = "workspace.json";
        if (SafeDirectory(vault))
        {
            var marker = Path.Combine(vault, Marker);
            if (!SafeFile(marker) || new FileInfo(marker).Length != Utf8.GetByteCount(EmptyWorkspace)
                || File.ReadAllText(marker, Utf8) != EmptyWorkspace)
                throw new IOException("Unknown project marker");
            return;
        }
        var staging = ChildDirectory(workspaces, ".empty-" + Guid.NewGuid().ToString("N"));
        var temporary = Path.Combine(staging, Marker);
        try
        {
            using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                var data = Utf8.GetBytes(EmptyWorkspace);
                file.Write(data, 0, data.Length);
                file.Flush(true);
            }
            Directory.Move(staging, vault);
        }
        finally
        {
            if (SafeDirectory(staging))
            {
                File.Delete(temporary);
                Directory.Delete(staging);
            }
        }
    }

    private static int OpenApplication()
    {
        var install = Path.GetDirectoryName(typeof(LaunchD0).Assembly.Location);
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (!SafeDirectory(install) || !SafeDirectory(local)) throw new IOException("Missing application root");
        var data = ChildDirectory(local, "ProjectPracticeWIN10");
        var appData = ChildDirectory(data, "AppData");
        var workspaces = ChildDirectory(data, "workspaces");
        var vaultA = Path.Combine(workspaces, "Учебный проект");
        var vaultB = Path.Combine(workspaces, "Пустой проект");
        if (!SafeDirectory(vaultA)) Provision(install, appData, vaultA);
        if (!SafeDirectory(vaultA) || !SafeFile(Path.Combine(vaultA, "workspace.json"))
            || !SafeFile(Path.Combine(vaultA, "vault.sqlite3")))
            throw new IOException("The provisioned project is incomplete");
        EnsureEmptyProject(workspaces, vaultB);
        var args = "--app-data " + Quote(appData) + " --vault-a " + Quote(vaultA)
            + " --vault-b " + Quote(vaultB) + " --d0";
        var info = ProcessInfo(Path.Combine(install, Shell), args, install);
        using (var process = Process.Start(info))
        {
            process.WaitForExit();
            return process.ExitCode;
        }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length != 0) return 2;
        try
        {
            bool created;
            using (var mutex = new Mutex(true, MutexName, out created))
            {
                if (!created) return 0;
                try { return OpenApplication(); }
                finally { mutex.ReleaseMutex(); }
            }
        }
        catch (Exception error)
        {
            if (!(error is IOException || error is UnauthorizedAccessException || error is ArgumentException
                || error is InvalidOperationException || error is System.ComponentModel.Win32Exception))
                throw;
            MessageBox.Show("Не удалось открыть учебное приложение. Убедитесь, что установка завершена и папки приложения доступны.",
                "Финансовый ассистент", MessageBoxButton.OK, MessageBoxImage.Error);
            return 1;
        }
    }
}
