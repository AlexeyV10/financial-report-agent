"""One parent-owned request per process; bounded UTF8 JSONL, no HTTP or model."""
import argparse, os, sys, time, json
from common import PROTOCOL, MAX_REQUEST, validate, decode
from adapter import DemoAdapter
from renderer import PdfiumRenderer
def main():
    sys.stdout.reconfigure(encoding='utf8',errors='strict')
    sys.stderr.reconfigure(encoding='utf8',errors='replace')
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True);args=parser.parse_args()
    q=None
    def emit(kind,**data):
        print(json.dumps(dict(protocol=PROTOCOL,job=q['job'] if q else None,type=kind,**data),ensure_ascii=False),flush=True)
    try:
        q=validate(decode(sys.stdin.buffer.readline(MAX_REQUEST+1),MAX_REQUEST))
        emit('progress',percent=5,text='Проверка собственного источника')
        adapter=DemoAdapter(args.workspace)
        if q['operation']=='crash':os._exit(23)
        if q['operation']=='slow':
            for i in range(40):time.sleep(.1);emit('progress',percent=5+i*2,text='Учебная фоновая задача: этап '+str(i+1)+' из 40')
        if q['operation'] in {'calculate','slow'}:data=dict(outcome=adapter.run(q['job']))
        else:data=PdfiumRenderer().render(adapter,q['zoom'],q['rotation'],q['dpi'])
        emit('done',**data)
    except Exception as exc:
        # No paths, document content or traceback on the GUI protocol.
        emit('error',code=getattr(exc,'code',None) or type(exc).__name__)
        return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
