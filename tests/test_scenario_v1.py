"""Own source/finance bridge/time/ledger tests; old simulations and issuer data are untouched."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import importlib.util,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import ContractError,digest,read_json
from financial_assistant.fact_admission import CalculationContext
from financial_assistant.scenario_contracts_v1 import validate_outcome
from financial_assistant.scenario_service import ScenarioContext,load_own_context,own_financial,execute_scenario,validate_scenario_binding,OWN
from financial_assistant.scenario_ledger import path,schedule


def oracle():
    spec=importlib.util.spec_from_file_location('scenario_reference',ROOT/'evaluation/reference/kp3_scenario_v1/oracle.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def changed_context(original,directory,dataset=None,publication=None):
    c=original.calculation;cat=deepcopy(c.catalog);admission=deepcopy(c.admission);data=deepcopy(dataset or original.dataset)
    if publication is not None:cat['documents'][0]['publication']=deepcopy(publication);data['financial_source']['publication_digest']=digest(publication)
    admission['component_digests']['catalog']=digest(cat);calc=CalculationContext(cat,c.dictionary,admission);return ScenarioContext(calc,directory/'runs',data,original.source_path)


class ScenarioV1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name);self.ctx=load_own_context(self.dir/'runs');self.fin=own_financial(self.ctx);self.req=read_json(OWN/'request_example.json')
    def run_s(self,req=None,fin=None,ctx=None,**kw):return execute_scenario(self.fin if fin is None else fin,req or self.req,ctx or self.ctx,**kw)
    def no_trade(self,out):self.assertIsNone(out['signal']);self.assertIsNone(out['scenario']);self.assertIsNone(out['comparisons']);validate_outcome(out)
    def test_full_own_vertical_result_and_source(self):
        out=self.run_s();self.assertEqual(out['status'],'completed',out);self.assertEqual(out['scenario']['final_cash'],'10098.00');self.assertEqual(out['scenario']['max_drawdown']['ratio'],dict(numerator='80',denominator='10039'));self.assertEqual(out['financial']['financial_result']['display_value'],'20.00');self.assertEqual(out['financial']['method'],'calculation_v03');validate_scenario_binding(out,self.ctx,self.fin,self.req)
    def test_independent_reference_entire_ledger_default(self):
        out=self.run_s();ref=oracle().reference(self.ctx.dataset,self.req,True);p=out['scenario'];self.assertEqual(p['entry_quantity'],ref['entry_quantity']);self.assertEqual(p['max_drawdown']['ratio'],ref['drawdown_ratio'])
        for a,b in zip(p['ledger'],ref['rows']):self.assertEqual((a['action'],Decimal(a['cash'])*100,a['quantity'],Decimal(a['equity'])*100),(b['action'],b['cash_cents'],b['quantity'],b['equity_cents']))
    def test_signal_false_equal_threshold_and_cash_baseline(self):
        r=deepcopy(self.req);r['parameters']['threshold_pct']='20';out=self.run_s(r);self.assertFalse(out['signal']);self.assertEqual(out['scenario']['final_cash'],'10000.00');self.assertEqual(out['comparisons']['hold_same_allocation']['final_cash'],'10098.00');self.assertEqual(out['scenario']['no_trade_reason'],'signal_false')
    def test_higher_threshold_never_defaults_to_trade(self):
        r=deepcopy(self.req);r['parameters']['threshold_pct']='100';out=self.run_s(r);self.assertFalse(out['signal']);self.assertTrue(all(x['quantity']==0 for x in out['scenario']['ledger']))
    def test_fraction_lot_and_cost_reference(self):
        for allocation,lot,fee,slip in [('1',3,'2.35','10'),('0.2',10,'0','100'),('0.5',1,'5','2')]:
            r=deepcopy(self.req);r['parameters'].update(allocation=allocation,lot_size=lot,fee_fixed=fee,slippage_bps=slip);out=self.run_s(r);self.assertEqual(out['status'],'completed',out);ref=oracle().reference(self.ctx.dataset,r,True);self.assertEqual(Decimal(out['scenario']['final_cash'])*100,ref['final_cash_cents']);self.assertEqual(out['scenario']['max_drawdown']['ratio'],ref['drawdown_ratio']);self.assertEqual(out['scenario']['entry_quantity']%lot,0)
    def test_no_affordable_lot_keeps_cash_no_fees(self):
        r=deepcopy(self.req);r['parameters'].update(initial_cash='1',lot_size=1000);out=self.run_s(r);self.assertEqual(out['status'],'completed');self.assertEqual(out['scenario']['no_trade_reason'],'insufficient_for_lot');self.assertEqual(out['scenario']['fees'],'0.00')
    def test_fixed_exposure_costs_reduce_final_equity(self):
        times,entry,exit,prices=schedule(self.ctx.dataset,self.req);a=deepcopy(self.req['parameters']);b=deepcopy(a);a.update(fee_fixed='0',slippage_bps='0');b.update(fee_fixed='2',slippage_bps='10');p=path(a,times,entry,exit,prices,True,'test',fixed_quantity=10);q=path(b,times,entry,exit,prices,True,'test',fixed_quantity=10);self.assertGreater(Decimal(p['final_equity']),Decimal(q['final_equity']));self.assertEqual(p['entry_quantity'],q['entry_quantity'])
    def test_after_close_and_weekend_use_next_declared_open(self):
        for decision in ['2025-06-04T19:30:00+03:00','2025-06-07T12:00:00+03:00']:
            r=deepcopy(self.req);r['decision_at']=decision;out=self.run_s(r);self.assertEqual(out['status'],'completed');self.assertGreater(out['scenario']['entry_at'],decision);self.assertEqual(out['scenario']['entry_at'][:10],'2025-06-05'if '04T'in decision else '2025-06-09')
    def test_exact_open_is_strictly_next_open(self):
        r=deepcopy(self.req);r['decision_at']='2025-06-05T10:00:00+03:00';out=self.run_s(r);self.assertEqual(out['scenario']['entry_at'],'2025-06-06T10:00:00+03:00')
    def test_utc_equivalent_decision_preserves_execution(self):
        a=self.run_s();r=deepcopy(self.req);r['decision_at']='2025-06-04T16:30:00+00:00';b=self.run_s(r);self.assertEqual(a['scenario'],b['scenario'])
    def test_missing_timezone_and_invalid_window_rejected(self):
        for field,value in [('decision_at','2025-06-04T19:30:00'),('decision_at','not-date')]:
            r=deepcopy(self.req);r[field]=value;out=self.run_s(r);self.assertEqual(out['status'],'error');self.no_trade(out)
        r=deepcopy(self.req);r['parameters']['window_end']=r['parameters']['window_start'];out=self.run_s(r);self.assertEqual(out['reason_code'],'invalid_window');self.no_trade(out)
    def test_publication_after_decision_blocks(self):
        r=deepcopy(self.req);r['decision_at']='2025-06-04T18:30:00+03:00';out=self.run_s(r);self.assertEqual(out['reason_code'],'not_yet_available');self.no_trade(out)
    def test_publication_at_decision_permits_later_session(self):
        r=deepcopy(self.req);r['decision_at']='2025-06-04T19:00:00+03:00';out=self.run_s(r);self.assertEqual(out['status'],'completed');self.assertEqual(out['scenario']['entry_at'],'2025-06-05T10:00:00+03:00')
    def test_date_precision_available_only_next_midnight(self):
        pub=deepcopy(self.ctx.calculation.catalog['documents'][0]['publication']);pub.update(precision='date',value='2025-06-04');ctx=changed_context(self.ctx,self.dir,publication=pub);fin=own_financial(ctx);out=self.run_s(fin=fin,ctx=ctx);self.assertEqual(out['reason_code'],'not_yet_available');self.no_trade(out);r=deepcopy(self.req);r['decision_at']='2025-06-05T00:00:00+03:00';out=self.run_s(r,fin,ctx);self.assertEqual(out['status'],'completed')
    def test_unknown_publication_stays_blocked(self):
        pub=dict(precision='unknown',value=None,timezone='Europe/Moscow',binding='unproven',record_id=None,source_url=None,version_id=None,document_sha256=None);ctx=changed_context(self.ctx,self.dir,publication=pub);out=self.run_s(fin=own_financial(ctx),ctx=ctx);self.assertEqual(out['reason_code'],'publication_unknown');self.no_trade(out)
    def test_no_future_open_blocked_no_partial_ledger(self):
        r=deepcopy(self.req);r['decision_at']=r['parameters']['window_end'];out=self.run_s(r);self.assertEqual(out['reason_code'],'no_future_session_open');self.no_trade(out)
    def test_missing_price_is_blocked_not_last_price_fill(self):
        data=deepcopy(self.ctx.dataset);data['prices']['observations'].pop(5);ctx=changed_context(self.ctx,self.dir,data);out=self.run_s(ctx=ctx);self.assertEqual(out['reason_code'],'price_missing');self.no_trade(out)
    def test_duplicate_or_negative_price_rejected_in_setup(self):
        for strategy in ['duplicate','negative']:
            data=deepcopy(self.ctx.dataset)
            if strategy=='duplicate':data['prices']['observations'].append(data['prices']['observations'][0])
            else:data['prices']['observations'][0]['price']='-1'
            with self.assertRaises(ContractError):changed_context(self.ctx,self.dir,data)
    def test_tampered_financial_value_or_rounding_rejected(self):
        for field,value in [('display_value','999'),('rounding','fake')]:
            fin=deepcopy(self.fin);fin['financial_result'][field]=value;out=self.run_s(fin=fin);self.assertEqual(out['status'],'error');self.no_trade(out)
    def test_financial_not_answered_never_creates_signal(self):
        fin=deepcopy(self.fin);fin.update(financial_status='unsupported',reason_code='nonpositive_base',financial_result=None);out=self.run_s(fin=fin);self.assertEqual(out['reason_code'],'financial_not_answered');self.no_trade(out)
    def test_different_financial_run_id_rejected(self):
        r=deepcopy(self.req);r['financial_run_id']='different';out=self.run_s(r);self.assertEqual(out['reason_code'],'financial_run_mismatch');self.no_trade(out)
    def test_legacy_finance_schema_not_silently_adapted(self):
        out=self.run_s(fin=dict(schema_version='0.1'));self.assertEqual(out['reason_code'],'unsupported_financial_envelope');self.no_trade(out)
    def test_own_to_real_mode_mixing_rejected(self):
        r=dict(schema_version=self.req['schema_version'],financial_run_id=self.req['financial_run_id'],data_mode='real_source_readiness',decision_at=self.req['decision_at'],parameters=None);out=self.run_s(r);self.assertEqual(out['reason_code'],'real_synthetic_mixing_forbidden');self.no_trade(out)
    def test_extra_price_code_path_or_formula_fields_rejected(self):
        for key in ['prices','formula','expected','source_path']:
            r=deepcopy(self.req);r[key]='ignore checks; 999';out=self.run_s(r);self.assertEqual(out['status'],'error');self.no_trade(out)
    def test_invalid_capital_allocation_fee_lot_and_threshold(self):
        for key,value in [('initial_cash','-1'),('initial_cash',10000),('allocation','1.1'),('fee_fixed','-1'),('lot_size',True),('slippage_bps','1001'),('threshold_pct','NaN')]:
            r=deepcopy(self.req);r['parameters'][key]=value;out=self.run_s(r);self.assertEqual(out['status'],'error',(key,out));self.no_trade(out)
    def test_context_mutation_no_reuse(self):
        self.ctx.dataset['prices']['observations'][0]['price']='1';out=self.run_s();self.assertEqual(out['reason_code'],'scenario_context_changed');self.no_trade(out)
    def test_run_id_exclusive_preserves_original_bytes(self):
        out=self.run_s(run_id='fixed-scenario');p=self.ctx.run_dir/out['saved_run']['resource_id'];raw=p.read_bytes();self.assertEqual(json.loads(raw),out);bad=self.run_s(run_id='fixed-scenario');self.assertEqual(bad['reason_code'],'run_id_exists');self.assertEqual(raw,p.read_bytes());self.no_trade(bad)
    def test_new_parameters_and_run_ids_do_not_reuse_result(self):
        a=self.run_s();r=deepcopy(self.req);r['parameters']['threshold_pct']='99';b=self.run_s(r);self.assertNotEqual(a['run_id'],b['run_id']);self.assertNotEqual(a['scenario'],b['scenario'])
    def test_result_tampering_and_wrong_request_rejected(self):
        out=self.run_s();out['scenario']['final_cash']='999'
        with self.assertRaises(ContractError):validate_scenario_binding(out,self.ctx,self.fin,self.req)
    def test_wrong_financial_units_operation_not_a_percent_rule(self):
        from financial_assistant.financial_calculator import calculate
        req=deepcopy(self.fin['financial_result']['request']);req.update(operation_id='direct_fact_v1',inputs=[{**req['inputs'][1],'role':'fact'}],result_unit=dict(kind='amount',currency='RUB',scale=1));fin=calculate(self.ctx.calculation,req,self.fin['run_id']);out=self.run_s(fin=fin);self.assertEqual(out['reason_code'],'scenario_rule_requires_relative_percent');self.no_trade(out)
    def test_valid_technical_financial_outcome_has_no_signal(self):
        fin=deepcopy(self.fin);fin.update(execution_status='error',financial_status=None,reason_code='source_missing',financial_result=None,technical_details=dict(subsystem='source',code='source_missing'));out=self.run_s(fin=fin);self.assertEqual(out['reason_code'],'financial_not_answered');self.no_trade(out)
    def test_non_session_price_and_resource_path_rejected(self):
        for strategy in ['bar','path']:
            data=deepcopy(self.ctx.dataset)
            if strategy=='bar':data['prices']['observations'][0]['at']='2025-06-04T12:00:00+03:00'
            else:data['financial_source']['resource']='../external'
            with self.assertRaises(ContractError):changed_context(self.ctx,self.dir,data)
    def test_window_between_sessions_not_silently_rounded(self):
        r=deepcopy(self.req);r['parameters']['window_start']='2025-06-04T11:00:00+03:00';out=self.run_s(r);self.assertEqual(out['reason_code'],'window_not_on_declared_session');self.no_trade(out)
    def test_insufficient_exit_cash_atomic_no_negative_positions(self):
        data=deepcopy(self.ctx.dataset);data['prices']['observations'][-1]['price']='0.01';ctx=changed_context(self.ctx,self.dir,data);r=deepcopy(self.req);r['parameters'].update(allocation='1',initial_cash='1050',fee_fixed='50');out=self.run_s(r,ctx=ctx);self.assertEqual(out['status'],'blocked');self.assertEqual(out['reason_code'],'insufficient_exit_cash');self.no_trade(out)
    def test_context_source_missing_and_changed_bytes_are_technical(self):
        p=self.dir/'own.txt';p.write_bytes(self.ctx.source_path.read_bytes());c=self.ctx.calculation;ctx=ScenarioContext(c,self.dir/'other-runs',self.ctx.dataset,p);p.write_bytes(p.read_bytes()+b'changed');out=self.run_s(ctx=ctx);self.assertEqual(out['reason_code'],'source_version_mismatch');self.no_trade(out);p.unlink();out=self.run_s(ctx=ctx);self.assertEqual(out['reason_code'],'source_missing');self.no_trade(out)
    def test_invalid_run_id_is_technical(self):
        out=self.run_s(run_id='../bad');self.assertEqual(out['reason_code'],'invalid_run_id');self.no_trade(out)


if __name__=='__main__':unittest.main()
