// Evidence collector only: no install/uninstall, network requests or model calls.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Management;
using System.Net.NetworkInformation;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using Microsoft.Win32;

public sealed class Readiness {
    public bool SameHost,Is64,AdministratorToken,AdministratorGroup,CleanDeclared,ProvenancePresent;
    public int WindowsBuild,ProductType,FrameworkRelease,KnownGlobalPython,KnownOllama,ActiveInterfaces;
    public List<string> Blockers(){
        var b=new List<string>();
        if(SameHost)b.Add("original_host_rejected");
        if(!Is64||WindowsBuild<22000||ProductType!=1)b.Add("Windows11_x64_client_required");
        if(FrameworkRelease<528040)b.Add("Framework48_required");
        if(AdministratorToken||AdministratorGroup)b.Add("standard_non_admin_account_required");
        if(!ProvenancePresent||!CleanDeclared)b.Add("clean_provenance_not_declared");
        if(KnownGlobalPython>0)b.Add("global_Python_found");
        if(KnownOllama>0)b.Add("Ollama_found");
        if(ActiveInterfaces>0)b.Add("offline_interfaces_not_confirmed");
        return b;
    }
}
public static class GuestEvidence {
    public const string InstallerSha="f69523d44f474eacb0905d66e4f90294a3124a3d348c44222e6fe8e9ec3e56cf";
    public const long InstallerBytes=22434104;
    static JavaScriptSerializer json=new JavaScriptSerializer(){MaxJsonLength=2000000};
    public static string Hash(byte[] bytes){using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
    static string FileHash(string p){using(var h=SHA256.Create())using(var f=File.OpenRead(p))return BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant();}
    public static string MachineFingerprint(string salt){
        using(var k=RegistryKey.OpenBaseKey(RegistryHive.LocalMachine,RegistryView.Registry64).OpenSubKey(@"SOFTWARE\Microsoft\Cryptography")){
            var id=k==null?null:k.GetValue("MachineGuid") as string;
            if(String.IsNullOrWhiteSpace(id))throw new InvalidDataException("machine_identity_unavailable");
            return Hash(Encoding.UTF8.GetBytes(salt+"\n"+id));
        }
    }
    static Dictionary<string,object> Read(string p){
        if(new FileInfo(p).Length>1000000)throw new InvalidDataException("bounded_json_required");
        return (Dictionary<string,object>)json.DeserializeObject(File.ReadAllText(p,Encoding.UTF8));
    }
    public static bool ProvenanceValid(Dictionary<string,object> p){
        string[] keys={"schema","session_id","kind","os_source","clean_state_note","clean_state_declared"};
        return p.Count==keys.Length&&keys.All(k=>p.ContainsKey(k))&&(string)p["schema"]=="win02b-provenance-1"&&
            Regex.IsMatch((string)p["session_id"],"^[a-zA-Z0-9_-]{1,64}$")&&
            new[]{"fresh_install","reverted_clean_snapshot","separate_clean_machine"}.Contains((string)p["kind"])&&
            ((string)p["os_source"]).Length>=8&&((string)p["os_source"]).Length<=512&&
            ((string)p["clean_state_note"]).Length>=8&&((string)p["clean_state_note"]).Length<=1024&&
            p["clean_state_declared"] is bool&&(bool)p["clean_state_declared"];
    }
    public static List<string> KnownPrograms(string[] names){
        var found=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(var dir in (Environment.GetEnvironmentVariable("PATH")??"").Split(';')){
            if(String.IsNullOrWhiteSpace(dir))continue;
            foreach(var name in names){
                string p;try{p=Path.Combine(dir.Trim('"'),name);}catch{continue;}
                if(File.Exists(p)){
                    // Record WindowsApps aliases separately; do not execute them.
                    if(p.IndexOf("\\Microsoft\\WindowsApps\\",StringComparison.OrdinalIgnoreCase)>=0)continue;
                    found.Add(p);
                }
            }
        }
        return found.ToList();
    }
    static bool PythonRegistry(){
        foreach(var hive in new[]{RegistryHive.CurrentUser,RegistryHive.LocalMachine})foreach(var view in new[]{RegistryView.Registry32,RegistryView.Registry64})
            using(var key=RegistryKey.OpenBaseKey(hive,view).OpenSubKey(@"SOFTWARE\Python\PythonCore"))if(key!=null&&key.SubKeyCount>0)return true;
        return false;
    }
    static string Installed(){return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","Проектная практика WIN02");}
    static Dictionary<string,string> DataHashes(string path){
        var d=new Dictionary<string,string>();if(!Directory.Exists(path))return d;
        var pending=new Stack<string>();pending.Push(path);long total=0;
        while(pending.Count>0){
            string dir=pending.Pop();if((File.GetAttributes(dir)&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("own_data_reparse_refused");
            foreach(var p in Directory.GetFiles(dir)){
                if((File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("own_data_reparse_refused");
                long size=new FileInfo(p).Length;total+=size;
                if(d.Count>=5000||size>50000000||total>100000000)throw new InvalidDataException("own_data_size_limit");
                d[p.Substring(path.Length+1).Replace('\\','/')]=FileHash(p);
            }
            foreach(var sub in Directory.GetDirectories(dir))pending.Push(sub);
        }
        return d;
    }
    static bool Inside(string root,string relative){
        return !relative.Contains(":")&&!relative.StartsWith("/")&&!relative.StartsWith("\\")&&!relative.Replace('\\','/').Split('/').Contains("..")&&Path.GetFullPath(Path.Combine(root,relative)).StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase);
    }
    static object OwnSnapshot(string phase,Dictionary<string,object> guard,string output){
        string install=Installed(),data=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ProjectPractice","WIN02");
        string manifestPath=Path.Combine(install,"payload.json");bool present=File.Exists(manifestPath),payloadOK=false,readonlyOK=false;int checkedFiles=0;
        if(present){
            payloadOK=FileHash(manifestPath)==(string)guard["payload_manifest_sha256"];readonlyOK=true;
            if(payloadOK){var manifest=Read(manifestPath);var files=(Dictionary<string,object>)manifest["files"];
                foreach(var item in files){if(!Inside(install,item.Key))throw new InvalidDataException("payload_path");string p=Path.Combine(install,item.Key);payloadOK=payloadOK&&File.Exists(p)&&FileHash(p)==(string)item.Value;readonlyOK=readonlyOK&&File.Exists(p)&&(File.GetAttributes(p)&FileAttributes.ReadOnly)!=0;checkedFiles++;}
            }
        }
        var hashes=DataHashes(data);bool? preserved=null;
        string baseline=Path.Combine(output,"before-uninstall.json");
        if(phase=="uninstalled"&&File.Exists(baseline)){
            var before=Read(baseline);var snapshot=(Dictionary<string,object>)before["own_application"];var old=(Dictionary<string,object>)snapshot["data_file_sha256"];
            preserved=old.All(x=>hashes.ContainsKey(x.Key)&&hashes[x.Key]==(string)x.Value);
        }
        int ownProcesses=0;bool processReadComplete=true;
        foreach(var name in new[]{"ProjectPractice","python"})foreach(var p in Process.GetProcessesByName(name))using(p){try{if(p.MainModule.FileName.StartsWith(install+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))ownProcesses++;}catch{processReadComplete=false;}}
        bool uninstallKey;
        using(var key=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\ProjectPracticeWIN02"))uninstallKey=key!=null;
        string shortcut=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"Проектная практика WIN02","Финансовые документы.lnk");
        return new{install_present=Directory.Exists(install),payload_manifest_present=present,payload_matches_pinned_manifest=payloadOK,readonly_assets=readonlyOK,checked_payload_files=checkedFiles,shortcut_present=File.Exists(shortcut),HKCU_uninstall_present=uninstallKey,data_file_sha256=hashes,data_preserved_from_before_uninstall=preserved,own_processes=ownProcesses,process_read_complete=processReadComplete,visual_source_highlight="manual_pending",spoken_Narrator="manual_pending",system200_DPI="manual_pending",system_high_contrast="manual_pending"};
    }
    static void Emit(object d){Console.WriteLine(json.Serialize(d));}
    public static int Main(string[] args){
        Console.OutputEncoding=new UTF8Encoding(false);
        try{
            if(args.Length!=1||!new[]{"preflight","installed","before-uninstall","uninstalled"}.Contains(args[0])){Emit(new{status="invalid_phase",guest_accepted=false});return 64;}
            string kit=AppDomain.CurrentDomain.BaseDirectory,guardPath=Path.Combine(kit,"host-guard.private.json");
            if(!File.Exists(guardPath)){Emit(new{status="host_guard_missing",guest_accepted=false});return 22;}
            var guard=Read(guardPath);
            string fingerprint=MachineFingerprint((string)guard["salt"]);
            if(fingerprint==(string)guard["host_hash"]){Emit(new{schema="win02b-checkpoint-1",status="original_host_rejected",phase=args[0],guest_accepted=false,guest_environment_collected=false,model_calls=0});return 21;}
            string setup=Path.Combine(kit,"ProjectPractice-WIN02-setup.exe");
            if(!File.Exists(setup)||new FileInfo(setup).Length!=InstallerBytes||FileHash(setup)!=InstallerSha){Emit(new{status="installer_hash_mismatch",guest_accepted=false});return 23;}
            var provenance=Read(Path.Combine(kit,"provenance.json"));bool declared=ProvenanceValid(provenance);
            var principal=new WindowsPrincipal(WindowsIdentity.GetCurrent());var identity=WindowsIdentity.GetCurrent();
            int build=Convert.ToInt32(Registry.GetValue(@"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion","CurrentBuildNumber",0));
            int framework=Convert.ToInt32(Registry.GetValue(@"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full","Release",0));
            int productType=0;string caption="unknown";
            using(var search=new ManagementObjectSearcher("SELECT Caption,ProductType FROM Win32_OperatingSystem"))foreach(ManagementObject o in search.Get()){productType=Convert.ToInt32(o["ProductType"]);caption=(string)o["Caption"];}
            var network=NetworkInterface.GetAllNetworkInterfaces().Where(n=>n.NetworkInterfaceType!=NetworkInterfaceType.Loopback).Select(n=>new{type=n.NetworkInterfaceType.ToString(),state=n.OperationalStatus.ToString()}).ToArray();
            var readiness=new Readiness(){SameHost=false,Is64=Environment.Is64BitOperatingSystem&&Environment.Is64BitProcess,WindowsBuild=build,ProductType=productType,FrameworkRelease=framework,AdministratorToken=principal.IsInRole(WindowsBuiltInRole.Administrator),AdministratorGroup=identity.Groups.Cast<IdentityReference>().Any(x=>x.Value=="S-1-5-32-544"),CleanDeclared=declared,ProvenancePresent=true,KnownGlobalPython=KnownPrograms(new[]{"python.exe","python3.exe","py.exe"}).Count+(PythonRegistry()?1:0),KnownOllama=KnownPrograms(new[]{"ollama.exe"}).Count,ActiveInterfaces=network.Count(x=>x.state=="Up")};
            var blockers=readiness.Blockers();
            if(args[0]=="preflight"&&(Directory.Exists(Installed())||Directory.Exists(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ProjectPractice","WIN02"))))blockers.Add("preinstall_application_state_not_clean");
            if(!declared){Emit(new{status="provenance_required",blockers=blockers,guest_accepted=false});return 24;}
            string output=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ProjectPractice","WIN02B-evidence",(string)provenance["session_id"]);Directory.CreateDirectory(output);
            string file=Path.Combine(output,args[0]+".json");if(File.Exists(file))throw new InvalidOperationException("checkpoint_exists_use_new_session");
            var own=OwnSnapshot(args[0],guard,output);
            var record=new{schema="win02b-checkpoint-1",phase=args[0],collected_utc=DateTime.UtcNow.ToString("o"),status="evidence_only_not_acceptance",guest_accepted=false,readiness_eligible=blockers.Count==0,blockers=blockers,provenance_declared=provenance,provenance_independently_verified=false,OS=caption,build=build,framework_release=framework,standard_account_candidate=!readiness.AdministratorToken&&!readiness.AdministratorGroup,network_interfaces=network,network_probe_sent=false,known_global_python=readiness.KnownGlobalPython,known_ollama=readiness.KnownOllama,WindowsApps_aliases="Excluded from executable discovery; manual installed-app review still required",own_application=own,model_calls=0};
            File.WriteAllText(file,json.Serialize(record),new UTF8Encoding(false));Emit(record);return blockers.Count==0?0:25;
        }catch(Exception e){Emit(new{status="collector_error",code=e.GetType().Name,detail=e.Message,guest_accepted=false});return 2;}
    }
}
