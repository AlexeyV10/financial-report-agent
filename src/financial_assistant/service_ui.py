"""Presentation/state only. Financial values already formatted by the registered calculator."""
from copy import deepcopy
from .contracts_v2 import digest,need

OP_LABELS={'direct_fact_v1':'Значение показателя','absolute_change_v1':'Абсолютное изменение','relative_change_v1':'Изменение в процентах','scale_v1':'Сумма в другом масштабе','operating_margin_v1':'Операционная маржа'}
METRIC_LABELS={'revenue':'Выручка','operating_profit':'Операционная прибыль','operating_cash_flow':'Чистый денежный поток от операционной деятельности'}


def period_label(p):return p.get('date')if p['kind']=='instant'else p['start']+' — '+p['end']+' ('+dict(full_year='полный год',quarter='квартал',year_to_date='накопленный период',custom='особый период')[p['duration_type']]+')'


def value_label(result):
    u=result['result_unit']
    label='%'if u['kind']=='percent'else {1:'',1000:'тыс.',1000000:'млн',1000000000:'млрд'}[u['scale']]+' '+('руб.'if u['currency']=='RUB'else u['currency'])
    return result['display_value']+' '+label.strip()


class ViewState:
    def __init__(self):self.fingerprint=None;self.answer=None;self.answers=[]
    def select(self,source,context_identity):
        fp=digest(dict(source=source,context=context_identity))
        changed=fp!=self.fingerprint
        if changed:self.fingerprint=fp;self.answer=None;self.answers=[]
        return changed
    def accept(self,answer,source,context_identity,answers):
        need(self.fingerprint==digest(dict(source=source,context=context_identity)),'view_context_changed')
        need(answer['context_digest']==context_identity and answer['source_input_digest']==digest(dict(source=source,answers=answers)),'view_answer_mismatch')
        self.answer=deepcopy(answer);self.answers=deepcopy(answers)
