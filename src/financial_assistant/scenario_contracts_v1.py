"""Explicit scenario contracts; not a migration of legacy scenario0.1 or financial formulas."""
from decimal import Decimal,ROUND_HALF_UP,ROUND_FLOOR
from .contracts_v2 import identifier,instant,need,number,shape

REQUEST='kp3-scenario-request-0.1'
OUTCOME='kp3-scenario-outcome-0.1'
ELIGIBILITY='kp3-scenario-eligibility-0.1'
LEDGER='kp3-scenario-ledger-0.1'
LABEL='ИСКУССТВЕННЫЕ ДАННЫЕ / ВИРТУАЛЬНЫЙ СЦЕНАРИЙ'
REAL_LABEL='ПРОВЕРКА РЕАЛЬНОГО ИСТОЧНИКА / ТОРГОВЛИ НЕТ'
STAGES=['financial_validation','eligibility','ledger','result_validation','persistence']


def dec(value):
    need(type(value)is str and len(value)<=40,'scenario_decimal_string_required');return number(value)


def money(value):return value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
def floor_money(value):return value.quantize(Decimal('.01'),rounding=ROUND_FLOOR)
def display(value):return format(value,'f')


def validate_request(r):
    shape(r,'schema_version financial_run_id data_mode decision_at parameters');need(r['schema_version']==REQUEST,'unsupported_scenario_request');identifier(r['financial_run_id']);instant(r['decision_at'])
    need(r['data_mode']in {'own_synthetic','real_source_readiness'},'invalid_scenario_mode')
    if r['data_mode']=='real_source_readiness':need(r['parameters']is None,'real_synthetic_mixing_forbidden');return
    p=r['parameters'];shape(p,'initial_cash allocation threshold_pct fee_fixed slippage_bps lot_size window_start window_end')
    cash,allocation,threshold,fee,slip=[dec(p[k])for k in ['initial_cash','allocation','threshold_pct','fee_fixed','slippage_bps']]
    need(0<cash<=1000000000 and money(cash)==cash,'invalid_capital');need(0<allocation<=1,'invalid_allocation');need(0<=threshold<=100,'invalid_threshold');need(0<=fee<=1000000 and money(fee)==fee,'invalid_fee');need(0<=slip<=1000,'invalid_slippage');need(type(p['lot_size'])is int and 1<=p['lot_size']<=1000000,'invalid_lot_size')
    start,end=instant(p['window_start']),instant(p['window_end']);need(start<end,'invalid_window');need(start<=instant(r['decision_at'])<=end,'decision_outside_window')


def validate_outcome(o):
    shape(o,'schema_version run_id status reason_code data_mode label request context_digest financial eligibility signal scenario comparisons trace saved_run model_calls')
    need(o['schema_version']==OUTCOME and o['model_calls']==0,'invalid_scenario_outcome');identifier(o['run_id']);need(o['status']in {'completed','blocked','error'},'invalid_scenario_status');need([t['stage']for t in o['trace']]==STAGES,'incomplete_scenario_trace')
    need(all(t['run_id']==o['run_id']and t['status']in {'completed','blocked','error','skipped'}and t['elapsed_ms']>=0 for t in o['trace']),'invalid_scenario_trace')
    if o['status']!='completed':need(o['signal']is None and o['scenario']is None and o['comparisons']is None,'blocked_scenario_has_positions')
    else:
        need(o['data_mode']=='own_synthetic'and o['label']==LABEL and type(o['signal'])is bool,'real_trade_forbidden');need(o['eligibility']['status']=='eligible','scenario_not_eligible')
        for path in [o['scenario'],*o['comparisons'].values()]:
            need(path['schema_version']==LEDGER and path['label']==LABEL and path['final_quantity']==0,'invalid_scenario_ledger');need(all(dec(r['cash'])>=0 and type(r['quantity'])is int and r['quantity']>=0 for r in path['ledger']),'negative_cash_or_short')
