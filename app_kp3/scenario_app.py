"""Isolated minimal scenario12 UI. Arithmetic and admission live in the shared services."""
from copy import deepcopy
from datetime import datetime
import json,os,sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
import streamlit as st
from financial_assistant.contracts_v2 import digest,read_json
from financial_assistant.service_b import execute,load_service_context
from financial_assistant.scenario_service import ScenarioContext,load_own_context,own_financial,execute_scenario
from financial_assistant.scenario_contracts_v1 import REQUEST,LABEL,REAL_LABEL

st.set_page_config(page_title='Условный сценарий',layout='wide')
st.title('Условный сценарий')
st.caption('Проверенный финансовый результат → проверка доступности данных → виртуальный пример.')
mode=st.selectbox('Выберите источник сценария',['Собственные искусственные данные','Проверка реального источника'],index=None,placeholder='Выберите явно')
ctx=None;params=None;did=None;decision='';error=None
try:
    if mode=='Собственные искусственные данные':
        st.warning(LABEL);st.caption('Вымышленная группа, выручка100 и120 RUB за полные2023/2024. Временная доступность, актив, календарь и цены придуманы для проверки программы. Это не рыночная доходность.')
        ctx=load_own_context();example=read_json(ROOT/'data/scenarios/kp3_scenario_v1/request_example.json');p=example['parameters'];left,right=st.columns(2)
        with left:
            capital=st.text_input('Начальный капитал, RUB',p['initial_cash']);allocation=st.text_input('Доля капитала, от0 до1',p['allocation']);threshold=st.text_input('Порог роста выручки, %',p['threshold_pct']);decision=st.text_input('Момент решения с часовым поясом',example['decision_at'])
        with right:
            fee=st.text_input('Комиссия за операцию, RUB',p['fee_fixed']);slip=st.text_input('Проскальзывание, базисные пункты',p['slippage_bps']);lot=st.number_input('Размер лота',min_value=1,max_value=1000000,value=1,step=1)
        sessions=ctx.dataset['calendar']['sessions'];opens=[s['open']for s in sessions];closes=[s['close']for s in sessions];a,b=st.columns(2)
        with a:start=st.selectbox('Начало окна',opens,index=0,format_func=lambda x:datetime.fromisoformat(x).strftime('%d.%m.%Y %H:%M'))
        with b:end=st.selectbox('Конец окна',closes,index=len(closes)-1,format_func=lambda x:datetime.fromisoformat(x).strftime('%d.%m.%Y %H:%M'))
        params=dict(initial_cash=capital,allocation=allocation,threshold_pct=threshold,fee_fixed=fee,slippage_bps=slip,lot_size=int(lot),window_start=start,window_end=end)
        st.caption('Правило: точный относительный рост строго выше порога. Покупка — на первом объявленном открытии строго после решения, продажа — в конце окна. Это собственный календарь, не календарь биржи.')
    elif mode=='Проверка реального источника':
        st.info(REAL_LABEL);st.caption('Проверка не запускает сделки. Неизвестная публикация exact-PDF, отсутствие допустимых цен и календаря сохраняют blocked.')
        setup=os.environ.get('KP3_SCENARIO_REAL_CONTEXT')
        if not setup:raise ValueError('real_setup_missing')
        service=load_service_context(setup);ctx=ScenarioContext(service,ROOT/'tmp/scenario-runs');cat=service.calculation.catalog;docs={d['document_id']:d for d in cat['documents']};orgs={o['organization_id']:o for o in cat['organizations']}
        did=st.selectbox('Официальная exact-версия',list(docs),index=None,placeholder='Выберите документ',format_func=lambda key:orgs[docs[key]['organization_id']]['name']+' · '+docs[key]['report_period']['start']+' — '+docs[key]['report_period']['end'])
        decision=st.text_input('Момент проверки с часовым поясом',value='',placeholder='Например: 2026-11-10T12:00:00+03:00')
        st.caption('Сначала фиксированный B проверит выручку и её относительное изменение по выбранной версии; затем общий scenario gate проверит готовность. Модель не вызывается.')
except Exception as e:error=getattr(e,'code','scenario_setup_unavailable');st.error('Техническая ошибка подготовки: '+error)

fingerprint=digest(dict(mode=mode,params=params,did=did,decision=decision,context=None if ctx is None else ctx.identity,error=error))
if st.session_state.get('scenario_fingerprint')!=fingerprint:st.session_state['scenario_result']=None;st.session_state['scenario_fingerprint']=fingerprint
ready=ctx is not None and error is None and mode is not None and(mode!='Проверка реального источника'or did is not None and bool(decision))
if st.button('Рассчитать виртуальный сценарий'if mode=='Собственные искусственные данные'else 'Проверить допуск',disabled=not ready,type='primary'):
    try:
        ctx.validate()
        if mode=='Собственные искусственные данные':fin=own_financial(ctx,'scenario-fin-'+uuid4().hex);data_mode='own_synthetic'
        else:
            d=docs[did];fs=[next(f for f in cat['facts']if f['document_id']==did and f['metric_id']=='revenue'and f['origin_role']==role)for role in ['comparative_period','reported_period']];src=dict(kind='form',form=dict(schema_version='kp3-form-0.1',input_id='scenario-real-selection',original_question='Проверка относительного изменения выручки перед допуском сценария.',fields=dict(organization=d['organization_id'],operation_id='relative_change_v1',metric_ids=['revenue'],periods=[f['period']for f in fs],documents=[dict(document_id=did,version_id=d['version_id'])],mode='snapshot'),assumptions=[]));fin=execute(src,'B',ctx.service);data_mode='real_source_readiness'
        request=dict(schema_version=REQUEST,financial_run_id=fin['run_id'],data_mode=data_mode,decision_at=decision,parameters=params);st.session_state['scenario_result']=execute_scenario(fin,request,ctx)
    except Exception as e:st.session_state['scenario_result']=None;st.error('Техническая ошибка: '+getattr(e,'code','scenario_execution_failed'))

out=st.session_state.get('scenario_result')
if out:
    try:ctx.validate()
    except Exception as e:st.session_state['scenario_result']=None;out=None;st.error('Источник или подготовка изменились: '+getattr(e,'code','scenario_context_changed'))
if out:
    st.subheader(out['label']);fin=out['financial']
    if fin and fin['status']=='verified':st.write('Финансовый результат: '+fin['financial_result']['display_value']+' '+(' %'if fin['financial_result']['result_unit']['kind']=='percent'else fin['financial_result']['result_unit']['currency']))
    if out['status']=='completed':
        st.success('Сигнал выполнен'if out['signal']else 'Сигнала нет: рост не выше порога');main=out['scenario'];a,b,c=st.columns(3);a.metric('Итоговый капитал, RUB',main['final_equity']);b.metric('Изменение капитала, RUB',main['pnl']);c.metric('Максимальная просадка, %',main['max_drawdown']['percent'])
        paths={'Сценарий':main,'Деньги':out['comparisons']['cash_no_interest'],'Удержание':out['comparisons']['hold_same_allocation']};chart=[dict(Момент=r['at'],**{label:float(p['ledger'][i]['equity'])for label,p in paths.items()})for i,r in enumerate(main['ledger'])];st.line_chart(pd.DataFrame(chart),x='Момент',y=list(paths),height=280)
        st.caption('Кривая — на вымышленных ценах. Удержание использует ту же долю, допустимый момент входа и расходы; деньги — без процентов. Просадка учитывает первоначальный капитал.')
        st.dataframe(pd.DataFrame([dict(Вариант=k,Капитал_RUB=p['final_equity'],Результат_RUB=p['pnl'],Комиссии_RUB=p['fees'],Проскальзывание_RUB=p['slippage_cost'])for k,p in paths.items()]),hide_index=True)
        st.subheader('Журнал виртуальных операций');st.dataframe(pd.DataFrame(main['ledger'])[['at','action','raw_price','traded_quantity','commission','cash','quantity','equity']].rename(columns=dict(at='Момент',action='Действие',raw_price='Цена',traded_quantity='Объём операции',commission='Комиссия',cash='Деньги',quantity='Количество',equity='Капитал')),hide_index=True)
        if main['no_trade_reason']:st.info('Операций нет: '+main['no_trade_reason'])
    elif out['status']=='blocked':
        st.warning('Сценарий заблокирован: '+out['reason_code'])
        if out['eligibility']:st.write('Причины: '+', '.join(out['eligibility']['reason_codes']))
    else:st.error('Техническая ошибка: '+out['reason_code'])
    with st.expander('Доказательства, временной допуск и trace'):
        st.json(dict(financial=out['financial'],eligibility=out['eligibility'],trace=out['trace'],run_id=out['run_id']))
