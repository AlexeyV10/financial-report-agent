"""Fixed developer diagnostic of installed assets/runtime; never model/network calls."""
from pathlib import Path
import importlib.util,json,sys
sys.stdout.reconfigure(encoding='utf8',errors='strict')
from adapter import DemoAdapter
from renderer import PdfiumRenderer
import pypdfium2
ROOT=Path(__file__).resolve().parents[2]
def main():
    a=DemoAdapter(ROOT/'assets/demo');answer=a.run('installed-diagnostic')
    f=answer['financial_result'];renders=[]
    for rotation in [0,90,180,270]:
        p=PdfiumRenderer().render(a,2,rotation,2)
        renders.append({k:p[k] for k in ['width','height','rect','page','sha256','zoom','dpi','rotation']})
    result=dict(schema='win02-installed-diagnostic-1',execution_status=answer['execution_status'],financial_status=answer['financial_status'],display=f['display_value'],operation=f['operation_id'],source_sha=a.manifest['sha256'],renders=renders,python=sys.version,executable=sys.executable,prefix=sys.prefix,path=sys.path,isolated=sys.flags.isolated,no_user_site=sys.flags.no_user_site,pdfium=str(pypdfium2.PDFIUM_INFO),qt_present=importlib.util.find_spec('PySide6') is not None,new_model_calls=0)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
