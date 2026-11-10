"""Human labels and explicit UI selections only. No financial calculation or new admission."""
from copy import deepcopy
from datetime import date
from .input_contracts import validate_fields

METHODS={'B':'Поиск и расчёт без модели','A':'Один выбор модели','C':'Агент с инструментами'}
OPERATIONS={'direct_fact_v1':'Найти значение в отчёте','relative_change_v1':'Сравнить — изменение в процентах','absolute_change_v1':'Сравнить — разница в рублях','scale_v1':'Показать в других единицах','operating_margin_v1':'Рассчитать операционную маржу'}
METRICS={'revenue':'Выручка','operating_profit':'Операционная прибыль','operating_cash_flow':'Денежный поток от операций'}
GENITIVE={'revenue':'выручки','operating_profit':'операционной прибыли','operating_cash_flow':'денежного потока от операций'}
FIELDS={'organization':'Компания','operation_id':'Что рассчитать','metric_ids':'Показатель','definition_ids':'Определение показателя','periods':'Периоды','documents':'Версия отчёта','version_policy':'Какие версии использовать','mode':'По каким данным анализировать','as_of':'Дата и время анализа','source_unit':'Единицы исходных данных','result_unit':'Единицы результата','comparability_id':'Сопоставимость отчётов','accounting_standard':'Стандарт отчётности','consolidation':'Группа или отдельная компания'}
REASONS={
 'missing_organization':'Выберите компанию или укажите её в вопросе.',
 'unknown_organization':'Эта компания не найдена в подготовленном каталоге.',
 'question_form_conflict':'Выбор в форме противоречит вопросу. Исправьте вопрос или выбранные условия.',
 'clarification_conflict':'Новое уточнение противоречит уже заданным условиям. Измените исходный запрос.',
 'no_compatible_fact':'В подготовленных данных нет подходящего набора. Это не означает, что строки нет в самом отчёте.',
 'publication_unknown':'Дата публикации точной версии отчёта не подтверждена. Ответ на историческую дату недоступен.',
 'not_yet_available':'На выбранный момент источник ещё не был доступен.',
 'source_missing':'Не найден зарегистрированный файл отчёта. Проверьте его в разделе «Документы».',
 'source_version_mismatch':'Файл отличается от проверенной версии. Нужен исходный зарегистрированный отчёт.',
 'index_missing':'Поиск ещё не подготовлен. Проверьте готовность в разделе «Документы».',
 'index_hash_mismatch':'Поисковые данные изменились. Нужна проверка подготовки.',
 'context_artifact_changed':'Изменились данные или настройки проверки. Расчёт остановлен.',
 'service_context_changed':'Изменился контекст проверки. Расчёт остановлен.',
 'adapter_unavailable':'Локальная модель не запущена. Можно явно выбрать «Поиск и расчёт без модели» и выполнить новый запрос.',
 'model_unavailable':'Локальная модель недоступна. Выберите другой способ анализа или проверьте её запуск.',
 'scope_not_supported':'Поддерживается отчётность нефинансовой группы по МСФО. Этот запрос выходит за её границы.',
 'unsupported_operation':'Такой расчёт пока не поддерживается.',
 'unsupported_metric':'Этот показатель пока не поддерживается.',
 'nonpositive_base':'Изменение в процентах рассчитывается только при положительном базовом значении.',
 'zero_denominator':'Для маржи нужна ненулевая выручка.',
 'negative_revenue':'Маржа при отрицательной выручке не рассчитывается выбранным методом.',
 'comparability_unproven':'Сопоставимость разных отчётов не доказана. Выберите подходящие периоды одной версии или уточните запрос.',
 'incompatible_units':'Единицы исходных данных несовместимы.',
 'incompatible_periods':'Периоды несовместимы. Выберите полные сопоставимые окна.',
 'ambiguous_change':'Уточните, нужно изменение в рублях или в процентах.',
 'unverified_candidate':'Найдены только непроверенные кандидаты. Они не допускаются к расчёту.',
 'run_in_progress_or_interrupted_choose_new_run':'Предыдущая попытка ещё идёт или была прервана. Автоматического повтора нет. Для новой попытки нажмите «Рассчитать ещё раз».',
 'call_limit':'Достигнут лимит действий модели. Финансового ответа нет.',
 'timeout':'Превышено время ожидания. Финансового ответа нет.',
 'total_timeout':'Превышен общий лимит времени. Финансового ответа нет.',
 'invalid_capital':'Начальный капитал должен быть положительной суммой в рублях.',
 'real_prices_unavailable':'Нет допустимых реальных цен.',
 'real_calendar_unavailable':'Нет проверенного торгового календаря.',
 'corporate_actions_unchecked':'Не проверены корпоративные события.',
 'price_rights_unconfirmed':'Не подтверждены права на данные цен.',
 'real_execution_not_supported':'Реальное исполнение сделок не поддерживается.',
 'price_missing':'Не хватает цены для выбранного момента. Последняя известная цена не подставляется.',
 'no_future_session_open':'После выбранного момента нет допустимого открытия торговой сессии.',
 'insufficient_exit_cash':'Не хватает денег на расходы при выходе. Сценарий остановлен.'}


def reason(code):return REASONS.get(code,'Запрос остановлен проверкой. Подробная причина доступна в диагностике.')


def number(text):
    """Group a canonical decimal STRING without rounding, scaling or float conversion."""
    value=str(text);sign=''
    if value.startswith(('-', '+')):sign,value=value[0],value[1:]
    parts=value.split('.')
    if len(parts)>2 or not all(p.isdigit()for p in parts):return str(text)
    groups=[parts[0][max(0,i-3):i]for i in range(len(parts[0]),0,-3)]
    grouped='\u00a0'.join(reversed(groups))
    return sign+grouped+(','+parts[1]if len(parts)==2 else'')


def unit_label(unit):
    if unit.get('kind')=='percent':return '%'
    if unit.get('kind')=='percentage_point':return 'п. п.'
    currency='₽'if unit.get('currency')=='RUB'else unit.get('currency','')
    return ({1:'',1000:'тыс. ',1000000:'млн ',1000000000:'млрд '}.get(unit.get('scale'),str(unit.get('scale'))+' × ')+currency).strip()


def period_label(period):
    if period['kind']=='instant':return 'На '+date.fromisoformat(period['date']).strftime('%d.%m.%Y')
    start=date.fromisoformat(period['start']);end=date.fromisoformat(period['end']);kind=period['duration_type']
    if kind=='full_year':title=str(end.year)+' · полный год'
    elif kind=='quarter':title=['I','II','III','IV'][(start.month-1)//3]+' квартал '+str(end.year)
    elif kind=='year_to_date':title=('I полугодие'if end.month==6 else str(end.month)+' месяцев')+' '+str(end.year)
    else:title='Выбранный период'
    return title+' · '+start.strftime('%d.%m.%Y')+'–'+end.strftime('%d.%m.%Y')


def document_label(document):return period_label(document['report_period'])+' · '+('МСФО'if document['accounting_standard']=='IFRS'else document['accounting_standard'])+' · версия '+document['sha256'][:6]


def source_and_answers(mode,question,fields):
    validate_fields(fields,partial=True);selected={k:deepcopy(v)for k,v in fields.items()if v is not None}
    if mode=='question':return dict(kind='text',input_id='desktop-input',question=question),[selected]if selected else []
    return dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id='desktop-input',original_question=question or 'Задача задана выбранными полями формы.',fields=deepcopy(fields),assumptions=[])),[]


def option_label(field,option,catalog,dictionary):
    value=option['value'];orgs={o['organization_id']:o['name']for o in catalog['organizations']};docs={d['document_id']:d for d in catalog['documents']}
    if field=='organization':return orgs.get(value,option['label'])
    if field=='operation_id':return OPERATIONS.get(value,option['label'])
    if field=='metric_ids':return ' / '.join(METRICS.get(v,v)for v in value)
    if field=='periods':return ' → '.join(period_label(v)for v in value)if isinstance(value,list)else period_label(value)
    if field=='documents':return ' / '.join(document_label(docs[v['document_id']])for v in value)
    if field=='mode':return {'snapshot':'По выбранной отчётности','historical':'Что было известно на дату'}.get(value,option['label'])
    if field=='version_policy':return {'explicit_versions':'Выбранные отчёты, включая сравнительные данные','original_period_documents':'Первоначальные отчёты периодов'}.get(value,option['label'])
    if field in {'source_unit','result_unit'}:return unit_label(value)
    if field=='definition_ids':
        defs={d['definition_id']:d['label']for d in dictionary['definitions']};return ' / '.join(defs.get(v,v)for v in value)
    return option['label']


def example_fields(catalog):
    """An explicitly clicked example supplies CONTEXT only, never values or expected results."""
    doc=next(d for d in catalog['documents']if d['organization_id']=='phosagro_group'and d['report_period']['duration_type']=='quarter'and d['report_period']['end']=='2025-03-31')
    facts=[f for f in catalog['facts']if f['document_id']==doc['document_id']and f['metric_id']=='revenue']
    periods=sorted((f['period']for f in facts),key=lambda p:p['end'])
    return dict(organization=doc['organization_id'],operation_id='relative_change_v1',metric_ids=['revenue'],periods=periods,documents=[dict(document_id=doc['document_id'],version_id=doc['version_id'])],version_policy='explicit_versions',mode='snapshot')


def result_heading(result):
    op=result['operation_id'];metric=result['inputs'][0]['metric_id']
    if op=='operating_margin_v1':return 'Операционная маржа'
    if op in {'absolute_change_v1','relative_change_v1'}:return 'Изменение '+GENITIVE[metric]
    return METRICS[metric]
