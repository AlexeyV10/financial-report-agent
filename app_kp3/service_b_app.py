"""Minimal isolated Streamlit UI of the common fixed service B; no financial formulas here."""
from pathlib import Path
import json,os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import streamlit as st
from financial_assistant.contracts_v2 import digest
from financial_assistant.service_b import execute,load_service_context
from financial_assistant.service_ui import ViewState,OP_LABELS,METRIC_LABELS,period_label,value_label
from financial_assistant.source_viewer import SourceViewer

st.set_page_config(page_title='Проверяемый финансовый ответ',layout='wide')
st.title('Проверяемый финансовый ответ')
st.caption('Фиксированный маршрут B · подготовленный каталог · без модели')


def main():
    config=os.environ.get('KP3_SERVICE_CONTEXT')
    if not config:st.error('Не задан локальный контекст запуска.');return
    try:ctx=load_service_context(config)
    except Exception as e:
        if 'view'in st.session_state:st.session_state.view.answer=None
        if 'viewer'in st.session_state:st.session_state.viewer.revoke()
        st.error('Локальные ресурсы запуска недоступны или изменились.');st.code(getattr(e,'code','setup_unavailable'));return
    if 'view'not in st.session_state:st.session_state.view=ViewState()
    if st.session_state.get('viewer_identity')!=ctx.identity:
        if 'viewer'in st.session_state:st.session_state.viewer.revoke()
        st.session_state.viewer=SourceViewer(ctx.calculation).start();st.session_state.viewer_identity=ctx.identity
    view=st.session_state.view;viewer=st.session_state.viewer;cat=ctx.calculation.catalog
    def invalidate():view.answer=None;view.answers=[];viewer.revoke()
    mode=st.radio('Способ ввода',['Форма','Русский вопрос'],horizontal=True,key='input_mode',on_change=invalidate)
    if mode=='Русский вопрос':
        question=st.text_area('Ваш вопрос',placeholder='Укажите показатель, группу, полные периоды, версию отчёта и режим.',key='question',on_change=invalidate)
        st.caption('Например: «Покажи выручку группы ... за ... год из отчёта за ... год. Снимок.» Неоднозначные поля будут уточнены.')
        source=dict(kind='text',input_id='ui-input',question=question)
    else:
        left,right=st.columns(2)
        orgs={o['organization_id']:o for o in cat['organizations']};docs={d['document_id']:d for d in cat['documents']}
        with left:
            org=st.selectbox('Организация',list(orgs),index=None,format_func=lambda x:orgs[x]['name'],placeholder='Выберите организацию',key='organization',on_change=invalidate)
            op=st.selectbox('Действие',list(OP_LABELS),index=None,format_func=OP_LABELS.get,placeholder='Выберите действие',key='operation',on_change=invalidate)
            if op=='operating_margin_v1':mids=['operating_profit','revenue'];st.caption('Маржа: операционная прибыль / выручка одной версии и периода.')
            else:
                metric=st.selectbox('Показатель',list(METRIC_LABELS),index=None,format_func=METRIC_LABELS.get,placeholder='Выберите показатель',key='metric',on_change=invalidate);mids=[metric]if metric else None
            available={digest(f['period']):f['period']for f in cat['facts']if f['organization_id']==org and(not mids or f['metric_id']in mids)}
            periods=st.multiselect('Полные периоды',list(available),format_func=lambda x:period_label(available[x]),max_selections=2,key='periods',on_change=invalidate)
            st.caption('Для изменения: сначала предыдущий, затем текущий. Квартал и накопленный период выбираются отдельно.')
        with right:
            available_docs=[d['document_id']for d in cat['documents']if d['organization_id']==org]
            chosen=st.multiselect('Версии отчётов',available_docs,format_func=lambda x:period_label(docs[x]['report_period'])+' · '+docs[x]['sha256'][:8],max_selections=2,key='documents',on_change=invalidate)
            policy=st.selectbox('Политика версии',['explicit_versions','original_period_documents'],index=None,format_func=lambda x:'Выбранные exact-версии (сравнительные колонки допустимы)'if x=='explicit_versions'else 'Исходные документы соответствующих периодов',key='policy',on_change=invalidate)
            analysis=st.selectbox('Режим',['snapshot','historical'],index=None,format_func=lambda x:'Снимок документа'if x=='snapshot'else 'Что было известно на дату',placeholder='Выберите режим',key='analysis_mode',on_change=invalidate)
            asof=st.text_input('Момент с UTC-смещением',placeholder='2026-11-10T01:00:00+03:00',key='as_of',on_change=invalidate)if analysis=='historical'else None
            result=None
            if op=='scale_v1':
                scale=st.selectbox('Масштаб результата',[1,1000,1000000,1000000000],index=None,format_func=lambda s:{1:'Единицы',1000:'Тысячи',1000000:'Миллионы',1000000000:'Миллиарды'}[s],key='scale',on_change=invalidate)
                currency=st.selectbox('Валюта результата',['RUB','USD'],index=None,key='currency',on_change=invalidate)
                if scale and currency:result=dict(kind='amount',currency=currency,scale=scale)
        with st.expander('Стандарт, границы и определение'):
            standard=st.selectbox('Стандарт',['IFRS','RAS'],index=None,placeholder='Определить однозначно по каталогу',key='standard',on_change=invalidate)
            consolidation=st.selectbox('Границы',['group','legal_entity'],index=None,format_func=lambda s:'Консолидированная группа'if s=='group'else 'Отдельное юрлицо',placeholder='Определить однозначно по каталогу',key='consolidation',on_change=invalidate)
            defs={d['definition_id']:d for d in ctx.calculation.dictionary['definitions']if not mids or d['metric_id']in mids}
            definitions=st.multiselect('Версии определений',list(defs),format_func=lambda x:defs[x]['label']+' · '+defs[x]['version'],max_selections=2,key='definitions',on_change=invalidate)
            st.caption('Неуказанные metadata выводятся только при однозначности. Для маржи порядок определений: прибыль, выручка.')
        original=st.text_input('Исходный вопрос или комментарий к форме',key='form_question',on_change=invalidate)
        fields=dict(organization=org,operation_id=op,metric_ids=mids,definition_ids=definitions or None,periods=[available[p]for p in periods]or None,documents=[dict(document_id=d,version_id=docs[d]['version_id'])for d in chosen]or None,version_policy=policy,mode=analysis,as_of=asof or None,result_unit=result,accounting_standard=standard,consolidation=consolidation)
        source=dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id='ui-input',original_question=original or 'Запрос из структурированной формы.',fields=fields,assumptions=[]))
    if view.select(source,ctx.identity):viewer.revoke()
    if st.button('Получить ответ',type='primary',key='execute',disabled=mode=='Русский вопрос'and not source['question'].strip()):
        result=execute(source,'B',ctx,[]);view.accept(result,source,ctx.identity,[]);viewer.register(result)
    answer=view.answer
    if answer is None:st.info('Выберите поля или задайте вопрос. После изменения ввода прежний ответ скрывается.');return
    st.divider();st.caption('Запуск: '+answer['run_id']);st.write('Исходный вопрос: '+answer['original_question'])
    if answer['execution_status']=='awaiting_clarification':
        st.subheader('Нужно уточнение');patch={}
        for i,c in enumerate(answer['clarifications']):
            st.write(c['message']);options=c['options'];key='clarify_'+answer['run_id']+'_'+str(i)
            if options:
                idx=st.selectbox('Выбор: '+c['field'],range(len(options)),index=None,format_func=lambda x:options[x]['label'],key=key)
                if idx is not None:patch[c['field']]=options[idx]['value']
            elif c['field']=='as_of':
                stamp=st.text_input('Дата и время с зоной',key=key)
                if stamp:patch['as_of']=stamp
            else:st.caption('Уточните соответствующие поля основной формы или исходную формулировку.')
        if st.button('Применить уточнения',key='apply_clarification',disabled=not patch):
            answers=view.answers+[patch];result=execute(source,'B',ctx,answers);view.accept(result,source,ctx.identity,answers);viewer.register(result);st.rerun()
    elif answer['execution_status']in {'error','limit'}:st.error('Техническая ошибка. Финансовый результат не получен.');st.code(answer['reason_code'])
    elif answer['financial_status']=='answered':
        result=answer['financial_result'];st.metric(OP_LABELS[result['operation_id']],value_label(result));st.caption('Арифметика по округлённым исходным данным не повышает точность отчёта.')
        for check in answer['assumption_checks']:
            wording={'increase':'рост','decrease':'снижение','unchanged':'отсутствие изменения'}
            if check['status']=='contradicted':st.warning('Предпосылка не подтвердилась: по выбранным данным — '+wording[check['observed_direction']]+'.')
            elif check['status']=='supported':st.success('Направление изменения подтверждено выбранными данными.')
            else:st.info('Предпосылка не проверена для этого действия.')
            if check['explanation_status']=='not_supported':st.caption('Причина изменения не исследовалась.')
        with st.expander('Исходные значения и формула'):
            for x in result['inputs']:st.write(METRIC_LABELS[x['metric_id']]+': '+x['value']+' '+x['source_unit']['currency']+' ×'+str(x['source_unit']['scale'])+'; '+period_label(x['period']));st.caption('Исходная запись: '+x['raw_value'])
            st.code(result['formula']);st.write('Округление: '+result['rounding'])
        with st.expander('Первичные источники и ограничения'):
            for i,s in enumerate(result['sources']):
                loc=s['evidence']['locator'];st.write(s['document_id']+' · PDF-страница '+str(loc.get('pdf_page','—')));st.caption(str(loc))
                if s['data_origin']=='real':st.link_button('Открыть локальную страницу источника',viewer.url(s['document_id'],s['version_id'],loc['pdf_page']))
                st.caption('Проверено ассистентом. Публикация: '+s['publication']['precision']+'. Аудит: '+s['audit']['opinion']+'. '+s['audit']['limitation'])
            st.caption('Право распространения первичных PDF не установлено; источник доступен только локально.')
    else:
        message={'publication_unknown':'Дата публикации exact-версии не доказана. Анализ на дату заблокирован.','unverified_candidate':'Найденный кандидат не является проверенным входом.','nonpositive_base':'Для относительного изменения нужна положительная база.','no_compatible_fact':'В каталоге нет совместимого подготовленного входа.'}.get(answer['reason_code'],'Запрос не завершён финансовым ответом.')
        st.warning(message);st.code(answer['reason_code'])
    with st.expander('Понятая задача и происхождение полей'):
        if answer['normalized_input']:st.json(dict(fields=answer['normalized_input']['fields'],origins=answer['normalized_input']['field_origins'],assumptions=answer['normalized_input']['assumptions'],history=answer['normalized_input']['history']))
        if answer['unfulfilled_requests']:st.write('Невыполненные компоненты: '+', '.join(answer['unfulfilled_requests']))
    with st.expander('Трасса выполнения'):
        st.json(dict(run_id=answer['run_id'],execution_status=answer['execution_status'],request_status=answer['request_status'],financial_status=answer['financial_status'],trace=answer['trace'],saved_run=answer['saved_run']))


main()
