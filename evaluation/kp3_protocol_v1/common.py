"""Strict local data, deterministic hashing; no production, network or executable payloads."""
import hashlib,json,re
from pathlib import Path

class ProtocolError(ValueError):pass
def require(ok,reason):
    if not ok:raise ProtocolError(reason)
def exact(value,keys):require(type(value)is dict and set(value)==set(keys.split()),'fields_mismatch')
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
def file_sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        while block:=f.read(1024*1024):h.update(block)
    return h.hexdigest()
def ident(s):require(type(s)is str and re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,199}',s)is not None,'invalid_id')
def read(path,limit=8000000):
    p=Path(path);require(p.is_file()and p.stat().st_size<=limit,'missing_or_oversized_file')
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'duplicate_json_key');out[k]=v
        return out
    def constant(s):raise ProtocolError('nonfinite_json')
    return json.loads(p.read_text(encoding='utf8'),object_pairs_hook=pairs,parse_constant=constant)
def write_new(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf8',newline='\n')as f:f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
