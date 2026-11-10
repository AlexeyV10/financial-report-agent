"""Isolated product13 UI. All financial/scenario arithmetic belongs to existing services."""
from pathlib import Path
from datetime import datetime
import os,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import streamlit as st
import pandas as pd
import altair as alt
from financial_assistant.contracts_v2 import digest,read_json
from financial_assistant.service_b import load_service_context
from financial_assistant.service_ui import OP_LABELS,METRIC_LABELS,period_label,value_label
from financial_assistant.product_history import RunStore
from financial_assistant.product_downloads import HistoryDownloads
from financial_assistant.product_service import METHODS,financial,scenario,preflight,live_fingerprint,restore_registered
from financial_assistant.scenario_service import ScenarioContext,load_own_context
from financial_assistant.scenario_contracts_v1 import REQUEST,LABEL,REAL_LABEL
from financial_assistant.source_viewer import SourceViewer
from financial_assistant.agent_model_v2 import load_agent_model

st.set_page_config(page_title='Отчёт → проверяемый ответ',layout='wide')
st.title('Отчёт → проверяемый ответ')
st.caption('Учебный анализ отчётности · точные источники · расчёты кодом')

REASONS={'publication_unknown':'Дата публикации точной версии не доказана. На выбранную дату ответ недопустим.',
 'nonpositive_base':'Для относительного изменения нужна положительная база.',
 'no_compatible_fact':'В подготовленном каталоге нет совместимого набора. Это не доказывает отсутствие строки в PDF.',
 'source_missing':'Не найден зарегистрированный локальный файл.',
 'source_version_mismatch':'Байты документа отличаются от проверенной версии.',
 'index_missing':'Нет подготовленного поискового индекса.',
 'index_hash_mismatch':'Изменился индекс: нужна проверенная подготовка.',
 'model_unavailable':'Локальная модель недоступна. Запустите прежний scripts/local_model.ps1 start или отдельно выберите B.',
 'adapter_unavailable':'Локальная модель недоступна. Запустите прежний scripts/local_model.ps1 start или отдельно выберите B.',
 'real_prices_unavailable':'нет допустимых реальных цен',
 'real_calendar_unavailable':'нет проверенного календаря',
 'corporate_actions_unchecked':'не проверены корпоративные события',
 'price_rights_unconfirmed':'не подтверждены права на цены',
 'real_execution_not_supported':'реальное исполнение не поддерживается',
 'incompatible_periods':'Периоды несовместимы. Выберите полные окна через форму; parser поддерживает ограниченную грамматику.',
 'insufficient_evidence':'Поиск не дал полного комплекта доказательств.',
 'run_in_progress_or_interrupted_choose_new_run':'Запуск уже идёт или прерван. Автоповтора нет; для новой попытки выберите «Новый запуск».',
 'invalid_capital':'Начальный капитал должен быть положительной суммой в рублях.'}

def reason(code):return REASONS.get(code,'Проверка завершилась со статусом: '+str(code))

def downloads(store,record):
    key=record['record_id'];left,right=st.columns(2)
    left.link_button('Скачать JSON',st.session_state.downloads.url(key,'json'))
    right.link_button('Скачать Markdown',st.session_state.downloads.url(key,'md'))
    st.caption('Экспорт содержит только собственный ответ и минимальные локаторы. Первичные страницы и полный текст не включены. История хранится локально в tmp; резервной облачной копии нет.')

def render_fin(a,viewer,archived=False):
    st.caption('Запуск '+a['run_id']+' · метод '+a['method']+' · вызовы модели: '+str(a['model_calls']))
    st.text('Исходный вопрос: '+a['original_question'])
    if a['execution_status']=='awaiting_clarification':st.info('Нужно уточнение: выберите варианты ниже.')
    elif a['execution_status']in {'error','limit'}:st.error('Техническая остановка. Финансового результата нет. '+reason(a['reason_code']))
    elif a['financial_status']=='answered':
        r=a['financial_result'];st.metric(OP_LABELS[r['operation_id']],value_label(r));st.caption('Расчёт не повышает точность округлённых данных отчёта.')
        for c in a['assumption_checks']:
            wording={'increase':'рост','decrease':'снижение','unchanged':'отсутствие изменения'}
            if c['status']=='contradicted':st.warning('Предпосылка опровергнута: заявлено '+wording[c['assumption']['asserted_direction']]+', наблюдается '+wording[c['observed_direction']]+'.')
            elif c['status']=='supported':st.success('Направление изменения подтверждено выбранными фактами.')
            else:st.info('Предпосылка не проверена.')
        st.subheader('Из чего получен результат')
        for x in r['inputs']:
            st.write(METRIC_LABELS[x['metric_id']]+' — '+x['value']+' '+x['source_unit']['currency']+' × '+str(x['source_unit']['scale']))
            st.caption(period_label(x['period'])+' · исходная запись: '+x['raw_value'])
            st.caption(('Сравнительная колонка'if x['origin_role']=='comparative_period'else'Отчётный период')+' · '+x['document_id'])
        formula={'direct_fact_v1':'Проверенное значение строки отчёта','absolute_change_v1':'Текущее значение − предыдущее','relative_change_v1':'(Текущее − предыдущее) / предыдущее × 100%','scale_v1':'Исходная сумма × исходный масштаб / выбранный масштаб','operating_margin_v1':'Отчётная операционная прибыль / выручка × 100%'}
        st.write('Формула: '+formula[r['operation_id']]);st.caption('Проценты: HALF_UP до двух знаков. Денежные величины сохраняют точную дробь и точность исходника.')
        with st.expander('Доказательства и страницы источника'):
            viewer.register(a)
            for i,s in enumerate(r['sources']):
                loc=s['evidence']['locator'];st.write(s['document_id']+' · PDF-страница '+str(loc.get('pdf_page','—')))
                st.write('Строка: '+str(loc.get('row_label','—'))+' · колонка: '+str(loc.get('column_label','—')))
                st.caption('Версия '+s['version_id']+' · проверка ассистентом · публикация '+s['publication']['precision'])
                if s['data_origin']=='real':st.link_button('Открыть проверяемую страницу '+str(i+1),viewer.url(s['document_id'],s['version_id'],loc['pdf_page']))
                st.caption('Аудит: '+s['audit']['opinion']+'. '+s['audit']['limitation'])
            st.caption('Права на распространение PDF неизвестны. Открытие страницы проверяет точные байты, но не заменяет разметку числа. Human reviewed: 0.')
    else:st.warning(reason(a['reason_code']))
    if a['unfulfilled_requests']:st.warning('Осталось невыполненным: '+', '.join(a['unfulfilled_requests'])+'. Причина «почему» не исследовалась.')
    with st.expander('Понятая задача, происхождение полей и техническая трасса'):
        st.json(a)

def render_scenario(out):
    st.subheader(out['label'])
    if out['status']=='completed':
        st.success('Сигнал выполнен'if out['signal']else 'Сигнала нет: рост не выше порога')
        p=out['scenario'];a,b,c=st.columns(3);a.metric('Итоговый капитал, RUB',p['final_equity']);b.metric('Изменение, RUB',p['pnl']);c.metric('Максимальная просадка, %',p['max_drawdown']['percent'])
        paths={'Сценарий':p,'Деньги':out['comparisons']['cash_no_interest'],'Удержание':out['comparisons']['hold_same_allocation']}
        chart=pd.DataFrame([{'Момент':x['at'],'Вариант':k,'Капитал, RUB':float(x['equity'])}for k,v in paths.items()for x in v['ledger']])
        st.altair_chart(alt.Chart(chart).mark_line(point=True).encode(x=alt.X('Момент:N',sort=None),y=alt.Y('Капитал, RUB:Q',scale=alt.Scale(zero=False)),color='Вариант:N',tooltip=list(chart.columns)).properties(height=260),width='stretch')
        st.caption('Вымышленные цены. Деньги — без процентов. Удержание — с той же долей, допустимым входом и расходами.')
        for k,v in paths.items():st.write(k+': капитал '+v['final_equity']+' RUB; комиссии '+v['fees']+' RUB; проскальзывание '+v['slippage_cost']+' RUB')
        with st.expander('Журнал денег и количества'):
            for r in p['ledger']:st.write(r['at']+' · '+r['action']+' · деньги '+r['cash']+' · количество '+str(r['quantity'])+' · капитал '+r['equity'])
    elif out['status']=='blocked':st.warning('Сценарий заблокирован. '+reason(out['reason_code']));st.write('Недостающие условия: '+'; '.join(reason(x)for x in(out['eligibility']or {}).get('reason_codes',[])))
    else:st.error('Техническая остановка. '+reason(out['reason_code']))
    with st.expander('Финансовый вход, временной допуск и трасса'):st.json(out)

def activate(fp,viewer):
    if st.session_state.get('active_fp')!=fp:
        st.session_state.active_fp=fp;st.session_state.active_record=None;st.session_state.answers=[];st.session_state.nonce=0;viewer.revoke();st.session_state.downloads.revoke()

def run_controls():
    if st.button('Новый запуск',help='Явно разрешить ещё один запуск с новыми расходами; прежний исход останется в истории.'):
        st.session_state.nonce=time.time_ns();st.session_state.active_record=None

def main():
    config=os.environ.get('KP3_PRODUCT_CONTEXT')
    if not config:st.error('Не задан локальный контекст. Запуск: KP3_PRODUCT_CONTEXT=tmp/service-context.json.');return
    try:ctx=load_service_context(config);store=RunStore(os.environ.get('KP3_PRODUCT_HISTORY',ROOT/'tmp/product13/history'))
    except Exception as e:st.session_state.active_record=None;st.error('Подготовка недоступна: '+reason(getattr(e,'code','setup_unavailable')));return
    if st.session_state.get('viewer_context')!=ctx.identity:
        if 'viewer'in st.session_state:st.session_state.viewer.close()
        st.session_state.viewer=SourceViewer(ctx.calculation).start();st.session_state.viewer_context=ctx.identity
    viewer=st.session_state.viewer;cat=ctx.calculation.catalog
    if st.session_state.get('downloads_path')!=str(store.path):
        if 'downloads'in st.session_state:st.session_state.downloads.close()
        st.session_state.downloads=HistoryDownloads(store).start();st.session_state.downloads_path=str(store.path)
    page=st.sidebar.radio('Раздел',['Обзор','Анализ','Условный сценарий','История и экспорт','Источники','Диагностика'])
    if st.session_state.get('page')!=page:st.session_state.active_record=None;viewer.revoke();st.session_state.downloads.revoke();st.session_state.page=page
    if page=='Обзор':
        st.subheader('Что можно проверить');st.write('Выручку, отчётную операционную прибыль и конечный чистый операционный денежный поток нефинансовой группы по МСФО.')
        st.write('Пять действий: значение, разность, относительное изменение, масштаб и операционная маржа. Начните с формы в разделе «Анализ».')
        st.info('8 точных PDF-версий · 48 проверенных ячеек · 2 группы. Это учебные источники, не заказчики и не внедрения.')
        st.warning('Дата публикации всех 8 версий неизвестна. Анализ «на дату» и реальные торговые сценарии закрыты. Synthetic сценарий доступен отдельно.')
        st.write('B работает без модели. C вызывает модель для выбора инструментов; A делает один выбор после поиска. Сравнение качества ещё не проводилось.')
        if st.button('Проверить локальную готовность'):
            try:p=preflight(ctx);st.success('Готовность источников: '+str(p['ready']));st.dataframe(p['documents'],hide_index=True)
            except Exception as e:st.error(reason(getattr(e,'code','preflight_error')))
        if st.button('Проверить модель без генерации'):
            try:st.json(load_agent_model(ROOT/'data/config/local_model.json').probe())
            except Exception as e:st.error(reason(getattr(e,'code','model_unavailable')))
        return
    if page=='Источники':
        st.subheader('Готовность уже зарегистрированных источников');st.caption('Файл, извлечение, подготовка и происхождение — разные состояния. Новый сбор/OCR не выполняется.')
        try:st.dataframe(preflight(ctx)['documents'],hide_index=True)
        except Exception as e:st.error(reason(getattr(e,'code','preflight_error')))
        st.write('Prepared: 48 проверенных ячеек. Automatic: 40/48 целевых ячеек, 6/8 документов; ещё 8 квартальных кандидатов не допущены. Успех поиска не подтверждает финансовый смысл.')
        st.info('Если файла нет, восстановите только зарегистрированную exact-версию в доверенной карте tmp. SHA и размер должны совпасть. Произвольная загрузка не добавляет Fact или публикацию.')
        docs={d['document_id']:d for d in cat['documents']};did=st.selectbox('Зарегистрированная версия для восстановления',list(docs),index=None)
        upload=st.file_uploader('Локальный PDF уже зарегистрированной версии',type=['pdf'])
        if st.button('Проверить и восстановить exact-файл',disabled=did is None or upload is None):
            try:st.success({'already_present':'Совпадающий файл уже есть: повторная копия не создавалась.','restored_exact_version':'Точная версия восстановлена; каталог и provenance не менялись.'}[restore_registered(ctx,did,upload.getvalue())])
            except Exception as e:st.error(reason(getattr(e,'code','source_restore_failed')))
        return
    if page=='Диагностика':
        st.write('КП3-13: открытая разработка. Итоговый набор и benchmark КП3-14 ещё не запускались. Старые QA07 C/call_limit, 3/10 financial и reserved n=0 остаются прежними результатами.')
        with st.expander('Контекст и версии'):st.json(dict(context_digest=ctx.identity,live_digest=live_fingerprint(ctx),catalog=cat['catalog_id'],history_schema='kp3-history-0.1'))
        return
    if page=='История и экспорт':
        st.subheader('Собственные сохранённые запуски');rows=store.listing()
        if not rows:st.info('История пока пуста. Выполните анализ или собственный сценарий.');return
        options={r['record_id']:r for r in rows};key=st.selectbox('Сохранённый запуск',list(options),index=None,format_func=lambda x:options[x]['saved_at']+' · '+options[x]['method']+' · '+options[x]['status'])
        if key:
            try:
                record=store.load(key);st.warning('Сохранённый снимок. Источники заново не проверялись; модель не вызывается.');r=record['payload']['result']
                if record['payload']['kind']=='financial':render_fin(r,viewer,True)
                else:render_scenario(r)
                downloads(store,record)
            except Exception as e:st.error('Сохранённый файл повреждён или не поддерживается: '+getattr(e,'code',str(e)))
        return
    if page=='Условный сценарий':return scenario_page(ctx,store,viewer)
    st.subheader('Финансовый анализ')
    method=st.selectbox('Метод',list(METHODS),format_func=METHODS.get)
    mode=st.radio('Ввод',['Форма','Русский вопрос'],horizontal=True)
    if mode=='Русский вопрос':source=dict(kind='text',input_id='product13-input',question=st.text_area('Ваш вопрос',placeholder='Показатель, группа, полный период, версия отчёта и режим.'))
    else:source=form_source(ctx)
    fp=digest(dict(source=source,method=method,live=live_fingerprint(ctx)));activate(fp,viewer);run_controls()
    if st.button('Получить ответ',type='primary',disabled=mode=='Русский вопрос'and not source['question'].strip()):
        try:
            with st.spinner('Выполняется выбранный маршрут; повторного автоматического запуска нет…'):
                record,reused=financial(source,st.session_state.answers,method,ctx,store,st.session_state.nonce)
            st.session_state.active_record=record
            if reused:st.info('Открыт ранее сохранённый запуск; новых вызовов нет. Для новой попытки нажмите «Новый запуск».')
        except Exception as e:st.session_state.active_record=None;st.error(reason(getattr(e,'code',str(e))))
    record=st.session_state.get('active_record')
    if record:
        a=record['payload']['result'];render_fin(a,viewer)
        if a['execution_status']=='awaiting_clarification':
            patch={}
            for i,c in enumerate(a['clarifications']):
                st.write(c['message'])
                if c['options']:
                    idx=st.selectbox('Уточнение: '+c['field'],range(len(c['options'])),index=None,format_func=lambda x,c=c:c['options'][x]['label'],key=a['run_id']+str(i))
                    if idx is not None:patch[c['field']]=c['options'][idx]['value']
                elif c['field']=='as_of':
                    value=st.text_input('Дата, время и UTC-смещение',key=a['run_id']+str(i))
                    if value:patch['as_of']=value
                else:st.caption('Измените соответствующее поле формы или вопрос.')
            if st.button('Применить уточнения',disabled=not patch):
                st.session_state.answers=st.session_state.answers+[patch]
                try:st.session_state.active_record=financial(source,st.session_state.answers,method,ctx,store,st.session_state.nonce)[0];st.rerun()
                except Exception as e:st.error(reason(getattr(e,'code',str(e))))
        downloads(store,record)

def form_source(ctx):
    cat=ctx.calculation.catalog;orgs={o['organization_id']:o for o in cat['organizations']};docs={d['document_id']:d for d in cat['documents']}
    left,right=st.columns(2)
    with left:
        org=st.selectbox('Группа',list(orgs),index=None,format_func=lambda x:orgs[x]['name'],placeholder='Выберите группу')
        op=st.selectbox('Действие',list(OP_LABELS),index=None,format_func=OP_LABELS.get)
        metric=st.selectbox('Показатель',list(METRIC_LABELS),index=None,format_func=METRIC_LABELS.get,disabled=op=='operating_margin_v1')
        mids=['operating_profit','revenue']if op=='operating_margin_v1'else [metric]if metric else None
        available={digest(f['period']):f['period']for f in cat['facts']if f['organization_id']==org and(not mids or f['metric_id']in mids)}
        periods=st.multiselect('Полные периоды (предыдущий → текущий)',list(available),format_func=lambda x:period_label(available[x]),max_selections=2)
    with right:
        chosen=st.multiselect('Точные версии отчётов',[d for d in docs if docs[d]['organization_id']==org],format_func=lambda x:period_label(docs[x]['report_period'])+' · '+docs[x]['sha256'][:8],max_selections=2)
        policy=st.selectbox('Политика версии',['explicit_versions','original_period_documents'],index=None,format_func=lambda x:'Выбранные версии, включая сравнительные колонки'if x=='explicit_versions'else 'Исходные документы периодов')
        analysis=st.selectbox('Режим',['snapshot','historical'],index=None,format_func=lambda x:'Снимок документа'if x=='snapshot'else 'Что было известно на дату')
        asof=st.text_input('На дату: время и UTC-смещение',placeholder='2026-11-10T12:00:00+03:00')if analysis=='historical'else None
        target=None
        if op=='scale_v1':
            scale=st.selectbox('Масштаб результата',[1,1000,1000000,1000000000],index=None,format_func=lambda x:{1:'рубли',1000:'тыс. рублей',1000000:'млн рублей',1000000000:'млрд рублей'}[x])
            if scale:target=dict(kind='amount',currency='RUB',scale=scale)
    with st.expander('Определения и границы'):
        st.caption('Нефинансовая консолидированная группа, IFRS. Метаданные выводятся только при однозначности и отмечаются в происхождении полей.')
        definitions={x['definition_id']:x for x in ctx.calculation.dictionary['definitions']if not mids or x['metric_id']in mids}
        selected=st.multiselect('Определения (для маржи: прибыль → выручка)',list(definitions),format_func=lambda x:definitions[x]['label']+' · '+definitions[x]['version'],max_selections=2)
    question=st.text_input('Исходный вопрос / комментарий к форме')
    return dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id='product13-input',original_question=question or 'Явный запрос из структурированной формы.',fields=dict(organization=org,operation_id=op,metric_ids=mids,definition_ids=selected or None,periods=[available[p]for p in periods]or None,documents=[dict(document_id=d,version_id=docs[d]['version_id'])for d in chosen]or None,version_policy=policy,mode=analysis,as_of=asof or None,result_unit=target),assumptions=[]))

def scenario_page(service,store,viewer):
    st.subheader('Условный сценарий');mode=st.selectbox('Источник сценария',['Собственные искусственные данные','Проверка реального источника'],index=None)
    if mode is None:st.info('Выберите источник явно.');return
    params=None;fin=None
    if mode=='Собственные искусственные данные':
        st.warning(LABEL);st.caption('Выручка 100 → 120 RUB. Вымышленная группа, доступность, актив, календарь и цены; это не рыночная доходность.')
        ctx=load_own_context();example=read_json(ROOT/'data/scenarios/kp3_scenario_v1/request_example.json');p=example['parameters'];left,right=st.columns(2)
        with left:
            cash=st.text_input('Капитал, RUB',p['initial_cash']);allocation=st.text_input('Доля капитала',p['allocation']);threshold=st.text_input('Порог роста, %',p['threshold_pct']);decision=st.text_input('Момент решения с UTC-смещением',example['decision_at'])
        with right:
            fee=st.text_input('Комиссия за операцию, RUB',p['fee_fixed']);slip=st.text_input('Проскальзывание, базисные пункты',p['slippage_bps']);lot=st.number_input('Лот',min_value=1,max_value=1000000,value=1,step=1)
            sessions=ctx.dataset['calendar']['sessions'];start=st.selectbox('Начало окна',[s['open']for s in sessions]);end=st.selectbox('Конец окна',[s['close']for s in sessions],index=len(sessions)-1)
        params=dict(initial_cash=cash,allocation=allocation,threshold_pct=threshold,fee_fixed=fee,slippage_bps=slip,lot_size=int(lot),window_start=start,window_end=end);data_mode='own_synthetic'
        st.caption('Рост строго выше порога. Вход — первое объявленное открытие строго после решения; выход — закрытие конца окна. Лоты целые, расходы включены.')
    else:
        st.info(REAL_LABEL);rows=[]
        for row in store.listing():
            if row['kind']=='financial'and row['status']!='damaged':
                r=store.load(row['record_id'])['payload']['result']
                if r['financial_status']=='answered':rows.append(r)
        if not rows:st.info('Сначала получите финансовый ответ в разделе «Анализ».');return
        idx=st.selectbox('Проверенный финансовый запуск',range(len(rows)),index=None,format_func=lambda x:rows[x]['run_id']+' · '+rows[x]['original_question'])
        if idx is None:return
        fin=rows[idx];ctx=ScenarioContext(service,ROOT/'tmp/scenario-runs');data_mode='real_source_readiness';decision=st.text_input('Момент проверки с UTC-смещением');st.caption('Содержание финансового входа будет проверено заново. Реальные цены не подставляются.')
    req=dict(schema_version=REQUEST,financial_run_id=fin['run_id']if fin else 'pending-own-financial',data_mode=data_mode,decision_at=decision,parameters=params);source=dict(request=req,financial=fin)
    activate(digest(dict(source=source,context=ctx.identity,live=live_fingerprint(service))),viewer);run_controls()
    if st.button('Рассчитать сценарий'if params else 'Проверить готовность',type='primary',disabled=not decision):
        try:st.session_state.active_record=scenario(source,ctx,store,st.session_state.nonce)[0]
        except Exception as e:st.session_state.active_record=None;st.error(reason(getattr(e,'code',str(e))))
    record=st.session_state.get('active_record')
    if record:render_scenario(record['payload']['result']);downloads(store,record)

try:main()
except Exception as e:st.session_state.active_record=None;st.error('Техническая ошибка интерфейса: '+reason(getattr(e,'code',str(e))))
