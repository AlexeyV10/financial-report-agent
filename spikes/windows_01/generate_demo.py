"""Own deterministic fixture v1; no issuer PDF, source text or financial gold imported."""
from pathlib import Path
from copy import deepcopy
import hashlib, json, sys
from reportlab.pdfgen.canvas import Canvas
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import digest

def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def generate(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    pdf=out/'own-demo-v1.pdf'
    c=Canvas(str(pdf),pagesize=(420,360),invariant=1,pageCompression=0)
    c.setTitle('WIN-01 own fictional data v1');c.setAuthor('Project practice / Codex assisted fixture')
    c.setFillColorRGB(.08,.30,.20);c.setFont('Helvetica-Bold',17)
    c.drawString(32,315,'OWN FICTIONAL GROUP')
    c.setFillColorRGB(.12,.12,.12);c.setFont('Helvetica',11)
    for y,text in [(287,'Educational fixture - not an issuer report'),(266,'IFRS / consolidated nonfinancial group'),(245,'Full year: 01 Jan 2025 - 31 Dec 2025'),(224,'Currency and scale: RUB million'),(204,'Metric                                      2025')]:c.drawString(32,y,text)
    c.setStrokeColorRGB(.7,.8,.74);c.line(32,195,385,195)
    c.drawString(32,180,'Revenue');c.drawString(306,180,'120')
    c.drawString(32,156,'Operating profit');c.drawString(306,156,'18')
    c.setFont('Helvetica',9);c.drawString(32,105,'Both amounts are positive. No publication date is asserted.')
    c.drawString(32,85,'Page 1 / Own generated example; redistribution permitted.')
    c.showPage();c.save()
    sha=hashlib.sha256(pdf.read_bytes()).hexdigest()
    cat=json.loads((ROOT/'data/catalogs/kp3_finance_dev_v1/runtime_catalog.json').read_text(encoding='utf8'))
    cat['catalog_id']='windows01-own-v1';cat['metrics']=[m for m in cat['metrics'] if m['metric_id'] in {'revenue','operating_profit'}]
    doc=deepcopy(cat['documents'][1]);doc.update(document_id='windows01-own',version_id='windows01-own-v1',sha256=sha,byte_length=pdf.stat().st_size,pdf_pages=1)
    period=dict(kind='duration',duration_type='full_year',start='2025-01-01',end='2025-12-31');doc['report_period']=period
    doc['availability'].update(local_resource_id='windows01-own',file_status='available',extraction_status='extracted')
    doc['rights'].update(note='Own original generated fixture; redistribution permitted. No project code license selected.',checked_on='2026-11-11')
    prov=dict(status='assistant_checked',method='Own fictional fixture; values and headers verified against generated PDF, not human reviewed.',human_reviewer=None)
    doc['provenance']=prov;cat['documents']=[doc];cat['facts']=[];cat['evidence']=[]
    for metric,value,label in [('revenue','120','Revenue'),('operating_profit','18','Operating profit')]:
        ev=dict(evidence_id=metric+'-own-ev',document_id=doc['document_id'],version_id=doc['version_id'],document_sha256=sha,locator=dict(kind='synthetic',record_id=metric+'-own',row_label=label,column_label='2025',unit_header='RUB million'),metric_id=metric,definition_id=next(m['definition_id'] for m in cat['metrics'] if m['metric_id']==metric),period=period,currency='RUB',scale=1000000,raw_value=value,numeric_encoding='decimal_string',provenance=prov)
        fact=dict(fact_id=metric+'-own',organization_id=doc['organization_id'],document_id=doc['document_id'],version_id=doc['version_id'],metric_id=metric,definition_id=ev['definition_id'],value=value,original_label=label,currency='RUB',scale=1000000,period=period,evidence_id=ev['evidence_id'],evidence_digest=digest(ev),provenance=prov,origin_role='reported_period')
        cat['evidence'].append(ev);cat['facts'].append(fact)
    dictionary=json.loads((ROOT/'data/dictionaries/kp3_finance_v1/definitions.json').read_text(encoding='utf8'))
    admission=dict(admission_version='1.0',context_id='windows01-own-admission',data_origin='synthetic',catalog_id=cat['catalog_id'],component_digests={k:digest(v) for k,v in dict(catalog=cat,dictionary=dictionary,bindings=None,checks=None).items()},resource_policy='required_for_real',comparability_records=[])
    manifest=dict(schema='windows01-demo-1',document_id=doc['document_id'],version_id=doc['version_id'],sha256=sha,page=1,page_size=[420,360],pdf_file=pdf.name,origin='own_original_generated_synthetic',redistribution='permitted_for_this_demo_only',generator_version='1',cells={'revenue-own':[300,174,340,198],'operating_profit-own':[300,150,340,174]})
    for name,obj in [('catalog',cat),('dictionary',dictionary),('admission',admission),('manifest',manifest)]:save(out/(name+'.json'),obj)
    print(json.dumps(dict(pdf_sha256=sha,pdf_bytes=pdf.stat().st_size,fixture_origin=manifest['origin'])))
if __name__=='__main__':generate(sys.argv[1])
