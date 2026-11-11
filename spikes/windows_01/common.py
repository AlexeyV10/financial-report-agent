"""Small feasibility contract, not the future WIN-05 service."""
import json, re
PROTOCOL='windows01-1'
MAX_REQUEST=8192
MAX_RESPONSE=2_000_000
def unique(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise ValueError('duplicate_key')
        d[k]=v
    return d
def decode(line,limit=MAX_RESPONSE):
    if len(line)>limit:raise ValueError('frame_too_large')
    return json.loads(line.decode('utf8'),object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite')))
def request(job,operation,zoom=1.0,rotation=0,dpi=1.0):
    return dict(protocol=PROTOCOL,job=job,operation=operation,zoom=zoom,rotation=rotation,dpi=dpi)
def validate(q):
    if not isinstance(q,dict) or set(q)!={'protocol','job','operation','zoom','rotation','dpi'}:raise ValueError('schema')
    if q['protocol']!=PROTOCOL or not isinstance(q['job'],str) or not re.fullmatch('[a-zA-Z0-9-]{1,64}',q['job']):raise ValueError('identity')
    if q['operation'] not in {'calculate','render','slow','crash'}:raise ValueError('operation')
    if type(q['rotation']) is not int or q['rotation'] not in {0,90,180,270}:raise ValueError('rotation')
    for key in ['zoom','dpi']:
        if type(q[key]) not in {int,float} or not .5<=q[key]<=2:raise ValueError(key)
    return q
def pixel_rect(rect,width,height,rotation,scale):
    def point(x,y):
        a,b=x,height-y
        if rotation==90:a,b=height-b,a
        elif rotation==180:a,b=width-a,height-b
        elif rotation==270:a,b=b,width-a
        return a*scale,b*scale
    pts=[point(x,y) for x in [rect[0],rect[2]] for y in [rect[1],rect[3]]]
    return [min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)]
class CurrentJob:
    """A terminal/cancelled or replaced generation cannot publish a late result."""
    def __init__(self):self.current=None;self.state='idle'
    def start(self,job):self.current=job;self.state='running'
    def cancel(self):self.current=None;self.state='cancelled'
    def accept(self,event):
        if self.state!='running' or event.get('protocol')!=PROTOCOL or event.get('job')!=self.current:return False
        if event.get('type') in {'done','error'}:self.state=event['type']
        return True
