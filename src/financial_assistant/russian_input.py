"""Bounded Russian keyword/date grammar v1. No LLM, executable text or Fact values."""
from calendar import monthrange
from copy import deepcopy
import re
import unicodedata
from .catalog import validate_catalog
from .contracts_v2 import boundary,digest,need,shape
from .input_contracts import FORM_SCHEMA,new_input,validate_assumptions,validate_fields,validate_input

LANGUAGE_VERSION='ru-input-v1'
MORPH={'сегежи':'сегежа','сегежу':'сегежа','сегежей':'сегежа','фосагры':'фосагро'}
ALIAS_EXPANSIONS={'segezha group':['segezha']}
METRICS={'revenue':r'\bвыручк[а-я]*\b','operating_profit':r'\bоперационн[а-я]*\s+прибыл[а-я]*\b','operating_cash_flow':r'\bcfo\b|\b(?:чист[а-я]*\s+)?денежн[а-я]*\s+поток[а-я]*\s+от\s+операционн[а-я]*\s+деятельност[а-я]*\b|\bоперационн[а-я]*\s+денежн[а-я]*\s+поток[а-я]*\b'}
DIRECTIONS={'increase':r'вырос[а-я]*|возрос[а-я]*|увеличил[а-я]*','decrease':r'снизил[а-я]*|снизи[а-я]*|упал[а-я]*|уменьшил[а-я]*','unchanged':r'не\s+измени[а-я]*|остал[а-я]*\s+неизменн[а-я]*'}


def normalize(s):
    s=' '.join(unicodedata.normalize('NFKC',s).casefold().replace('ё','е').split())
    return re.sub(r'\b[а-я]+\b',lambda m:MORPH.get(m[0],m[0]),s)


def aliases_for(org):
    aliases={normalize(org['name']),*(normalize(a)for a in org['aliases'])}
    for canonical,forms in ALIAS_EXPANSIONS.items():
        if canonical in aliases:aliases.update(forms)
    return aliases


def organizations(catalog,query):
    q=normalize(query);return [o for o in catalog['organizations']if q in {normalize(o['organization_id']),*aliases_for(o)}]


def duration(year,kind='full_year',n=None):
    y=int(year)
    if kind=='quarter':start=(int(n)-1)*3+1;end=start+2
    else:start=1;end=int(n)if n else 12
    return dict(kind='duration',duration_type=kind,start=f'{y:04d}-{start:02d}-01',end=f'{y:04d}-{end:02d}-{monthrange(y,end)[1]:02d}')


def _set(t,k,v,origin='text'):
    t['fields'][k]=deepcopy(v);t['field_origins'][k]=origin


def _issue(t,field,code,message):t['issues'].append(dict(field=field,code=code,message=message))


@boundary
def parse_text(question,catalog,input_id='input-task'):
    validate_catalog(catalog);t=new_input(input_id,question,'text',digest(catalog),LANGUAGE_VERSION);q=normalize(question)
    if re.search(r'игнорируй|выполни\s+(?:код|команд)|возьми\s+\d|__import__|\beval\s*\(|\bexec\s*\(|https?://|powershell|cmd\s*/',q):t['unsupported_reasons'].append('untrusted_instruction')
    if re.search(r'ebitda|fcf|capex|дивиденд|чист[а-я]*\s+прибыл|процентн[а-я]*\s+доход|комиссионн[а-я]*\s+доход|поступлен[а-я]*\s+от\s+покупател',q):t['unsupported_reasons'].append('unsupported_metric')
    if re.search(r'\bбанк[а-я]*\b|страхов[а-я]*\s+компани|\bgaap\b',q):t['unsupported_reasons'].append('financial_or_other_standard_not_supported')
    if re.search(r'процентн[а-я]*\s+пункт|п\.?\s*п\.',q):t['unsupported_reasons'].append('percentage_point_operation_not_registered')
    if re.search(r'перевед[а-я]*.*(?:доллар|евро)|курс[а-я]*\s+валют|\bfx\b',q):t['unsupported_reasons'].append('currency_conversion_not_supported')
    found=[]
    for o in catalog['organizations']:
        aliases=aliases_for(o)
        if any(re.search(r'(?<!\w)'+re.escape(a)+r'(?!\w)',q)for a in aliases):found.append(o)
    if len(found)==1:_set(t,'organization',found[0]['organization_id'])
    elif len(found)>1:_issue(t,'organization','ambiguous_organization','Указано несколько организаций; выберите одну.')
    else:
        unknown=re.search(r'\b(?:компани[яи]|групп[аы]|у)\s+[«\"]?([а-яa-z][а-яa-z-]+)',q)
        if unknown:t['hints']['organization_unmatched']=unknown[1]
        _issue(t,'organization','unknown_organization'if unknown else 'missing_organization','Выберите организацию из каталога; совпадение имени не установлено.')
    if re.search(r'консолидирован|\bгрупп[а-я]*\b',q):_set(t,'consolidation','group')
    if re.search(r'юрлиц|отдельн[а-я]*\s+компани',q):_set(t,'consolidation','legal_entity')
    if re.search(r'мсфо|\bifrs\b',q):_set(t,'accounting_standard','IFRS')
    if re.search(r'рсбу|\bras\b',q):_set(t,'accounting_standard','RAS')
    margin=bool(re.search(r'операционн[а-я]*\s+марж[а-я]*',q));mids=[m for m,p in METRICS.items()if re.search(p,q)]
    if margin:
        if 'operating_cash_flow'in mids:t['unsupported_reasons'].append('multiple_metrics_not_supported')
        mids=['operating_profit','revenue']
    if mids:_set(t,'metric_ids',mids)
    # Preserve an asserted direction, including a request for causal explanation, before operation mapping.
    directions=[(k,re.search(p,q))for k,p in DIRECTIONS.items()if re.search(p,q)]
    if re.search(r'не\s+(?:снизи|упал|вырос|увеличил)',q):t['unsupported_reasons'].append('negated_direction_not_supported');directions=[]
    if len(directions)==1:
        direction= directions[0][0]
        # Full original wording is retained as the premise fragment, not synthesized by the parser.
        t['assumptions']=[dict(kind='direction',asserted_direction=direction,text_fragment=question,requires_check=True,why_requested='почему'in q)]
        t['assumption_origin']='text'
        if 'почему'in q:t['unfulfilled_requests'].append('causal_explanation_not_supported')
    elif len(directions)>1:t['unsupported_reasons'].append('ambiguous_direction')
    rel=bool(re.search(r'на\s+сколько\s+процент|темп[а-я]*\s+рост|относительн|процентн[а-я]*\s+(?:изменен|рост)|\bрост\b.*%',q))
    absolute=bool(re.search(r'абсолютн|разниц[а-я]*|разност[а-я]*|на\s+сколько\s+(?:рубл|млн|млрд|тыс)',q))
    changed=bool(re.search(r'измен[а-я]*|вырос[а-я]*|снизи[а-я]*|упал[а-я]*|уменьшил[а-я]*|увеличил[а-я]*|рост[а-я]*|на\s*сколько',q))
    both=rel and (absolute or bool(re.search(r'на\s+сколько\s+и\s+на\s+сколько',q)))
    scale_matches=list(re.finditer(r'\bв\s+(млрд|миллиард[а-я]*|млн|миллион[а-я]*|тыс\.?|тысяч[а-я]*|рубл[а-я]*)',q));scale_match=scale_matches[0]if scale_matches else None
    scale=None
    if scale_match:
        s=scale_match[1];scale=1000000000 if s.startswith(('млрд','миллиард'))else 1000000 if s.startswith(('млн','миллион'))else 1000 if s.startswith(('тыс','тысяч'))else 1
        currency='USD'if re.search(r'доллар|\busd\b',q)else 'RUB'if re.search(r'рубл|\brub\b',q)else None
        if len(scale_matches)>1:_issue(t,'result_unit','ambiguous_target_unit','Указано несколько представлений суммы; выберите одно.')
        elif currency:_set(t,'result_unit',dict(kind='amount',currency=currency,scale=scale))
        else:_issue(t,'result_unit','currency_required','Укажите валюту суммы вместе с масштабом.')
    operation=None
    if both:_issue(t,'operation_id','multiple_operations','Запрошены два действия; выберите одно для этого запроса.');t['unfulfilled_requests'].append('multiple_operations_require_explicit_selection')
    elif margin:
        operation='operating_margin_v1'
        if changed:t['unsupported_reasons'].append('margin_change_not_registered')
    elif rel:operation='relative_change_v1'
    elif absolute:operation='absolute_change_v1'
    elif t['assumptions'] and re.search(r'правда\s+ли|верно\s+ли|почему|действительно',q):operation='absolute_change_v1'
    elif changed:_issue(t,'operation_id','ambiguous_change','Нужно абсолютное изменение или относительное изменение в процентах?')
    elif mids and re.search(r'кака[яи]|каков|сколько|покаж|найд|значени|сумм',q):operation='scale_v1'if scale is not None else 'direct_fact_v1'
    else:t['unsupported_reasons'].append('intent_not_recognized')
    if operation:
        _set(t,'operation_id',operation)
        if operation not in {'relative_change_v1','operating_margin_v1'}and re.search(r'в\s+процент|%',q):t['unsupported_reasons'].append('amount_percent_unit_conflict')
        if operation in {'relative_change_v1','operating_margin_v1'}:
            if scale is not None:t['unsupported_reasons'].append('percent_amount_unit_conflict')
            else:_set(t,'result_unit',dict(kind='percent'))
    if len(mids)>1 and not margin:t['unsupported_reasons'].append('multiple_metrics_not_supported')
    # Dates of knowledge are masked before reporting years are parsed.
    dated=re.search(r'(?:по\s+состоянию\s+на|на\s+дату|известно\s+на|на)\s+(\d{4}-\d{2}-\d{2}(?:t\d{2}:\d{2}:\d{2}(?:z|[+-]\d{2}:\d{2}))?|\d{2}\.\d{2}\.\d{4})',q)
    clean=q
    if dated:
        _set(t,'mode','historical');t['hints']['as_of_text']=dated[1];clean=q[:dated.start()]+ ' '+q[dated.end():]
        if 't'in dated[1]:_set(t,'as_of',dated[1].replace('t','T').replace('z','Z'))
        else:_issue(t,'as_of','as_of_time_zone_required','Укажите момент с временем и UTC-смещением; дата не заменяет as_of.')
    elif re.search(r'historical|историческ|на\s+дату|что\s+было\s+известно',q):_set(t,'mode','historical')
    elif re.search(r'snapshot|снимок',q):_set(t,'mode','snapshot')
    if re.search(r'snapshot|снимок',q)and (dated or re.search(r'historical|историческ|на\s+дату',q)):t['unsupported_reasons'].append('conflicting_mode')
    # Source report year is not a requested financial period.
    source=re.search(r'из\s+(?:годового\s+)?отчет[а-я]*\s+за\s+(20\d{2})\s*год[а-я]*',clean)
    if len(re.findall(r'из\s+(?:годового\s+)?отчет[а-я]*\s+за\s+20\d{2}',clean))>1:t['unsupported_reasons'].append('multiple_source_reports')
    if source:
        t['hints']['document_report_year']=int(source[1]);clean=clean[:source.start()]+' '+clean[source.end():];_set(t,'version_policy','explicit_versions')
    mentioned=re.findall(r'\bдокумент\s+([a-z0-9][a-z0-9_.:-]*)',q)
    docs={d['document_id']:d for d in catalog['documents']};recognized=[]
    for token in mentioned:
        did=token if token in docs else token.rstrip('.,:;')
        if did not in docs:t['unsupported_reasons'].append('unknown_document_id')
        else:recognized.append(docs[did]);clean=clean.replace(token,' ')
    if len(recognized)>1:t['unsupported_reasons'].append('multiple_document_mentions')
    elif recognized:
        d=recognized[0];_set(t,'documents',[dict(document_id=d['document_id'],version_id=d['version_id'])]);_set(t,'version_policy','explicit_versions')
    if re.search(r'исходн[а-я]*\s+отчет|первоначальн[а-я]*\s+верси',q):_set(t,'version_policy','original_period_documents')
    if re.search(r'явн[а-я]*\s+верси|сравнительн[а-я]*\s+колон',q):_set(t,'version_policy','explicit_versions')
    if re.search(r'исходн[а-я]*\s+отчет|первоначальн[а-я]*\s+верси',q)and re.search(r'сравнительн[а-я]*\s+колон',q):t['unsupported_reasons'].append('conflicting_version_policy')
    years=re.findall(r'\b20\d{2}\b',clean);t['hints']['years']=list(dict.fromkeys(int(y)for y in years))
    quarter=re.search(r'\b(1|2|3|4|i|ii|iii|iv|перв[а-я]*|втор[а-я]*|трет[а-я]*|четверт[а-я]*)\s+квартал',clean)
    qnumber=None
    if quarter:
        x=quarter[1];qnumber=int(x)if x.isdigit()else {'i':1,'ii':2,'iii':3,'iv':4}.get(x)or next(n for stem,n in [('перв',1),('втор',2),('трет',3),('четверт',4)]if x.startswith(stem))
    months=re.search(r'\b(3|6|9)\s*месяц',clean)
    half=bool(re.search(r'перв[а-я]*\s+полугод|1\s+полугод',clean))
    if len(re.findall(r'\b(?:[1-4]|i{1,3}|iv|перв[а-я]*|втор[а-я]*|трет[а-я]*|четверт[а-я]*)\s+квартал',clean))>1 or len(re.findall(r'\b[369]\s*месяц',clean))>1 or (quarter and (months or half))or((quarter or months or half)and re.search(r'за\s+20\d{2}\s+год',clean)):t['unsupported_reasons'].append('mixed_period_grammar')
    if len(years)in {1,2} and len(set(years))==len(years):
        if qnumber:_set(t,'periods',[duration(y,'quarter',qnumber)for y in years])
        elif months or half:_set(t,'periods',[duration(y,'year_to_date',months[1]if months else 6)for y in years])
        elif re.search(r'полны[а-я]*\s+год|\bгод[а-я]*\b',clean):_set(t,'periods',[duration(y)for y in years])
    if t['fields']['periods']is None:_issue(t,'periods','incomplete_period','Нужны полный период и тип окна: год, накопленные месяцы или отдельный квартал.')
    validate_input(t);return t


@boundary
def parse_form(form,catalog):
    validate_catalog(catalog);shape(form,'schema_version input_id original_question fields assumptions');need(form['schema_version']==FORM_SCHEMA,'unsupported_form_version');validate_fields(form['fields'],partial=True);validate_assumptions(form['assumptions'],form['original_question'])
    t=new_input(form['input_id'],form['original_question'],'form',digest(catalog),LANGUAGE_VERSION)
    t['raw_fields']=deepcopy(form['fields'])
    for k,v in form['fields'].items():
        if v is not None:_set(t,k,v,'form')
    detected=parse_text(form['original_question'],catalog,form['input_id'])
    # Structured choices cannot silently contradict an explicit understood part of the wording.
    for k in ['operation_id','metric_ids','periods','consolidation','accounting_standard','mode','as_of','result_unit']:
        if t['fields'][k]is not None and detected['fields'][k]is not None:need(t['fields'][k]==detected['fields'][k],'question_form_conflict')
    if detected['fields']['organization']and t['fields']['organization']:
        need(any(o['organization_id']==detected['fields']['organization']for o in organizations(catalog,t['fields']['organization'])),'question_form_conflict')
    t['hints']['document_report_year']=detected['hints']['document_report_year']
    t['unsupported_reasons']=[x for x in detected['unsupported_reasons']if x not in {'intent_not_recognized'}]
    t['assumptions']=deepcopy(form['assumptions']);t['assumption_origin']='form'if t['assumptions']else 'none'
    if detected['assumptions']:
        if t['assumptions']:
            need(all(any(a['asserted_direction']==b['asserted_direction']and(not b['why_requested']or a['why_requested'])for a in t['assumptions'])for b in detected['assumptions']),'assumption_conflict')
        else:t['assumptions']=deepcopy(detected['assumptions']);t['assumption_origin']='text'
    t['unfulfilled_requests']=deepcopy(detected['unfulfilled_requests'])
    if any(a['why_requested']for a in t['assumptions'])and 'causal_explanation_not_supported'not in t['unfulfilled_requests']:t['unfulfilled_requests'].append('causal_explanation_not_supported')
    validate_input(t);return t
