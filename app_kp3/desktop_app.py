"""Approved desktop design. Presentation around unchanged financial/product services."""
from pathlib import Path
from datetime import datetime,date,time as day_time
from html import escape
import os,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import streamlit as st
import pandas as pd
import altair as alt
from financial_assistant.contracts_v2 import digest,read_json
from financial_assistant.desktop_presentation import METHODS,OPERATIONS,METRICS,FIELDS,reason,number,unit_label,period_label,document_label,source_and_answers,option_label,example_fields,result_heading
from financial_assistant.service_b import load_service_context
from financial_assistant.product_history import RunStore
from financial_assistant.product_downloads import HistoryDownloads
from financial_assistant.product_service import financial,scenario,preflight,live_fingerprint,restore_registered
from financial_assistant.source_viewer import SourceViewer
from financial_assistant.scenario_service import load_own_context,ScenarioContext
from financial_assistant.scenario_contracts_v1 import REQUEST,LABEL,REAL_LABEL
from financial_assistant.agent_model_v2 import load_agent_model

st.set_page_config(page_title='Отчёт — финансовый анализ',page_icon=':material/finance:',layout='wide',initial_sidebar_state='expanded')
st.html('<style>'+(ROOT/'app_kp3/desktop.css').read_text(encoding='utf8')+'</style>')
PAGES={'Анализ отчётности':':material/query_stats:','Документы':':material/folder_open:','История':':material/history:','Учебный сценарий':':material/science:','Как это работает':':material/help_outline:'}


def mark(text,cls):st.html('<div class="'+cls+'">'+escape(str(text))+'</div>')


def clear_result():
    st.session_state.active_record=None;st.session_state.followups=[];st.session_state.nonce=0;st.session_state.evidence_open=False
    if 'viewer'in st.session_state:st.session_state.viewer.revoke()
    if 'downloads'in st.session_state:st.session_state.downloads.revoke()


def activate(fingerprint):
    if st.session_state.get('active_fingerprint')!=fingerprint:clear_result();st.session_state.active_fingerprint=fingerprint


def navigate(page):
    if st.session_state.get('desktop_page')!=page:clear_result();st.session_state.desktop_page=page


def fill_example(ctx):
    f=example_fields(ctx.calculation.catalog);st.session_state.update(input_mode='Задать вопрос',question='На сколько процентов изменилась выручка ФосАгро за I квартал 2024 и 2025?',org=f['organization'],operation=f['operation_id'],metric='revenue',previous=digest(f['periods'][0]),current=digest(f['periods'][1]),doc_selection=[f['documents'][0]['document_id']],version_policy='explicit_versions',data_mode='snapshot',comment='Сравнение выручки в процентах по выбранным периодам.',example_selected=True)
    clear_result()


def reset_input():
    for key in ['org','previous','current','single_period','operation','metric','data_mode','scale','version_policy']:st.session_state[key]=None
    st.session_state.doc_selection=[];st.session_state.question='';st.session_state.comment='';st.session_state.example_selected=False
    clear_result()


def setup():
    path=os.environ.get('KP3_DESKTOP_CONTEXT')
    if not path:
        st.error('Приложению нужен подготовленный каталог. Инструкция запуска находится в docs/kp3/desktop_ui_v1.md.');return None,None
    try:
        ctx=load_service_context(path);store=RunStore(os.environ.get('KP3_DESKTOP_HISTORY',ROOT/'tmp/desktop/history'))
    except Exception as e:clear_result();st.error('Не удалось подготовить приложение. '+reason(getattr(e,'code','setup_unavailable')));return None,None
    if st.session_state.get('viewer_identity')!=ctx.identity:
        if 'viewer'in st.session_state:st.session_state.viewer.close()
        st.session_state.viewer=SourceViewer(ctx.calculation).start();st.session_state.viewer_identity=ctx.identity;clear_result()
    if st.session_state.get('download_store')!=str(store.path):
        if 'downloads'in st.session_state:st.session_state.downloads.close()
        st.session_state.downloads=HistoryDownloads(store).start();st.session_state.download_store=str(store.path)
    return ctx,store


def sidebar():
    with st.sidebar:
        st.html('<div class="brand"><span>↗</span>Отчёт</div><div class="sidebar-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>')
        with st.container(key='navigation'):
            for name,icon in list(PAGES.items())[:4]:st.button(name,icon=icon,width='stretch',type='primary'if st.session_state.desktop_page==name else'secondary',on_click=navigate,args=(name,))
        with st.container(key='sidebar-footer'):
            st.caption('Каждое число — с источником. Отчётность, точная страница и проверяемый расчёт.')
            st.button('Как это работает',icon=PAGES['Как это работает'],width='stretch',on_click=navigate,args=('Как это работает',))


def export(record):
    st.session_state.downloads.select(record['record_id'])
    with st.popover('Скачать ответ',icon=':material/download:',width='stretch'):
        st.caption('Собственный ответ и ссылки на источник. Полные страницы отчётов не включены.')
        st.link_button('Краткий отчёт (.md)',st.session_state.downloads.url(record['record_id'],'md'),width='stretch')
        st.link_button('Данные для программы (.json)',st.session_state.downloads.url(record['record_id'],'json'),width='stretch')


def evidence(answer,ctx):
    viewer=st.session_state.viewer;viewer.register(answer)
    with st.container(border=True,key='source-card'):
        st.subheader('Источник чисел');seen=set()
        for source in answer['financial_result']['sources']:
            loc=source['evidence']['locator'];doc=next(d for d in ctx.calculation.catalog['documents']if d['document_id']==source['document_id'])
            st.markdown('**'+document_label(doc)+'**')
            st.write('Строка: '+str(loc.get('row_label','—')))
            st.caption('Колонка: '+str(loc.get('column_label','—'))+' · единицы: '+str(loc.get('unit_header','—')))
            st.caption('Страница PDF '+str(loc.get('pdf_page','—'))+' · печатная страница '+str(loc.get('printed_page','—')))
            key=(source['document_id'],source['version_id'],loc.get('pdf_page'))
            if source['data_origin']=='real'and key not in seen:
                st.link_button('Открыть страницу отчёта',viewer.url(*key),icon=':material/open_in_new:',width='stretch');seen.add(key)
            with st.expander('Версия и ограничения источника'):
                st.caption('Числа размечены и сверены ассистентом; проверка пользователем не заявлена.')
                st.write('Аудит: '+source['audit']['opinion']);st.caption(source['audit']['limitation'])
                st.caption('Дата публикации точной версии не подтверждена. Права на распространение PDF не установлены.')
                st.code(source['version_id'],language=None)
        st.caption('Открытие страницы проверяет точные байты файла. Оно не является новой проверкой финансового смысла числа.')


def show_assumptions(answer):
    names={'increase':'рост','decrease':'снижение','unchanged':'отсутствие изменения'}
    for c in answer['assumption_checks']:
        if c['status']=='contradicted':st.warning('Предпосылка не подтвердилась: в вопросе заявлено '+names[c['assumption']['asserted_direction']]+', по данным — '+names[c['observed_direction']]+'.')
        elif c['status']=='supported':st.success('Направление изменения подтвердилось по выбранным данным.')
        else:st.info('Предпосылка пока не проверена: допустимого финансового результата нет.')
    if answer['unfulfilled_requests']:st.warning('Причины роста или снижения не исследовались. Расчёт проверяет значения и изменение, но не объясняет, почему оно произошло.')


def render_result(record,ctx,archived=False):
    a=record['payload']['result']
    if archived:st.warning('Сохранённый ответ. Источники заново не проверялись, модель и расчёт не запускались.')
    if a['financial_status']=='answered'and a['execution_status']=='completed':
        r=a['financial_result'];unit=unit_label(r['result_unit']);value=number(r['display_value'])
        if r['operation_id']in {'relative_change_v1','absolute_change_v1'}and int(r['exact_result']['numerator'])>0:value='+'+value
        with st.container(border=True,key='answer-card'):
            mark('Сохранённый результат'if archived else'Есть проверяемый источник','result-badge')
            mark(result_heading(r),'result-kicker')
            org=next(o for o in ctx.calculation.catalog['organizations']if o['organization_id']==r['inputs'][0]['organization_id'])
            mark(org['name']+' · МСФО, группа компаний','company-line')
            st.html('<div class="hero-value">'+escape(value)+'<small>'+escape(unit)+'</small></div>')
            cells=[]
            for item in r['inputs']:
                label={'previous':'Базовый период','current':'Отчётный период','profit':'Операционная прибыль','revenue':'Выручка','fact':METRICS[item['metric_id']]}.get(item['role'],METRICS[item['metric_id']])
                cells.append('<div class="source-value"><div class="metric">'+escape(label)+'</div><div class="period">'+escape(period_label(item['period']))+'</div><div class="value">'+escape(number(item['value']))+' <small>'+escape(unit_label(item['source_unit']))+'</small></div><div class="comparative">'+('Сравнительные данные в выбранном отчёте'if item['origin_role']=='comparative_period'else'Отчётный период')+'</div></div>')
            st.html('<div class="source-values">'+''.join(cells)+'</div>')
            if len({x['document_id']for x in r['inputs']})==1 and any(x['origin_role']=='comparative_period'for x in r['inputs']):st.caption('Значение базового периода приведено в этом же отчёте как сравнительное. Оно не подменяется первоначальной версией другого документа.')
            show_assumptions(a)
            left,right=st.columns([1.1,1])
            with left:
                if st.button('Посмотреть источник',icon=':material/find_in_page:',type='primary',width='stretch',key='source-toggle'):st.session_state.evidence_open=not st.session_state.get('evidence_open',False)
            with right:export(record)
        if st.session_state.get('evidence_open'):evidence(a,ctx)
        with st.expander('Как получен ответ',icon=':material/checklist:'):
            steps={'input':'Понят вопрос','catalog_filters':'Выбраны условия','search':'Найдены данные','fact_resolution':'Определены точные ячейки','source_validation':'Проверены источник и совместимость','model_selection':'Проверен выбор модели','calculation':'Выполнен расчёт','result_validation':'Перепроверен результат','answer':'Подготовлен ответ'}
            for step in a['trace']:
                if step['status']!='skipped':st.write(('✓ 'if step['status']=='completed'else'• ')+steps.get(step['stage'],step['stage']))
            formulas={'direct_fact_v1':'Значение выбранной строки отчёта','absolute_change_v1':'Текущее значение − базовое значение','relative_change_v1':'(Текущее значение − базовое) / базовое × 100%','scale_v1':'Исходное значение × исходный масштаб / выбранный масштаб','operating_margin_v1':'Операционная прибыль / выручка × 100%'}
            st.caption('Формула: '+formulas[r['operation_id']]);st.caption('Проценты округляются до двух знаков (HALF_UP). Деньги сохраняют точное значение и исходную точность отчёта.')
    else:
        with st.container(border=True,key='clarification-card'):
            if a['execution_status']=='awaiting_clarification':st.subheader('Уточним условия анализа');st.info('Для однозначного ответа выберите варианты ниже.')
            elif a['execution_status']in {'error','limit'}:st.subheader('Не удалось завершить проверку');st.error(reason(a['reason_code']))
            else:st.subheader('Ответ пока недоступен');st.warning(reason(a['reason_code']))
            show_assumptions(a);st.caption('Числовой результат не показан. Прежнее число не подставляется вместо отказа.')
            export(record)
    with st.expander('Технические детали'):
        st.caption('Способ анализа: '+METHODS.get(a['method'],a['method'])+' · вызовы модели: '+str(a['model_calls']))
        st.write('Исходный вопрос: '+a['original_question']);st.json(a)


def selections(ctx,mode):
    cat=ctx.calculation.catalog;orgs={o['organization_id']:o for o in cat['organizations']};docs={d['document_id']:d for d in cat['documents']}
    org=st.selectbox('Компания',list(orgs),index=None,format_func=lambda v:{'phosagro_group':'ФосАгро','segezha_group':'Segezha Group'}.get(v,orgs[v]['name']),placeholder='Выберите или укажите в вопросе',key='org')
    fields=dict(organization=org)
    if mode=='question':
        q=st.text_area('Ваш вопрос',placeholder='Например: какая выручка ФосАгро за полный 2024 год?',height=135,key='question')
    else:
        op=st.selectbox('Что нужно сделать',list(OPERATIONS),index=None,format_func=OPERATIONS.get,placeholder='Выберите задачу',key='operation');fields['operation_id']=op
        metric=None if op=='operating_margin_v1'else st.selectbox('Показатель',list(METRICS),index=None,format_func=METRICS.get,placeholder='Выберите показатель',key='metric')
        mids=['operating_profit','revenue']if op=='operating_margin_v1'else[metric]if metric else None;fields['metric_ids']=mids
        if op=='operating_margin_v1':st.caption('Отчётная операционная прибыль / выручка. Одна группа, период, версия и единицы.')
        available={digest(f['period']):f['period']for f in cat['facts']if f['organization_id']==org and(not mids or f['metric_id']in mids)}
        available=dict(sorted(available.items(),key=lambda x:(x[1]['start'],x[1]['end'],x[1]['duration_type'])))
        for key in ['previous','current','single_period']:
            if st.session_state.get(key)not in available:st.session_state[key]=None
        if op in {'relative_change_v1','absolute_change_v1'}:
            previous=st.selectbox('Базовый период',list(available),index=None,format_func=lambda v:period_label(available[v]),placeholder='С чем сравниваем',key='previous')
            current=st.selectbox('Отчётный период',list(available),index=None,format_func=lambda v:period_label(available[v]),placeholder='Что сравниваем',key='current')
            fields['periods']=[available[x]for x in [previous,current]if x]or None
        else:
            period=st.selectbox('За какой период',list(available),index=None,format_func=lambda v:period_label(available[v]),placeholder='Выберите полный период',key='single_period');fields['periods']=[available[period]]if period else None
        if op=='scale_v1':
            scale=st.selectbox('Единицы результата',[1,1000,1000000,1000000000],index=None,format_func=lambda v:unit_label(dict(currency='RUB',scale=v)),placeholder='Выберите единицы',key='scale');fields['result_unit']=dict(kind='amount',currency='RUB',scale=scale)if scale else None
        q=st.text_input('Комментарий к задаче (необязательно)',key='comment')
    action_slot=st.container()
    eligible={did:d for did,d in docs.items()if not org or d['organization_id']==org}
    if any(d not in eligible for d in st.session_state.get('doc_selection',[])):st.session_state.doc_selection=[]
    with st.expander('Какую отчётность использовать'):
        chosen=st.multiselect('Какие отчёты использовать',list(eligible),format_func=lambda v:document_label(eligible[v]),max_selections=2,placeholder='Выберите версии или уточните после вопроса',key='doc_selection')
        fields['documents']=[dict(document_id=did,version_id=docs[did]['version_id'])for did in chosen]or None
        data_mode=st.selectbox('По каким данным анализировать',['snapshot','historical'],index=None,format_func=lambda v:'По выбранной отчётности'if v=='snapshot'else'Что было известно на дату',placeholder='Выберите режим анализа',key='data_mode');fields['mode']=data_mode
        if data_mode=='historical':
            st.warning('Дата публикации имеющихся версий не подтверждена. Исторический ответ будет заблокирован.')
            stamp_date=st.date_input('Дата анализа',value=None,key='asof-date');stamp_time=st.time_input('Время анализа · Москва (UTC+03:00)',value=None,key='asof-time')
            fields['as_of']=datetime.combine(stamp_date,stamp_time).isoformat()+'+03:00'if stamp_date and stamp_time is not None else None
    if chosen:st.caption('Выбран отчёт: '+document_label(docs[chosen[0]])+(' и ещё одна версия'if len(chosen)>1 else''))
    if data_mode:st.caption('Режим: '+('по выбранной отчётности'if data_mode=='snapshot'else'на историческую дату'))
    with st.expander('Дополнительные настройки'):
        method=st.selectbox('Способ анализа',list(METHODS),format_func=METHODS.get,key='method')
        policy=st.selectbox('Правило выбора версии',['explicit_versions','original_period_documents'],index=None,format_func=lambda v:'Выбранные отчёты, включая сравнительные данные'if v=='explicit_versions'else'Первоначальные отчёты периодов',placeholder='Уточнить при необходимости',key='version_policy')
        fields['version_policy']=policy
        definitions={d['definition_id']:d for d in ctx.calculation.dictionary['definitions']}
        if st.checkbox('Выбрать определения вручную',key='definition-manual'):
            values=st.multiselect('Определения показателей',list(definitions),format_func=lambda v:definitions[v]['label'],max_selections=2,key='definitions');fields['definition_ids']=values or None
        st.caption('Нефинансовые группы по МСФО. Новые источники, валютная конвертация и произвольные формулы здесь не добавляются.')
    st.caption('Выбран способ: '+METHODS[method]+'.')
    return (*source_and_answers(mode,q,fields),method,action_slot)


def clarification_controls(record,source,base_answers,method,ctx,store):
    a=record['payload']['result']
    if a['execution_status']!='awaiting_clarification':return
    patch={}
    for i,c in enumerate(a['clarifications']):
        label=FIELDS.get(c['field'],'Дополнительное условие')
        if c['options']:
            pick=st.selectbox(label,range(len(c['options'])),index=None,format_func=lambda v,c=c:option_label(c['field'],c['options'][v],ctx.calculation.catalog,ctx.calculation.dictionary),placeholder='Выберите вариант',key='clarify-'+a['run_id']+str(i))
            if pick is not None:patch[c['field']]=c['options'][pick]['value']
        elif c['field']=='as_of':
            value=st.text_input('Дата, время и часовой пояс',placeholder='2026-11-10T12:00:00+03:00',key='clarify-asof-'+a['run_id'])
            if value:patch['as_of']=value
        else:st.caption('Уточните поле «'+label+'» в условиях слева.')
    if st.button('Продолжить с выбранными условиями',type='primary',disabled=not patch):
        st.session_state.followups=st.session_state.followups+[patch]
        try:st.session_state.active_record=financial(source,base_answers+st.session_state.followups,method,ctx,store,st.session_state.nonce)[0];st.rerun()
        except Exception as e:st.error(reason(getattr(e,'code','clarification_failed')))


def analysis_page(ctx,store):
    left,right=st.columns([.94,1.4],gap='large')
    with left:
        with st.container(border=True,key='input-card'):
            st.subheader('Что анализируем')
            with st.container(key='input-mode'):mode=st.radio('Ввод',['Задать вопрос','Заполнить поля'],horizontal=True,label_visibility='collapsed',key='input_mode')
            source,base_answers,method,action_slot=selections(ctx,'question'if mode=='Задать вопрос'else'form')
            fp=digest(dict(source=source,answers=base_answers,method=method,live=live_fingerprint(ctx)));activate(fp)
            with action_slot:clicked=st.button('Проверить и рассчитать',type='primary',icon=':material/search_check:',width='stretch',disabled=source['kind']=='text'and not source['question'].strip())
            if clicked:
                try:
                    with st.spinner('Ищем данные и проверяем расчёт…'):record,reused=financial(source,base_answers+st.session_state.followups,method,ctx,store,st.session_state.nonce)
                    st.session_state.active_record=record
                    if reused:st.info('Открыт сохранённый результат этого запроса. Нового вызова модели не было.')
                except Exception as e:st.session_state.active_record=None;st.error(reason(getattr(e,'code','execution_failed')))
        st.button('Заполнить пример',icon=':material/lightbulb:',on_click=fill_example,args=(ctx,),width='stretch')
        if st.session_state.get('example_selected'):st.caption('Пример заполняет условия задачи. Числа получает и проверяет сервис; условия можно изменить.')
    with right:
        record=st.session_state.get('active_record')
        if record:
            render_result(record,ctx);clarification_controls(record,source,base_answers,method,ctx,store)
            if st.button('Рассчитать ещё раз',help='Создать отдельную новую попытку. При A/C возможны дополнительные вызовы модели.'):
                st.session_state.nonce=time.time_ns();st.session_state.active_record=None;st.session_state.viewer.revoke();st.session_state.downloads.revoke();st.rerun()
        else:
            with st.container(border=True,key='empty-card'):
                mark('↗','empty-mark');st.subheader('Здесь появится проверяемый ответ')
                mark('Задайте вопрос или заполните поля задачи. Если не хватает условий, мы уточним их. Рядом с результатом будут исходные числа и конкретная страница отчёта.','empty-copy')
                st.caption('Выручка · операционная прибыль · денежный поток от операций. Нет подходящих проверенных данных — нет подставленного числа.')


def documents_page(ctx):
    st.caption('8 версий отчётности двух групп. Подготовленная разметка сверена ассистентом; неизвестная публикация не заменяется датой получения.')
    orgs={o['organization_id']:o['name']for o in ctx.calculation.catalog['organizations']};org=st.selectbox('Показать компанию',list(orgs),index=None,format_func=orgs.get,placeholder='Все компании',key='docs-filter')
    if st.button('Проверить файлы и поиск',icon=':material/fact_check:'):
        try:st.session_state.readiness=preflight(ctx)
        except Exception as e:st.session_state.readiness=None;st.error(reason(getattr(e,'code','preflight_failed')))
    ready={r['document_id']:r for r in(st.session_state.get('readiness')or{}).get('documents',[])}
    for d in ctx.calculation.catalog['documents']:
        if org and d['organization_id']!=org:continue
        with st.container(border=True):
            st.markdown('**'+orgs[d['organization_id']]+' · '+document_label(d)+'**')
            if d['document_id']in ready:
                r=ready[d['document_id']];st.caption('Файл проверен'if r['file']=='ready'else reason(r['reason']))
            else:st.caption('Состояние файла ещё не проверялось в этом сеансе.')
            st.caption('Дата публикации точной версии не подтверждена · первичный PDF не входит в публичный пакет')
            with st.expander('Версия файла и восстановление'):
                st.code(d['sha256'],language=None)
                upload=st.file_uploader('Найти локальный PDF этой версии',type=['pdf'],key='restore-'+d['document_id'])
                if st.button('Проверить и восстановить файл',disabled=upload is None,key='restore-button-'+d['document_id']):
                    try:state=restore_registered(ctx,d['document_id'],upload.getvalue());st.success('Совпадающий файл уже на месте.'if state=='already_present'else'Точная версия восстановлена. Данные и проверка не повышены.');st.session_state.readiness=None
                    except Exception as e:st.error(reason(getattr(e,'code','restore_failed')))
    st.caption('Automatic-поиск даёт кандидатов: 40/48 целевых ячеек, 6/8 документов. Они не становятся проверенными входами калькулятора.')


def history_page(ctx,store):
    rows=store.listing()
    if not rows:st.info('История пока пуста. Сначала выполните анализ или учебный сценарий.');return
    options={r['record_id']:r for r in rows}
    def title(key):
        row=options[key]
        try:r=store.load(key)['payload']['result'];question=r.get('original_question','Учебный сценарий');return row['saved_at'][:16].replace('T',' ')+' UTC · '+question[:90]
        except Exception:return 'Повреждённый сохранённый файл'
    chosen=st.selectbox('Какой ответ открыть',list(options),index=None,format_func=title,placeholder='Выберите сохранённый анализ',key='history-selection')
    if st.session_state.get('history-active')!=chosen:st.session_state.viewer.revoke();st.session_state.downloads.revoke();st.session_state.evidence_open=False;st.session_state.history_active=chosen;st.session_state['history-active']=chosen
    if chosen:
        try:
            record=store.load(chosen)
            if record['payload']['kind']=='financial':render_result(record,ctx,True)
            else:st.warning('Сохранённый учебный сценарий, не новый расчёт.');render_scenario(record['payload']['result']);export(record)
        except Exception as e:st.error('Сохранённый файл повреждён или несовместим. '+reason(getattr(e,'code','history_failed')))


def render_scenario(out):
    st.warning(out['label'])
    if out['status']=='completed':
        st.success('Условие выполнено'if out['signal']else'Условие не выполнено — сценарий остаётся в деньгах')
        result=out['scenario'];a,b,c=st.columns(3);a.metric('Итоговый капитал',number(result['final_equity'])+' ₽');b.metric('Изменение капитала',number(result['pnl'])+' ₽');c.metric('Максимальная просадка',number(result['max_drawdown']['percent'])+' %')
        paths={'Сценарий':result,'Деньги':out['comparisons']['cash_no_interest'],'Удержание':out['comparisons']['hold_same_allocation']}
        chart=pd.DataFrame([dict(Момент=x['at'],Вариант=k,Капитал=float(x['equity']))for k,v in paths.items()for x in v['ledger']])
        st.altair_chart(alt.Chart(chart).mark_line(point=True).encode(x=alt.X('Момент:N',sort=None),y=alt.Y('Капитал:Q',scale=alt.Scale(zero=False)),color='Вариант:N',tooltip=list(chart.columns)).properties(height=250),width='stretch')
        st.caption('Вымышленные цены. Сравнение с деньгами и удержанием использует ту же долю и расходы.')
        with st.expander('Деньги, сделки и расходы'):st.dataframe(result['ledger'],hide_index=True)
    elif out['status']=='blocked':
        st.warning(reason(out['reason_code']))
        for code in(out.get('eligibility')or{}).get('reason_codes',[]):st.write('• '+reason(code))
    else:st.error(reason(out['reason_code']))
    with st.expander('Технические детали сценария'):st.json(out)


def scenario_page(ctx,store):
    st.info('Учебная модель на искусственных данных. Реальные сделки не выполняются.')
    mode=st.selectbox('На каких данных проверить сценарий',['Собственный учебный пример','Готовность реального источника'],index=None,placeholder='Выберите источник сценария',key='scenario-source')
    if mode is None:return
    params=None;fin=None
    if mode=='Собственный учебный пример':
        st.warning(LABEL);st.caption('Вымышленные выручка 100 → 120 ₽, актив, доступность, календарь и цены.')
        sc=load_own_context(ROOT/'tmp/desktop/scenario-runs');sample=read_json(ROOT/'data/scenarios/kp3_scenario_v1/request_example.json');p=sample['parameters']
        a,b=st.columns(2)
        with a:cash=st.text_input('Начальный капитал, ₽',p['initial_cash']);allocation=st.text_input('Доля капитала (0–1)',p['allocation']);threshold=st.text_input('Рост выше порога, %',p['threshold_pct']);decision=st.text_input('Момент решения с часовым поясом',sample['decision_at'])
        with b:fee=st.text_input('Комиссия за операцию, ₽',p['fee_fixed']);slip=st.text_input('Проскальзывание, базисные пункты',p['slippage_bps']);lot=st.number_input('Размер лота',min_value=1,max_value=1000000,value=1,step=1)
        sessions=sc.dataset['calendar']['sessions'];start=st.selectbox('Начало учебного окна',[s['open']for s in sessions]);end=st.selectbox('Конец учебного окна',[s['close']for s in sessions],index=len(sessions)-1)
        params=dict(initial_cash=cash,allocation=allocation,threshold_pct=threshold,fee_fixed=fee,slippage_bps=slip,lot_size=int(lot),window_start=start,window_end=end);data_mode='own_synthetic'
        st.caption('Вход — следующее объявленное открытие строго после решения. Комиссии, проскальзывание и целые лоты учитываются существующим сервисом.')
    else:
        st.warning(REAL_LABEL);rows=[]
        for row in store.listing():
            if row['kind']=='financial'and row['status']!='damaged':
                r=store.load(row['record_id'])['payload']['result']
                if r['financial_status']=='answered':rows.append(r)
        if not rows:st.info('Сначала выполните финансовый анализ, затем выберите его результат.');return
        pick=st.selectbox('Какой финансовый ответ использовать',range(len(rows)),index=None,format_func=lambda v:rows[v]['original_question'][:90],placeholder='Выберите ответ',key='scenario-financial')
        if pick is None:return
        fin=rows[pick];sc=ScenarioContext(ctx,ROOT/'tmp/desktop/scenario-runs');data_mode='real_source_readiness';decision=st.text_input('Момент проверки с часовым поясом')
    source=dict(request=dict(schema_version=REQUEST,financial_run_id=fin['run_id']if fin else'pending-own-financial',data_mode=data_mode,decision_at=decision,parameters=params),financial=fin)
    activate(digest(dict(source=source,context=sc.identity,live=live_fingerprint(ctx))))
    if st.button('Рассчитать учебный сценарий'if params else'Проверить готовность источника',type='primary',disabled=not decision):
        try:st.session_state.active_record=scenario(source,sc,store,st.session_state.nonce)[0]
        except Exception as e:st.session_state.active_record=None;st.error(reason(getattr(e,'code','scenario_failed')))
    record=st.session_state.get('active_record')
    if record:render_scenario(record['payload']['result']);export(record)


def help_page(ctx):
    with st.container(border=True):
        st.subheader('От вопроса к источнику')
        st.markdown('1. Выберите компанию или назовите её в вопросе.\n2. Укажите показатель, полные периоды и версию отчётности.\n3. Нажмите «Проверить и рассчитать».\n4. Откройте источник рядом с результатом.')
        st.write('Поддерживаются выручка, отчётная операционная прибыль и конечный чистый денежный поток от операционной деятельности нефинансовой группы по МСФО.')
        st.caption('Поиск и расчёт без модели — обычный фиксированный маршрут. Один выбор модели и агент с инструментами доступны в дополнительных настройках; автоматической замены одного способа другим нет.')
        st.warning('Все 8 дат публикации точных версий неизвестны. Исторический анализ и реальные торговые сценарии закрыты. Числа проверены ассистентом, пользовательская проверка не приписывается.')
    with st.expander('Настройки и диагностика'):
        if st.button('Проверить модель без генерации'):
            try:probe=load_agent_model(ROOT/'data/config/local_model.json').probe();st.success('Локальная модель доступна.');st.json(probe)
            except Exception as e:st.warning(reason(getattr(e,'code','adapter_unavailable')))
        st.caption('Для подготовленной модели: scripts/local_model.ps1 start. Запуск — отдельное действие, новая модель не скачивается.')
        st.json(dict(catalog=ctx.calculation.catalog['catalog_id'],context=ctx.identity,live=live_fingerprint(ctx)))


def main():
    st.session_state.setdefault('desktop_page','Анализ отчётности');sidebar();ctx,store=setup()
    if ctx is None:return
    page=st.session_state.desktop_page
    mark('Рабочее пространство / '+page,'breadcrumb')
    head,action=st.columns([3,1])
    with head:st.title('Новый анализ'if page=='Анализ отчётности'else page)
    if page=='Анализ отчётности':
        with action:st.button('Другой вопрос',icon=':material/add:',on_click=reset_input,width='stretch')
        mark('Задайте вопрос. Получите ответ с проверяемым источником.','page-subtitle');analysis_page(ctx,store)
    elif page=='Документы':documents_page(ctx)
    elif page=='История':history_page(ctx,store)
    elif page=='Учебный сценарий':scenario_page(ctx,store)
    else:help_page(ctx)


try:main()
except Exception as e:
    clear_result();st.error('Не удалось открыть интерфейс. '+reason(getattr(e,'code','desktop_failed')))
    with st.expander('Диагностика ошибки'):st.write(type(e).__name__);st.write(getattr(e,'code','desktop_failed'))
