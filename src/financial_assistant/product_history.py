"""Private, atomic snapshots and durable duplicate suppression; no model or arithmetic."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,os,re
from pathlib import Path
from uuid import uuid4
from .contracts_v2 import need,digest,shape
from .service_contracts import validate_answer
from .agent_contracts_v2 import validate_agent_answer
from .one_shot_contracts import validate_one_shot_answer
from .scenario_contracts_v1 import validate_outcome

ROOT=Path(__file__).resolve().parents[2]
VERSION='kp3-history-0.1'
MAX_BYTES=8000000
VALIDATORS={'kp3-answer-0.1':validate_answer,'kp3-answer-0.2':validate_agent_answer,'kp3-a-answer-0.1':validate_one_shot_answer,'kp3-scenario-outcome-0.1':validate_outcome}

def _unique(pairs):
    out={}
    for k,v in pairs:
        need(k not in out,'duplicate_json_key');out[k]=v
    return out

def _bytes(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')

def validate_payload(p):
    shape(p,'kind source answers result');need(p['kind']in {'financial','scenario'},'history_kind_invalid')
    need(type(p['source'])is dict and type(p['answers'])is list,'history_input_invalid')
    r=p['result'];need(type(r)is dict and r.get('schema_version')in VALIDATORS,'history_schema_unsupported')
    need((p['kind']=='scenario')==(r['schema_version']=='kp3-scenario-outcome-0.1'),'history_kind_mismatch')
    VALIDATORS[r['schema_version']](r);need(len(_bytes(p))<=MAX_BYTES,'history_size_limit')

def escape_md(text):
    # No active markdown links/HTML supplied by a question, source label or model.
    return ''.join('\\'+c if c in '\\`*_{}[]()#+-.!<>|'else c for c in str(text)).replace('\r','').replace('\n','  \n')

def markdown(record):
    p=record['payload'];r=p['result'];fin=r.get('financial_result');scenario=p['kind']=='scenario'
    lines=['# Собственный сохранённый запуск',escape_md(record['record_id']),
           'Снимок истории: текущие источники заново не проверялись. Модель при открытии не вызывается.',
           'Время сохранения: '+escape_md(record['saved_at']),
           'Исход: '+escape_md(r.get('execution_status',r.get('status')))+' / '+escape_md(r.get('reason_code')),
           'Исходный вопрос: '+escape_md(r.get('original_question',p['source'].get('question','')))]
    if scenario:
        lines.extend([escape_md(r['label']),'Новых вызовов модели: '+str(r['model_calls'])])
        if r['scenario']:
            x=r['scenario'];lines+=['Капитал: '+escape_md(x['final_equity'])+' RUB; изменение: '+escape_md(x['pnl'])+' RUB',
                                   'Максимальная просадка: '+escape_md(x['max_drawdown']['percent'])+' %']
    elif fin:
        u=fin['result_unit'];lines+=['Результат: '+escape_md(fin['display_value'])+' '+escape_md(u),
                                   'Формула: '+escape_md(fin['formula']),'Округление: '+escape_md(fin['rounding'])]
        for x in fin['inputs']:lines+=['Вход: '+escape_md({k:x[k]for k in ['metric_id','value','source_unit','period','raw_value']})]
        for s in fin['sources']:lines+=['Источник: '+escape_md(s)]
    lines+=['Предпосылки и невыполненные требования: '+escape_md({k:r.get(k)for k in ['assumption_checks','unfulfilled_requests']}),
            'Расходы и происхождение: '+escape_md({k:r.get(k)for k in ['model_calls','agent','selection','context_digest']}),
            'Данные и trace (собственный JSON, без первичных страниц):', '```json',json.dumps(p,ensure_ascii=False,indent=2), '```']
    # The JSON code block cannot be terminated by an untrusted question.
    lines[-2]=lines[-2].replace('`','\\u0060').replace('<','\\u003c').replace('>','\\u003e')
    return '\n\n'.join(lines)+'\n'

class RunStore:
    def __init__(self,path):
        self.path=Path(path).resolve();need(self.path.is_relative_to((ROOT/'tmp').resolve())and self.path!=(ROOT/'tmp').resolve(),'private_history_dir_required')
        self.path.mkdir(parents=True,exist_ok=True)
    def _path(self,key,suffix):
        need(type(key)is str and re.fullmatch('[0-9a-f]{64}',key)is not None,'history_id_invalid')
        p=self.path/(key+suffix);need(not p.is_symlink(),'history_symlink_forbidden');return p
    def _read(self,p):
        need(p.is_file()and p.stat().st_size<=MAX_BYTES,'history_missing_or_limit')
        return json.loads(p.read_text(encoding='utf8'),object_pairs_hook=_unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite_json')))
    def _atomic(self,p,value):
        data=_bytes(value);need(len(data)<=MAX_BYTES,'history_size_limit');tmp=self.path/('pending-'+uuid4().hex+'.tmp')
        try:
            with tmp.open('xb')as f:f.write(data);f.flush();os.fsync(f.fileno())
            os.link(tmp,p) # atomic, exclusive link: a prior snapshot is never replaced
        finally:
            if tmp.exists():tmp.unlink()
    def key(self,intent,context,nonce=0):
        need(type(nonce)is int and 0<=nonce<2**64,'history_nonce_invalid')
        return digest(dict(intent=intent,context=context,nonce=nonce))
    def load(self,key):
        r=self._read(self._path(key,'.json'));shape(r,'schema_version record_id saved_at context_digest payload payload_sha256')
        need(r['schema_version']==VERSION and r['record_id']==key,'history_record_mismatch');need(digest(r['payload'])==r['payload_sha256'],'history_hash_mismatch');validate_payload(r['payload']);return r
    def run(self,intent,context,producer,nonce=0):
        key=self.key(intent,context,nonce)
        if self._path(key,'.json').exists():return self.load(key),True
        claim=self._path(key,'.claim')
        try:
            with claim.open('x',encoding='utf8')as f:json.dump(dict(schema_version=VERSION,started_at=datetime.now(timezone.utc).isoformat()),f)
        except FileExistsError:
            if self._path(key,'.json').exists():return self.load(key),True
            raise ValueError('run_in_progress_or_interrupted_choose_new_run')
        payload=producer('product13-'+digest(dict(record=key,store=str(self.path)))[:32]);validate_payload(payload)
        r=dict(schema_version=VERSION,record_id=key,saved_at=datetime.now(timezone.utc).isoformat(),context_digest=context,payload=deepcopy(payload),payload_sha256=digest(payload))
        self._atomic(self._path(key,'.json'),r);return r,False
    def listing(self):
        rows=[]
        for p in self.path.glob('*.json'):
            try:
                r=self.load(p.stem);x=r['payload']['result'];rows.append(dict(record_id=p.stem,saved_at=r['saved_at'],kind=r['payload']['kind'],method=x.get('method','scenario'),status=x.get('execution_status',x.get('status'))))
            except Exception:rows.append(dict(record_id=p.stem,saved_at='',kind='invalid',method='',status='damaged'))
        return sorted(rows,key=lambda x:x['saved_at'],reverse=True)
    def export(self,key,kind):
        r=self.load(key);need(kind in {'json','markdown'},'history_export_invalid')
        return _bytes(r)if kind=='json'else markdown(r).encode('utf8')
