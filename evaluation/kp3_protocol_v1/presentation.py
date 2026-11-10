"""Strict independent grammar for the fixed product13 Markdown, not arbitrary narrative QA."""
import json
from .common import exact,require,digest

def escaped(value):return ''.join('\\'+x if x in '\\`*_{}[]()#+-.!<>|'else x for x in str(value)).replace('\r','').replace('\n','  \n')

def audit_markdown(text,record):
    try:
        exact(record,'schema_version record_id saved_at context_digest payload payload_sha256');require(record['schema_version']=='kp3-history-0.1'and digest(record['payload'])==record['payload_sha256'],'record_integrity_error');require(type(text)is str and len(text.encode())<=8000000,'presentation_limit')
        parts=text.split('```json\n\n');require(len(parts)==2,'unrecognized_presentation_grammar');body,ending=parts[1].rsplit('\n\n```',1);require(ending=='\n'and '```'not in body,'injected_code_fence');p=json.loads(body);require(p==record['payload'],'embedded_json_changed');r=p['result'];fin=r.get('financial_result');scenario=p['kind']=='scenario'
        lines=['# Собственный сохранённый запуск',escaped(record['record_id']),'Снимок истории: текущие источники заново не проверялись. Модель при открытии не вызывается.','Время сохранения: '+escaped(record['saved_at']),'Исход: '+escaped(r.get('execution_status',r.get('status')))+' / '+escaped(r.get('reason_code')),'Исходный вопрос: '+escaped(r.get('original_question',p['source'].get('question','')))]
        if scenario:
            lines.extend([escaped(r['label']),'Новых вызовов модели: '+str(r['model_calls'])])
            if r['scenario']:
                s=r['scenario'];lines.extend(['Капитал: '+escaped(s['final_equity'])+' RUB; изменение: '+escaped(s['pnl'])+' RUB','Максимальная просадка: '+escaped(s['max_drawdown']['percent'])+' %'])
        elif fin:
            lines.extend(['Результат: '+escaped(fin['display_value'])+' '+escaped(fin['result_unit']),'Формула: '+escaped(fin['formula']),'Округление: '+escaped(fin['rounding'])])
            for x in fin['inputs']:lines.append('Вход: '+escaped({k:x[k]for k in ['metric_id','value','source_unit','period','raw_value']}))
            for s in fin['sources']:lines.append('Источник: '+escaped(s))
        lines.extend(['Предпосылки и невыполненные требования: '+escaped({k:r.get(k)for k in ['assumption_checks','unfulfilled_requests']}),'Расходы и происхождение: '+escaped({k:r.get(k)for k in ['model_calls','agent','selection','context_digest']}),'Данные и trace (собственный JSON, без первичных страниц):'])
        require(parts[0]=='\n\n'.join(lines)+'\n\n','extra_missing_or_changed_human_claim');return dict(status='checked',matched=True,errors=[])
    except (ValueError,KeyError,TypeError)as e:return dict(status='unsupported_or_invalid_representation',matched=False,errors=[str(e)])
