"""Isolated optional PDF worker; reads ONLY a PDF and declarative extraction config."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.document_extraction import SCHEMA,ExtractionError,fingerprint,load_config,need,parse_region


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--config',type=Path,default=ROOT/'data/extraction/kp3_pdf_v1/config.json')
    args=parser.parse_args()
    try:
        need(args.output.resolve().is_relative_to((ROOT/'tmp').resolve()),'private_path_required')
        need(not args.output.exists(),'output_exists')
        cfg=load_config(args.config)
        import pdfplumber,pdfminer
        need(platform.python_version()==cfg['worker_python'] and pdfplumber.__version__==cfg['pdfplumber'] and pdfminer.__version__==cfg['pdfminer_six'],'worker_environment_mismatch')
        need(args.pdf.is_file(),'source_missing');need(args.pdf.stat().st_size<=cfg['max_pdf_bytes'],'source_too_large')
        with args.pdf.open('rb') as stream:data=stream.read(cfg['max_pdf_bytes']+1)
        need(len(data)<=cfg['max_pdf_bytes'],'source_too_large');need(data.startswith(b'%PDF-'),'source_not_pdf');sha=hashlib.sha256(data).hexdigest()
        pages=[]
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            need(0<len(pdf.pages)<=cfg['max_pages'],'unsupported_page_count')
            for i,page in enumerate(pdf.pages,1):
                x0,y0,x1,y1=page.bbox
                boxes=[('full_page',page.bbox)]
                if page.width/page.height>=cfg['spread_aspect_min']:
                    boxes=[('left_half_of_spread',(x0,y0,(x0+x1)/2,y1)),('right_half_of_spread',((x0+x1)/2,y0,x1,y1))]
                regions=[]
                for region_id,box in boxes:
                    crop=page.crop(box);words=crop.extract_words(x_tolerance=cfg['x_tolerance'],y_tolerance=cfg['y_tolerance'])
                    words=[w for w in words if w.get('upright',True)]
                    regions.append(parse_region(words,box,i,region_id,cfg))
                pages.append(dict(pdf_page=i,width=page.width,height=page.height,bbox=list(page.bbox),regions=regions));page.close()
        payload=dict(schema_version=SCHEMA,document_sha256=sha,byte_length=len(data),pdf_pages=len(pages),extractor_fingerprint=fingerprint(ROOT,cfg),config=cfg,environment=dict(python=platform.python_version(),pdfplumber=pdfplumber.__version__,pdfminer_six=pdfminer.__version__),origin='automatic_pdf_geometry_candidates',pages=pages)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as stream:stream.write(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(dict(status='extracted_candidates',sha256=sha,pages=len(pages),tables=sum(len(r['tables']) for p in pages for r in p['regions']),facts_admitted=0)))
        return 0
    except Exception as exc:
        # Worker boundary: even a PDF parser exception is a technical failure, never missing data.
        code=getattr(exc,'code','worker_dependency_missing' if isinstance(exc,ImportError) else 'output_exists' if isinstance(exc,FileExistsError) else 'pdf_worker_error')
        print(json.dumps(dict(status='error',reason_code=code,error_type=type(exc).__name__,detail=str(exc)[:500]),ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
