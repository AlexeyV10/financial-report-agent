"""Virtual own-data ledger, cash/hold comparisons and precisely defined drawdown."""
from decimal import Decimal,localcontext,ROUND_FLOOR
from fractions import Fraction
from .contracts_v2 import ContractError,instant,need,shape
from .scenario_contracts_v1 import LABEL,LEDGER,dec,money,floor_money,display


class ScenarioBlocked(ContractError):pass


def blocked(condition,code):
    if not condition:raise ScenarioBlocked(code)


def validate_dataset(d):
    shape(d,'schema_version dataset_id data_origin label publication_semantics financial_source instrument calendar prices');need(d['schema_version']=='kp3-scenario-dataset-0.1'and d['data_origin']=='self_created_synthetic'and d['label']==LABEL and d['publication_semantics']=='fictional_availability_only','synthetic_provenance_required')
    shape(d['financial_source'],'document_id version_id sha256 byte_length resource publication_digest');need(d['financial_source']['resource']=='own_financial_source.txt','untrusted_synthetic_resource');shape(d['instrument'],'instrument_id currency corporate_actions');need(d['instrument']==dict(instrument_id='SYNTH12_ASSET',currency='RUB',corporate_actions='none_in_declared_fixture'),'unsupported_synthetic_instrument')
    c=d['calendar'];shape(c,'calendar_id timezone synthetic sessions');need(c['synthetic']is True and c['timezone']=='Europe/Moscow','synthetic_calendar_required');need(type(c['sessions'])is list and 1<=len(c['sessions'])<=128,'invalid_calendar');ids=[];last=None
    for s in c['sessions']:
        shape(s,'session_id open close');a,b=instant(s['open']),instant(s['close']);need(a<b and a.utcoffset().total_seconds()==b.utcoffset().total_seconds()==10800,'invalid_session');need(last is None or a>last,'overlapping_sessions');last=b;ids.append(s['session_id'])
    need(len(ids)==len(set(ids)),'duplicate_session_id');p=d['prices'];shape(p,'snapshot_id synthetic currency instrument_id rights observations');need(p['synthetic']is True and p['currency']=='RUB'and p['instrument_id']=='SYNTH12_ASSET'and p['rights']=='self_created','synthetic_prices_required');need(type(p['observations'])is list and len(p['observations'])<=256,'invalid_price_series')
    seen=set();bars={instant(s[k])for s in c['sessions']for k in ['open','close']}
    for row in p['observations']:
        shape(row,'at price');t=instant(row['at']);need(t not in seen,'duplicate_price');need(t in bars,'price_not_at_declared_bar');seen.add(t);price=dec(row['price']);need(Decimal('.01')<=price<=1000000000 and price==money(price),'invalid_price')


def schedule(dataset,request):
    p=request['parameters'];start,end=instant(p['window_start']),instant(p['window_end']);decision=instant(request['decision_at']);sessions=dataset['calendar']['sessions'];prices={instant(r['at']):dec(r['price'])for r in dataset['prices']['observations']}
    blocked(start in {instant(s['open'])for s in sessions}and end in {instant(s['close'])for s in sessions},'window_not_on_declared_session')
    times=[instant(s[k])for s in sessions for k in ['open','close']if start<=instant(s[k])<=end];entries=[instant(s['open'])for s in sessions if decision<instant(s['open'])<=end and instant(s['open'])>=start]
    blocked(entries,'no_future_session_open');blocked(all(t in prices for t in times),'price_missing');return times,entries[0],end,prices


def path(parameters,times,entry,exit,prices,trade,reason,fixed_quantity=None):
    with localcontext()as ctx:
        ctx.prec=80;capital=dec(parameters['initial_cash']);allocation=dec(parameters['allocation']);fee=dec(parameters['fee_fixed']);slip=dec(parameters['slippage_bps'])/10000;lot=parameters['lot_size'];cash=capital;quantity=0;fees=Decimal(0);slippage=Decimal(0);ledger=[];peak=capital;max_dd=Fraction(0);peak_at=None;trough_at=None;peak_time=times[0];chosen=0
        def record(at,action,raw,effective=None,traded=0,gross=Decimal(0),commission=Decimal(0),adverse=Decimal(0),why='mark'):
            nonlocal peak,max_dd,peak_at,trough_at,peak_time
            equity=money(cash+Decimal(quantity)*raw)
            if equity>peak:peak=equity;peak_time=at
            drawdown=Fraction(peak-equity)/Fraction(peak)
            if drawdown>max_dd:max_dd=drawdown;peak_at=peak_time;trough_at=at
            ledger.append(dict(at=at.isoformat(),action=action,reason_code=why,raw_price=display(raw),effective_price=None if effective is None else display(effective),traded_quantity=traded,gross=display(gross),commission=display(commission),slippage_cost=display(adverse),cash=display(money(cash)),quantity=quantity,equity=display(equity)))
        for at in times:
            raw=prices[at]
            if at==entry and trade:
                effective=raw*(1+slip);budget=max(Decimal(0),floor_money(min(capital*allocation,capital-fee)));q=int((budget/effective/lot).to_integral_value(rounding=ROUND_FLOOR))*lot if budget>0 else 0
                if fixed_quantity is not None:q=fixed_quantity
                need(type(q)is int and q>=0 and q%lot==0,'invalid_fixed_exposure');gross=money(Decimal(q)*effective);blocked(q==0 or gross+fee<=cash,'insufficient_entry_cash');chosen=q
                if q:
                    cash-=gross+fee;quantity=q;fees+=fee;adverse=gross-money(Decimal(q)*raw);slippage+=adverse;record(at,'buy',raw,effective,q,gross,fee,adverse,'signal_entry')
                else:record(at,'no_trade',raw,why='insufficient_for_lot')
            elif at==exit and quantity:
                effective=raw*(1-slip);q=quantity;gross=money(Decimal(q)*effective);blocked(cash+gross-fee>=0,'insufficient_exit_cash');cash+=gross-fee;quantity=0;fees+=fee;adverse=money(Decimal(q)*raw)-gross;slippage+=adverse;record(at,'sell',raw,effective,q,gross,fee,adverse,'window_exit')
            else:record(at,'mark',raw,why=reason)
        need(quantity==0,'position_not_closed');dd=Decimal(max_dd.numerator)/Decimal(max_dd.denominator)*100
        return dict(schema_version=LEDGER,label=LABEL,entry_at=entry.isoformat(),exit_at=exit.isoformat(),entry_quantity=chosen,no_trade_reason=None if chosen else reason if not trade else 'insufficient_for_lot',ledger=ledger,final_cash=display(money(cash)),final_quantity=quantity,final_equity=display(money(cash)),pnl=display(money(cash-capital)),return_pct=display(money((cash/capital-1)*100)),fees=display(money(fees)),slippage_cost=display(money(slippage)),max_drawdown=dict(ratio=dict(numerator=str(max_dd.numerator),denominator=str(max_dd.denominator)),percent=display(money(dd)),peak_at=None if peak_at is None else peak_at.isoformat(),trough_at=None if trough_at is None else trough_at.isoformat(),definition='max((running_peak_equity - equity) / running_peak_equity), including initial capital'))


def simulate_paths(dataset,request,signal):
    times,entry,exit,prices=schedule(dataset,request);p=request['parameters'];main=path(p,times,entry,exit,prices,signal,'signal_false');hold=path(p,times,entry,exit,prices,True,'hold_same_allocation_same_eligible_entry');cash=path(p,times,entry,exit,prices,False,'cash_no_interest');return main,dict(cash_no_interest=cash,hold_same_allocation=hold)
