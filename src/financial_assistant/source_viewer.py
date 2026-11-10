"""Loopback-only exact-PDF viewer. No arbitrary paths, remote URLs, downloads or source copying."""
import hashlib,os,shutil,subprocess
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Lock,Thread
from urllib.parse import quote,urlsplit,unquote
from uuid import uuid4
from .contracts_v2 import ContractError,need

ROOT=Path(__file__).resolve().parents[2]


class SourceViewer:
    def __init__(self,calculation):
        self.calculation=calculation;self.allowed={};self.lock=Lock();self.server=None;self.render_cache={}
    def revoke(self):
        with self.lock:self.allowed={}
    def register(self,answer):
        self.revoke()
        if answer['financial_status']=='answered':
            with self.lock:self.allowed={s['document_id']:s['version_id']for s in answer['financial_result']['sources']if s['data_origin']=='real'}
    def checked_bytes(self,document_id,version_id):
        with self.lock:need(self.allowed.get(document_id)==version_id,'source_not_selected')
        self.calculation.validate();docs={d['document_id']:d for d in self.calculation.catalog['documents']};need(document_id in docs,'unknown_document_id');d=docs[document_id]
        need(d['version_id']==version_id and d['data_origin']=='real','source_version_mismatch')
        p=Path(self.calculation.resources[d['availability']['local_resource_id']]);need(p.stat().st_size==d['byte_length']and p.stat().st_size<=50000000,'source_version_mismatch');data=p.read_bytes()
        need(data.startswith(b'%PDF-')and len(data)==d['byte_length']and hashlib.sha256(data).hexdigest()==d['sha256'],'source_version_mismatch');return data
    def checked_page(self,document_id,version_id,page):
        self.checked_bytes(document_id,version_id)
        d=next(d for d in self.calculation.catalog['documents']if d['document_id']==document_id)
        need(type(page)is int and 1<=page<=d['pdf_pages'],'invalid_source_page')
        cache=ROOT/'tmp/source-pages'/d['sha256'];cache.mkdir(parents=True,exist_ok=True);key=(d['sha256'],page)
        with self.lock:
            if key not in self.render_cache:
                output=cache/('page-'+str(page)+'-'+uuid4().hex+'.png')
                renderer=shutil.which('pdftoppm');need(renderer is not None,'local_renderer_unavailable')
                source=self.calculation.resources[d['availability']['local_resource_id']]
                subprocess.run([renderer,'-f',str(page),'-l',str(page),'-r','110','-singlefile','-png',source,str(output.with_suffix(''))],check=True,timeout=45,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)if os.name=='nt'else 0)
                self.render_cache[key]=(output,hashlib.sha256(output.read_bytes()).hexdigest())
            output,expected=self.render_cache[key]
        self.checked_bytes(document_id,version_id);data=output.read_bytes();need(data.startswith(b'\x89PNG\r\n\x1a\n')and hashlib.sha256(data).hexdigest()==expected,'source_render_invalid');return data
    def start(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    parts=urlsplit(self.path);need(not parts.query,'invalid_source_route');segments=parts.path.split('/');need(len(segments)in {4,5},'invalid_source_route')
                    if len(segments)==4 and segments[1]=='source':data=owner.checked_bytes(unquote(segments[2]),unquote(segments[3]));mime='application/pdf'
                    else:
                        need(len(segments)==5 and segments[1]=='page'and segments[4].isdigit(),'invalid_source_route');data=owner.checked_page(unquote(segments[2]),unquote(segments[3]),int(segments[4]));mime='image/png'
                    self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('Content-Disposition','inline');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
                except (ContractError,OSError,KeyError,subprocess.SubprocessError):self.send_error(404,'Selected exact source unavailable')
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);Thread(target=self.server.serve_forever,daemon=True).start();return self
    def url(self,document_id,version_id,page):
        need(self.server is not None and type(page)is int and page>0,'invalid_viewer_link')
        return 'http://127.0.0.1:'+str(self.server.server_port)+'/page/'+quote(document_id,safe='')+'/'+quote(version_id,safe='')+'/'+str(page)
    def close(self):
        if self.server:self.server.shutdown();self.server.server_close()
