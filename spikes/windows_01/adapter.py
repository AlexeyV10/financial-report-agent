"""Narrow trusted synthetic source adapter, unchanged registered calculator07."""
from pathlib import Path
import hashlib, sys, json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.fact_admission import load_context
from financial_assistant.financial_calculator import calculate
from financial_assistant.contracts_v2 import need

class DemoAdapter:
    def __init__(self,workspace):
        self.workspace=Path(workspace).resolve()
        self.ctx=load_context(*(self.workspace/(n+'.json') for n in ['catalog','dictionary','admission']))
        self.manifest=json.loads((self.workspace/'manifest.json').read_text(encoding='utf8'))
        self.manifest_sha=hashlib.sha256((self.workspace/'manifest.json').read_bytes()).hexdigest()
        # Fixed asset name: manifest/model text never chooses a filesystem path.
        self.pdf=self.workspace/'own-demo-v1.pdf'
    def verify(self):
        import pypdfium2 as pdfium
        need(hashlib.sha256((self.workspace/'manifest.json').read_bytes()).hexdigest()==self.manifest_sha,'manifest_changed')
        self.ctx.validate()
        need(hashlib.sha256(self.pdf.read_bytes()).hexdigest()==self.manifest['sha256']==self.ctx.catalog['documents'][0]['sha256'],'source_changed')
        with pdfium.PdfDocument(str(self.pdf)) as doc:
            need(len(doc)==1,'source_pages')
            page=doc[0];text=page.get_textpage()
            full=text.get_text_bounded()
            need(all(s in full for s in ['IFRS / consolidated nonfinancial group','01 Jan 2025 - 31 Dec 2025','RUB million']),'source_header')
            for f in self.ctx.catalog['facts']:
                need(f['period']==dict(kind='duration',duration_type='full_year',start='2025-01-01',end='2025-12-31') and f['currency']=='RUB' and f['scale']==1000000,'source_context')
                rect=self.manifest['cells'][f['fact_id']]
                need(text.get_text_bounded(*rect).strip()==f['value'],'source_cell')
            text.close();page.close()
    def run(self,job):
        self.verify()
        facts={f['metric_id']:f for f in self.ctx.catalog['facts']}
        refs=[]
        for role,key in [('profit','operating_profit'),('revenue','revenue')]:
            f=facts[key];refs.append(dict(role=role,**{k:f[k] for k in ['fact_id','document_id','version_id','metric_id','definition_id','period']},source_unit=dict(currency=f['currency'],scale=f['scale'])))
        q=dict(schema_version='0.3',request_id=job,original_question='Операционная маржа собственного вымышленного примера',operation_id='operating_margin_v1',organization_id=facts['revenue']['organization_id'],consolidation='group',accounting_standard='IFRS',inputs=refs,version_policy='explicit_versions',comparability_id=None,result_unit=dict(kind='percent'),mode='snapshot',as_of=None)
        result=calculate(self.ctx,q,run_id=job)
        need(result['execution_status']=='completed' and result['financial_status']=='answered','calculator_refused')
        return result
