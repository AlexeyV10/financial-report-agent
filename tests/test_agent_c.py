"""Own scripted controller tests, never reported as actual LLM calls or unseen cases."""
from copy import deepcopy
from dataclasses import dataclass
import json,time,unittest
from pathlib import Path
import sys,tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from test_service_b import fixture,source
from financial_assistant.agent_c import execute_c,_validate_action,schemas
from financial_assistant.agent_contracts_v2 import AgentLimits,validate_agent_answer
from financial_assistant.agent_model_v2 import LocalAgentModel,load_agent_model,unique
from financial_assistant.contracts_v2 import ContractError,digest
from financial_assistant.input_binding import resolve_input
from financial_assistant.russian_input import parse_form


def schema_action(o,index=0,top=None):
    spec=o['tool_schemas']['oneOf'][index];props=spec['properties']['arguments']['properties'];args={k:deepcopy(s['const'])if 'const'in s else deepcopy(s['enum'][0])if 'enum'in s else top or s['maximum']for k,s in props.items()}
    if spec['properties']['tool']['const']=='calculate':
        refs=[]
        for r in o['task']['required_contexts']:
            f=next(f for f in o['candidates']if all(f[k]==r[k]for k in ['metric_id','definition_id','period'])and dict(currency=f['currency'],scale=f['scale'])==r['source_unit']);refs.append(dict(role=r['role'],fact_id=f['fact_id']))
        args['inputs']=refs
    return dict(tool=spec['properties']['tool']['const'],arguments=args)


@dataclass
class Scripted:
    actions:object=None
    strategy:str='smart'
    @property
    def metadata(self):return dict(kind='mock',adapter='own-scripted-controller-tests',strategy=self.strategy)
    def decide(self,o,timeout):
        n=o['limits']['max_calls']-o['remaining_calls'];choices=o['tool_schemas']['oneOf']
        if self.strategy=='sleep':time.sleep(2)
        if self.strategy=='bad_reply':return dict(unexpected=True)
        if self.actions is not None and n<len(self.actions):action=deepcopy(self.actions[n])
        elif self.strategy=='wrong_finish'and o['state']=='terminal'and n==3:action=dict(tool='finish',arguments=dict(receipt_id='old-receipt'))
        elif self.strategy=='after_calc_search'and o['state']=='terminal'and n==3:action=dict(tool='search_evidence',arguments=dict(query=o['search_keywords'],top_k=32))
        elif self.strategy=='never_finish'and o['state']=='terminal':action=dict(tool='finish',arguments=dict(receipt_id='never-current'))
        elif self.strategy=='loop':action=dict(tool='search_evidence',arguments=dict(query=o['search_keywords'],top_k=32))
        elif self.strategy=='top1'and n==0:action=schema_action(o,top=1)
        elif self.strategy=='refresh'and n in [0,2]and choices[0]['properties']['tool']['const']=='search_evidence':action=schema_action(o,top=2 if n==0 else 32)
        else:
            # Prefer unfetched IDs/calculation/finish; search only when required.
            i=next((i for i,s in enumerate(choices)if s['properties']['tool']['const']!='search_evidence'),0);action=schema_action(o,i)
        if self.strategy=='wrong_roles'and action['tool']=='calculate'and n==3:
            ids=[r['fact_id']for r in action['arguments']['inputs']][::-1]
            for r,fid in zip(action['arguments']['inputs'],ids):r['fact_id']=fid
        return dict(action=action,usage=dict(input_tokens=None,output_tokens=None),chat_requests=0,error=None)


class FakeLocalTransport(Scripted):
    """Explicit unit transport fake; NOT a real LLM result or part of its denominator."""
    @property
    def metadata(self):return dict(kind='local_llm',adapter='unit-transport-fake-not-real')
    def probe(self,timeout):return dict(unit_fake=True)
    def decide(self,o,timeout):
        if self.strategy=='transport_error':return dict(action=None,usage=dict(input_tokens=None,output_tokens=None),chat_requests=1,error='adapter_unavailable')
        r=super().decide(o,timeout);r['chat_requests']=1;return r


class ObserveSelection(Scripted):
    def decide(self,o,timeout):
        assert all('fact_id'not in r for r in o['task']['required_contexts'])
        assert all('value'not in f for f in o['candidates'])
        if o['state']=='ready':assert not o['candidates']
        return super().decide(o,timeout)


class AgentCTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name);self.ctx=fixture(self.dir)
    def run_c(self,s=None,adapter=None,**kw):return execute_c(s or source(self.ctx),self.ctx,adapter or Scripted(),**kw)
    def no_number(self,a):self.assertIsNone(a['financial_result'],a);self.assertIsNone(a['financial_status'],a);validate_agent_answer(a)
    def test_five_operations_roles_and_values(self):
        for op,value in [('direct_fact_v1','120'),('absolute_change_v1','20'),('relative_change_v1','20.00'),('scale_v1','0.12'),('operating_margin_v1','15.00')]:
            a=self.run_c(source(self.ctx,op));self.assertEqual(a['financial_status'],'answered',a);self.assertEqual(a['financial_result']['display_value'],value);self.assertEqual(a['model_calls'],0);self.assertEqual(a['agent']['mock_decisions'],4 if op in {'direct_fact_v1','scale_v1'}else 5);validate_agent_answer(a)
    def test_other_metrics_not_literal_two_revenues(self):
        for metric in ['operating_profit','operating_cash_flow']:
            a=self.run_c(source(self.ctx,metric=metric));self.assertEqual(a['financial_status'],'answered',a);self.assertEqual(a['financial_result']['inputs'][0]['metric_id'],metric)
    def test_top1_partial_finish_new_qa07_mechanic(self):
        a=self.run_c(source(self.ctx,'relative_change_v1'),limits=AgentLimits(max_search_results=1));self.assertTrue(a['agent']['finished'],a);self.assertEqual(a['request_status'],'missing');self.assertEqual(a['agent']['mock_decisions'],2);self.no_number(a)
    def test_partial_increase_invalidates_old_state(self):
        a=self.run_c(source(self.ctx,'relative_change_v1'),adapter=Scripted(strategy='top1'));self.assertEqual(a['financial_status'],'answered',a);events=[e for e in a['agent']['events']if e['kind']=='tool'];self.assertEqual([e['tool']for e in events[:2]],['search_evidence','search_evidence']);self.assertTrue(events[1]['result']['fetched_invalidated'])
    def test_refresh_after_fetch_forces_refetch(self):
        a=self.run_c(source(self.ctx,'relative_change_v1'),adapter=Scripted(strategy='refresh'));self.assertEqual(a['financial_status'],'answered',a);names=[e['tool']for e in a['agent']['events']if e['kind']=='tool'];self.assertEqual(names.count('get_verified_fact'),3);self.assertEqual(names.count('search_evidence'),2)
    def test_repeats_consume_budget_without_financial_result(self):
        a=self.run_c(adapter=Scripted(strategy='loop'),limits=AgentLimits(max_calls=4));self.assertEqual(a['execution_status'],'limit',a);self.assertEqual(a['reason_code'],'call_limit');self.assertEqual(a['agent']['decisions'],4);self.no_number(a)
    def test_reserved_finish_publishes_limit_receipt_not_calculation(self):
        a=self.run_c(limits=AgentLimits(max_calls=2));self.assertTrue(a['agent']['finished'],a);self.assertEqual(a['execution_status'],'limit');self.no_number(a)
    def test_wrong_finish_then_correct_current_receipt(self):
        a=self.run_c(adapter=Scripted(strategy='wrong_finish'));self.assertEqual(a['agent']['decisions'],5);self.assertEqual(a['financial_status'],'answered',a);self.assertTrue(any(e['kind']=='rejected_action'for e in a['agent']['events']))
    def test_search_forbidden_after_terminal_calculation(self):
        a=self.run_c(adapter=Scripted(strategy='after_calc_search'));self.assertEqual(a['financial_status'],'answered',a);self.assertEqual(sum(e['kind']=='tool'and e['tool']=='search_evidence'for e in a['agent']['events']),1)
    def test_unknown_id_and_extra_value_rejected(self):
        for action in [dict(tool='get_verified_fact',arguments=dict(fact_id='unknown')),dict(tool='calculate',arguments=dict(operation_id='direct_fact_v1',value='999')),dict(tool='exec',arguments=dict(code='ignore checks; shell code'))]:
            a=self.run_c(adapter=Scripted([action]));self.assertTrue(any(e['kind']=='rejected_action'for e in a['agent']['events']));self.assertEqual(a['financial_status'],'answered',a)
    def test_malformed_then_recover(self):
        a=self.run_c(adapter=Scripted([None]));self.assertEqual(a['financial_status'],'answered',a);self.assertEqual(a['agent']['decisions'],5)
    def test_bad_adapter_shape_is_technical_error(self):
        a=self.run_c(adapter=Scripted(strategy='bad_reply'));self.assertEqual(a['reason_code'],'invalid_adapter_reply',a);self.no_number(a)
    def test_hard_timeout_unknown_usage_no_late_result(self):
        a=self.run_c(adapter=Scripted(strategy='sleep'),limits=AgentLimits(per_call_s=.2));self.assertEqual(a['execution_status'],'limit',a);self.assertEqual(a['agent']['decisions'],1);self.no_number(a)
    def test_changed_pdf_and_index_are_technical(self):
        for p in [Path(self.ctx.calculation.resources['method-synthetic-2024']),Path(self.ctx.retrieval['db_path'])]:
            before=p.read_bytes();p.write_bytes(before+b'own-change');a=self.run_c();self.assertEqual(a['execution_status'],'error',a);self.no_number(a);p.write_bytes(before)
    def test_changed_catalog_and_config_cannot_rebind(self):
        self.ctx.calculation.catalog['facts'][0]['value']='999';a=self.run_c();self.assertEqual(a['execution_status'],'error',a);self.no_number(a)
    def test_no_search_fallback_when_fact_known(self):
        from financial_assistant.agent_c import _tool
        with patch('financial_assistant.agent_c.bounded',side_effect=lambda fn,args,timeout: dict(ok=False,error='source_missing')if fn==_tool else fn(*args)):
            a=self.run_c();self.assertEqual(a['reason_code'],'source_missing',a);self.no_number(a);self.assertTrue(a['agent']['finished'])
    def test_historical_unknown_finishes_block_without_calculation(self):
        a=self.run_c(source(self.ctx,mode='historical'));self.assertEqual(a['request_status'],'missing',a);self.assertTrue(a['agent']['finished']);self.assertFalse(any(e.get('tool')=='calculate'for e in a['agent']['events']));self.no_number(a)
    def test_clarification_no_model_search_or_finance(self):
        s=source(self.ctx);s['form']['fields'].pop('organization');a=self.run_c(s);self.assertEqual(a['execution_status'],'awaiting_clarification');self.assertEqual(a['agent']['decisions'],0);self.no_number(a)
    def test_clarification_preserves_original_history(self):
        s=source(self.ctx);s['form']['fields'].pop('organization');a=self.run_c(s,answers=[dict(organization='method_synthetic_group')]);self.assertEqual(a['original_question'],s['form']['original_question']);self.assertEqual(len(a['normalized_input']['history']),1);self.assertEqual(a['financial_status'],'answered',a)
    def test_persisted_run_and_duplicate_no_overwrite(self):
        a=self.run_c(run_id='explicit-c');p=self.ctx.run_dir/a['saved_run']['resource_id'];b=p.read_bytes();self.assertEqual(json.loads(b),a);x=self.run_c(run_id='explicit-c');self.assertEqual(x['reason_code'],'run_id_exists');self.assertEqual(p.read_bytes(),b);self.no_number(x)
    def test_new_context_and_input_no_stale_answers(self):
        a=self.run_c();b=self.run_c(source(self.ctx,metric='operating_profit'));self.assertNotEqual(a['run_id'],b['run_id']);self.assertNotEqual(a['source_input_digest'],b['source_input_digest']);self.assertNotEqual(a['financial_result']['display_value'],b['financial_result']['display_value'])
    def test_invalid_limits_and_run_id(self):
        for lim in [AgentLimits(max_calls=1),AgentLimits(timeout_s=float('nan')),AgentLimits(max_search_results=33)]:
            a=self.run_c(limits=lim);self.assertEqual(a['reason_code'],'invalid_agent_limits');self.no_number(a)
        a=self.run_c(run_id='../bad');self.assertEqual(a['reason_code'],'invalid_run_id');self.no_number(a)
    def test_json_duplicate_keys_and_endpoint_pins(self):
        with self.assertRaises(ValueError):json.loads('{"tool":1,"tool":2}',object_pairs_hook=unique)
        c=load_agent_model(ROOT/'data/config/local_model.json');self.assertEqual(c.metadata['kind'],'local_llm')
    def test_wrong_money_operation_roles_are_rejected(self):
        req=resolve_input(parse_form(source(self.ctx)['form'],self.ctx.calculation.catalog),self.ctx.calculation.catalog,self.ctx.calculation.dictionary)['request'];sc=schemas(req,'searched',[r['fact_id']for r in req['inputs']],32,AgentLimits(),None,req['inputs'])
        for act in [dict(tool='calculate',arguments=dict(operation_id='relative_change_v1',inputs=[])),dict(tool='calculate',arguments=dict(operation_id=req['operation_id'],inputs=[dict(role='previous',fact_id=req['inputs'][0]['fact_id'])]))]:
            with self.assertRaises(ContractError):_validate_action(act,sc)
    def test_premise_preserved_and_only_checked_after_finish(self):
        s=source(self.ctx,'absolute_change_v1');s['form']['original_question']='Почему выручка снизилась?';a=self.run_c(s);self.assertEqual(a['assumption_checks'][0]['status'],'contradicted');self.assertEqual(a['assumption_checks'][0]['explanation_status'],'not_supported');self.assertEqual(a['original_question'],s['form']['original_question'])
        b=self.run_c(s,limits=AgentLimits(max_calls=2));self.assertEqual(b['assumption_checks'][0]['status'],'not_checked');self.no_number(b)
    def test_financial_refusals_finish_and_negative_op_half_up(self):
        for metric,values,op,expected,reason in [('revenue',[('revenue-2023-comparative','0')],'relative_change_v1',None,'nonpositive_base'),('operating_profit',[('operating_profit-2024','-1'),('revenue-2024','32')],'operating_margin_v1','-3.13','ok'),('revenue',[('revenue-2024','0')],'operating_margin_v1',None,'zero_denominator')]:
            with tempfile.TemporaryDirectory(dir=ROOT/'tmp')as td:
                ctx=fixture(Path(td),[dict(fact_id=k,value=v)for k,v in values]);a=execute_c(source(ctx,op,metric),ctx,Scripted());self.assertTrue(a['agent']['finished'],a);self.assertEqual(a['reason_code'],reason);self.assertEqual(a['financial_result']['display_value']if a['financial_result']else None,expected);validate_agent_answer(a)
    def test_units_periods_and_missing_fact_never_call_model(self):
        for key,value,status in [('source_unit',dict(currency='USD',scale=1),'conflict'),('periods',[dict(kind='duration',duration_type='quarter',start='2024-04-01',end='2024-06-30')],'missing')]:
            s=source(self.ctx);s['form']['fields'][key]=value;a=self.run_c(s);self.assertEqual(a['request_status'],status);self.assertEqual(a['agent']['decisions'],0);self.no_number(a)
    def test_automatic_candidate_stops_before_get_fact(self):
        from financial_assistant.agent_c import _tool
        hit=dict(source_kind='automatic',status='found',reason_code='ok',index_sha256='a'*64,results=[dict(evidence_id=None)])
        with patch('financial_assistant.agent_c.bounded',side_effect=lambda fn,args,timeout: dict(ok=True,hits=deepcopy(hit))if fn==_tool else fn(*args)):
            a=self.run_c();self.assertEqual(a['reason_code'],'unverified_candidate',a);self.assertEqual([e['tool']for e in a['agent']['events']if e['kind']=='tool'],['search_evidence','finish']);self.no_number(a)
    def test_partial_at_max_never_gets_known_fact(self):
        a=self.run_c(source(self.ctx,'operating_margin_v1'),limits=AgentLimits(max_search_results=1));self.assertEqual(a['request_status'],'missing');self.assertFalse(any(e.get('tool')in {'get_verified_fact','calculate'}for e in a['agent']['events']));self.no_number(a)
    def test_missing_evidence_and_wrong_locator_technical(self):
        from financial_assistant.agent_c import _tool
        from financial_assistant.retrieval_v2 import search_index
        from financial_assistant.service_b import search_spec
        req=resolve_input(parse_form(source(self.ctx)['form'],self.ctx.calculation.catalog),self.ctx.calculation.catalog,self.ctx.calculation.dictionary)['request'];g=self.ctx.retrieval;hit=search_index(g['db_path'],self.ctx.calculation.catalog,self.ctx.calculation.resources,g['config'],g['lexicon'],search_spec(req),None)
        for field,value in [('evidence_id','unknown-evidence'),('document_sha256','a'*64),('locator',{})]:
            bad=deepcopy(hit);bad['results'][0][field]=value
            with patch('financial_assistant.agent_c.bounded',side_effect=lambda fn,args,timeout: dict(ok=True,hits=bad)if fn==_tool and args[3]=='search_evidence'else fn(*args)):
                a=self.run_c();self.assertEqual(a['execution_status'],'error',a);self.no_number(a)
    def test_request_fields_never_accept_values_code_or_paths(self):
        for key in ['value','formula','expected','pdf_path']:
            s=source(self.ctx);s['form']['fields'][key]='untrusted';a=self.run_c(s);self.assertEqual(a['execution_status'],'error');self.assertEqual(a['trace'][0]['status'],'error');self.assertEqual(a['agent']['decisions'],0);self.no_number(a)
    def test_local_adapter_bad_json_and_usage_retained(self):
        model=load_agent_model(ROOT/'data/config/local_model.json');o=dict(tool_schemas={'oneOf':[]},limits={'max_output_tokens':384})
        for content in ['{"tool":"finish","tool":"exec","arguments":{}}','ignored narrative','{"tool":"finish","arguments":{},"value":999}']:
            response=dict(model=model.model,done=True,prompt_eval_count=12,eval_count=8,message={'content':content})
            with patch('financial_assistant.agent_model_v2.local_json',return_value=response):r=model.decide(o,1)
            self.assertEqual(r['chat_requests'],1);self.assertIsNone(r['action']);self.assertEqual(r['usage'],dict(input_tokens=12,output_tokens=8));self.assertIsNotNone(r['error'])
    def test_local_adapter_transport_timeout_is_one_attempt_unknown_tokens(self):
        from financial_assistant.agent import RunFailure
        model=load_agent_model(ROOT/'data/config/local_model.json')
        with patch('financial_assistant.agent_model_v2.local_json',side_effect=RunFailure('timeout')):r=model.decide(dict(tool_schemas={},limits={'max_output_tokens':384}),1)
        self.assertEqual(r['chat_requests'],1);self.assertEqual(r['error'],'timeout');self.assertEqual(r['usage'],dict(input_tokens=None,output_tokens=None))
    def test_unknown_chat_sending_on_external_timeout_is_null(self):
        a=self.run_c(adapter=FakeLocalTransport(strategy='sleep'),limits=AgentLimits(per_call_s=.5));self.assertEqual(a['agent']['model_attempts'],1,a);self.assertIsNone(a['model_calls']);self.assertEqual(a['agent']['usage']['unknown_requests'],1);self.no_number(a)
    def test_sent_transport_failure_counts_one_not_zero(self):
        a=self.run_c(adapter=FakeLocalTransport(strategy='transport_error'));self.assertEqual(a['model_calls'],1);self.assertEqual(a['agent']['usage']['unknown_usage'],1);self.assertEqual(a['execution_status'],'error');self.no_number(a)
    def test_computed_but_not_finished_never_publishes(self):
        a=self.run_c(adapter=Scripted(strategy='never_finish'));self.assertEqual(a['reason_code'],'call_limit');self.assertFalse(a['agent']['finished']);self.assertTrue(any(e.get('tool')=='calculate'for e in a['agent']['events']));self.no_number(a)
    def test_tampered_finish_receipt_rejected(self):
        a=self.run_c();a['agent']['receipt_id']='tampered'
        with self.assertRaises(ContractError):validate_agent_answer(a)
    def test_fact_ids_only_appear_after_search_without_values(self):
        a=self.run_c(source(self.ctx,'operating_margin_v1'),adapter=ObserveSelection());self.assertEqual(a['financial_status'],'answered',a)
    def test_wrong_role_assignment_consumes_call_then_recovers(self):
        a=self.run_c(source(self.ctx,'relative_change_v1'),adapter=Scripted(strategy='wrong_roles'));self.assertEqual(a['financial_status'],'answered',a);self.assertEqual(a['agent']['decisions'],6);self.assertTrue(any(e.get('reason_code')=='selected_binding_conflict'for e in a['agent']['events']))
    def test_calculate_schema_leaves_id_permutation_to_model(self):
        req=resolve_input(parse_form(source(self.ctx,'relative_change_v1')['form'],self.ctx.calculation.catalog),self.ctx.calculation.catalog,self.ctx.calculation.dictionary)['request'];sc=schemas(req,'searched',[r['fact_id']for r in req['inputs']],32,AgentLimits(),None,req['inputs']);calc=sc['oneOf'][-1];self.assertEqual(len(calc['properties']['arguments']['properties']['inputs']['enum']),2)


if __name__=='__main__':unittest.main()
