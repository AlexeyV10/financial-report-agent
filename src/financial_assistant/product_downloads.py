"""Selected own snapshots only, via explicit loopback attachment links; no arbitrary URL/path."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Lock,Thread
from .contracts_v2 import need

class HistoryDownloads:
    def __init__(self,store):self.store=store;self.selected=None;self.lock=Lock();self.server=None
    def select(self,key):
        self.store.load(key)
        with self.lock:self.selected=key
    def revoke(self):
        with self.lock:self.selected=None
    def start(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    segments=self.path.split('/');need(len(segments)==3 and segments[1]=='export','invalid_export_route')
                    key,extension=segments[2].rsplit('.',1);need(extension in {'json','md'},'invalid_export_kind')
                    with owner.lock:need(key==owner.selected,'export_not_selected')
                    data=owner.store.export(key,'json'if extension=='json'else'markdown')
                    self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8'if extension=='json'else'text/markdown; charset=utf-8')
                    self.send_header('Content-Length',str(len(data)));self.send_header('Content-Disposition','attachment; filename="run-'+key[:12]+'.'+extension+'"');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
                except Exception:self.send_error(404,'Selected own snapshot unavailable')
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);Thread(target=self.server.serve_forever,daemon=True).start();return self
    def url(self,key,kind):
        need(kind in {'json','md'}and self.server is not None,'invalid_export_kind');self.select(key)
        return 'http://127.0.0.1:'+str(self.server.server_port)+'/export/'+key+'.'+kind
    def close(self):
        if self.server:self.server.shutdown();self.server.server_close()
