// Synthetic controls of evidence gates, never guest acceptance results.
using System;
using System.Collections.Generic;
using System.Linq;
public static class CollectorTests {
    static int count=0;
    static Readiness Eligible(){return new Readiness(){Is64=true,WindowsBuild=26200,ProductType=1,FrameworkRelease=533509,CleanDeclared=true,ProvenancePresent=true};}
    static void Check(bool x,string name){count++;if(!x)throw new Exception("failed_control:"+name);}
    static Dictionary<string,object> Provenance(){return new Dictionary<string,object>(){{"schema","win02b-provenance-1"},{"session_id","guest_run_01"},{"kind","fresh_install"},{"os_source","Own authorized test image"},{"clean_state_note","Fresh image before Python or Ollama install"},{"clean_state_declared",true}};}
    public static int Main(){
        var r=Eligible();Check(r.Blockers().Count==0,"eligible_does_not_imply_acceptance");
        r=Eligible();r.SameHost=true;Check(r.Blockers().Contains("original_host_rejected"),"same_host");
        r=Eligible();r.FrameworkRelease=528039;Check(r.Blockers().Contains("Framework48_required"),"missing_framework");
        r=Eligible();r.AdministratorToken=true;Check(r.Blockers().Contains("standard_non_admin_account_required"),"elevated");
        r=Eligible();r.AdministratorGroup=true;Check(r.Blockers().Contains("standard_non_admin_account_required"),"filtered_admin_not_standard_user");
        r=Eligible();r.WindowsBuild=19045;Check(r.Blockers().Contains("Windows11_x64_client_required"),"old_windows");
        r=Eligible();r.ProductType=3;Check(r.Blockers().Contains("Windows11_x64_client_required"),"server_not_client");
        r=Eligible();r.Is64=false;Check(r.Blockers().Contains("Windows11_x64_client_required"),"architecture");
        r=Eligible();r.CleanDeclared=false;Check(r.Blockers().Contains("clean_provenance_not_declared"),"no_clean_declaration");
        r=Eligible();r.KnownGlobalPython=1;Check(r.Blockers().Contains("global_Python_found"),"global_python");
        r=Eligible();r.KnownOllama=1;Check(r.Blockers().Contains("Ollama_found"),"model_runtime_present");
        r=Eligible();r.ActiveInterfaces=1;Check(r.Blockers().Contains("offline_interfaces_not_confirmed"),"network_up_not_offline");
        Check(GuestEvidence.ProvenanceValid(Provenance()),"provenance_shape");
        var p=Provenance();p["session_id"]="../outside";Check(!GuestEvidence.ProvenanceValid(p),"session_path_escape");
        p=Provenance();p["kind"]="new_venv";Check(!GuestEvidence.ProvenanceValid(p),"venv_not_clean_machine");
        p=Provenance();p["guest_passed"]=true;Check(!GuestEvidence.ProvenanceValid(p),"unknown_acceptance_field");
        p=Provenance();p["os_source"]="unknown";Check(!GuestEvidence.ProvenanceValid(p),"missing_source");
        Console.WriteLine("{\"synthetic_gate_controls_passed\":"+count+",\"guest_acceptance_tested\":false}");return 0;
    }
}
