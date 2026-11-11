// WIN-02 installed entry point. Reuses unchanged WPF slice and Python calculator.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Win32;

public static class RuntimeHost {
    static JavaScriptSerializer json=new JavaScriptSerializer(){MaxJsonLength=2000000};
    static IntPtr job=IntPtr.Zero;static Mutex mutex;
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr CreateJobObject(IntPtr attributes,string name);
    [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetInformationJobObject(IntPtr handle,int type,ref ExtendedLimits data,uint length);
    [DllImport("kernel32.dll",SetLastError=true)]static extern bool AssignProcessToJobObject(IntPtr handle,IntPtr process);
    [StructLayout(LayoutKind.Sequential)]struct BasicLimits {public long ProcessTime,JobTime;public uint Flags;public UIntPtr MinimumWorkingSet,MaximumWorkingSet;public uint ActiveProcessLimit;public UIntPtr Affinity;public uint Priority,Scheduling;}
    [StructLayout(LayoutKind.Sequential)]struct IOCounters {public ulong ReadOps,WriteOps,OtherOps,ReadBytes,WriteBytes,OtherBytes;}
    [StructLayout(LayoutKind.Sequential)]struct ExtendedLimits {public BasicLimits Basic;public IOCounters IO;public UIntPtr ProcessMemory,JobMemory,PeakProcess,PeakJob;}
    static void OwnChildren(){
        job=CreateJobObject(IntPtr.Zero,null);var limits=new ExtendedLimits();limits.Basic.Flags=0x2000;
        if(job==IntPtr.Zero||!SetInformationJobObject(job,9,ref limits,(uint)Marshal.SizeOf(typeof(ExtendedLimits)))||!AssignProcessToJobObject(job,Process.GetCurrentProcess().Handle))throw new InvalidOperationException("owned_process_job");
        // Static handle lives to process exit. Windows closes it on a hard parent crash,
        // terminating children as well. No breakaway flag is used for workers.
    }
    static string Sha(string p){using(var h=SHA256.Create())using(var f=File.OpenRead(p))return BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant();}
    public static void Verify(string install){
        var manifest=(Dictionary<string,object>)json.DeserializeObject(File.ReadAllText(Path.Combine(install,"payload.json"),Encoding.UTF8));
        if((string)manifest["schema"]!="win02-payload-1")throw new InvalidDataException("payload_schema");
        var files=(Dictionary<string,object>)manifest["files"];
        foreach(var item in files){
            string relative=item.Key;
            if(relative.Contains(":")||relative.StartsWith("/")||relative.StartsWith("\\")||Array.IndexOf(relative.Replace('\\','/').Split('/'),"..")>=0)throw new InvalidDataException("payload_path");
            string path=Path.GetFullPath(Path.Combine(install,relative));
            if(!path.StartsWith(install+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||!File.Exists(path)||Sha(path)!=(string)item.Value)throw new InvalidDataException("payload_changed");
        }
        // This is corruption detection, not authentication of an unsigned package.
    }
    static void Save(string path,object obj){File.WriteAllText(path,json.Serialize(obj),new UTF8Encoding(false));}
    static string Quote(string s){if(s.Contains("\"")||s.EndsWith("\\"))throw new ArgumentException("path");return "\""+s+"\"";}
    [STAThread]public static int Main(string[] args){
        bool diagnose=args.Length==1&&args[0]=="--diagnose",probe=args.Length==1&&args[0]=="--probe";
        if(args.Length>0&&!diagnose&&!probe)return 64;
        string install=AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        string data=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ProjectPractice","WIN02");
        string run=Path.Combine(data,"runs",Guid.NewGuid().ToString("N"));Directory.CreateDirectory(run);
        string receipt=Path.Combine(run,"host.json");
        try{
            bool created;mutex=new Mutex(true,"Local\\ProjectPracticeWIN02",out created);
            if(!created)throw new InvalidOperationException("already_running");
            if(!Environment.Is64BitProcess||Convert.ToInt32(Registry.GetValue(@"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full","Release",0))<528040)throw new InvalidOperationException("framework48_required");
            Verify(install);OwnChildren();
            string python=Path.Combine(install,"runtime","python.exe"),root=Path.Combine(install,"app"),demo=Path.Combine(root,"assets","demo");
            Save(receipt,new{schema="win02-host-1",status="verified",install=install,workspace=data,private_python=python,framework_release=Registry.GetValue(@"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full","Release",0),probe=probe,diagnose=diagnose,owned_process_job=true});
            if(diagnose){
                var info=new ProcessStartInfo(python,"-I -B -u "+Quote(Path.Combine(root,"spikes","windows_02","runtime_probe.py"))){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,WorkingDirectory=run};
                using(var p=Process.Start(info)){
                    var output=p.StandardOutput.ReadToEnd();var error=p.StandardError.ReadToEnd();p.WaitForExit();File.WriteAllText(Path.Combine(run,"runtime.json"),output,new UTF8Encoding(false));File.WriteAllText(Path.Combine(run,"stderr.txt"),error,new UTF8Encoding(false));return p.ExitCode;
                }
            }
            var app=new Application();var window=new WpfSpike(new[]{python,root,demo,Path.Combine(run,"ui.json")}.ConcatProbe(probe));
            window.Title="WIN-02 · Финансовые документы";
            window.Width=Math.Min(1120,SystemParameters.WorkArea.Width-32);window.Height=Math.Min(700,SystemParameters.WorkArea.Height-40);
            // Keep a finite table viewport at large DPI. The outer page can scroll
            // vertically on compact screens instead of clipping the lower result.
            var content=(Grid)window.Content;window.Content=null;content.Height=640;
            window.Content=new ScrollViewer(){Content=content,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            window.SizeChanged+=(s,e)=>{content.Height=Math.Max(640,window.ActualHeight-40);};
            app.Run(window);GC.KeepAlive(mutex);GC.KeepAlive(job);return 0;
        }catch(Exception e){
            Save(receipt,new{schema="win02-host-1",status="error",code=e.GetType().Name,detail=e.Message});
            if(!diagnose)MessageBox.Show("Не удалось открыть учебное приложение. Проверьте целостность установки и закройте его другие окна.","Проектная практика",MessageBoxButton.OK,MessageBoxImage.Error);
            return 2;
        }
    }
    static string[] ConcatProbe(this string[] values,bool probe){if(!probe)return values;return new[]{values[0],values[1],values[2],values[3],"--probe"};}
}
