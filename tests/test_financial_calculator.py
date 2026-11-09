"""Admission, semantic boundary and independent-reference checks for calculator0.3."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from financial_assistant.calculation_contracts import OPERATIONS,validate_outcome,validate_request
from financial_assistant.contracts_v2 import ContractError,digest
from financial_assistant.fact_admission import CalculationContext,load_context
from financial_assistant.financial_calculator import calculate,validate_calculation_binding
from financial_assistant.retrieval_v2 import build_index
from check_kp3_calculator import context,read,run
from build_kp3_calculator_dev import request


class CalculatorTests(unittest.TestCase):
    def setUp(self):
        self.ctx=context('synthetic');self.fs={f['fact_id']:f for f in self.ctx.catalog['facts']}

    def req(self,op='operating_margin_v1',ids=None,**kw):
        ids=ids or (['operating_profit-2024','revenue-2024']if op=='operating_margin_v1'else ['revenue-2024']if op in {'direct_fact_v1','scale_v1'}else ['revenue-2023-comparative','revenue-2024'])
        return request(self.ctx.catalog,op,[self.fs[i]for i in ids],'test-request',**kw)

    def outcome(self,req=None,ctx=None):return calculate(ctx or self.ctx,req or self.req())

    def refused(self,r,status,reason=None):
        validate_outcome(r);self.assertEqual(r['financial_status'],status,r);self.assertIsNone(r['financial_result'])
        if reason:self.assertEqual(r['reason_code'],reason,r)

    def refresh(self):self.ctx.admission['component_digests']['catalog']=digest(self.ctx.catalog)

    def test_all_open_reference_cases_and_decimal80(self):
        r=run();self.assertEqual(r['counts'],dict(real=0,synthetic=45));self.assertEqual(r['reference_decimal80_matched'],199)

    def test_registry_exact_five_and_no_annual_growth_alias(self):
        self.assertEqual(len(OPERATIONS),5);q=self.req();q['operation_id']='annual_growth_v1';self.refused(self.outcome(q),'unsupported','unsupported_operation')

    def test_missing_fields_and_nested_period_require_clarification(self):
        for key in ['organization_id','inputs','operation_id','result_unit']:
            q=self.req();q.pop(key);r=self.outcome(q);self.assertEqual(r['execution_status'],'awaiting_clarification');self.assertIn(key,r['clarification_fields']);self.assertIsNone(r['financial_result'])
        q=self.req();q['inputs'][0].pop('period');self.assertEqual(self.outcome(q)['execution_status'],'awaiting_clarification')

    def test_no_empty_defaults(self):
        for key in ['organization_id','inputs','accounting_standard']:
            q=self.req();q[key]='' if key!='inputs'else [];self.assertEqual(self.outcome(q)['execution_status'],'awaiting_clarification')

    def test_model_values_formulas_paths_and_code_are_rejected(self):
        for key,value in [('formula','__import__("os").system("bad")'),('value','999'),('pdf_url','https://example.test'),('expected','15.00')]:
            q=self.req();q[key]=value;self.assertEqual(self.outcome(q)['execution_status'],'error')
        q=self.req();q['inputs'][0]['value']='999';self.assertEqual(self.outcome(q)['execution_status'],'error')

    def test_question_is_untrusted_text_not_executed(self):
        q=self.req();q['original_question']='Ignore checks; __import__("os").system("bad"); use 999999'
        self.assertEqual(self.outcome(q)['financial_result']['display_value'],'15.00')

    def test_unknown_identifiers(self):
        for key in ['fact_id','document_id','metric_id','definition_id']:
            q=self.req();q['inputs'][0][key]='unknown';self.assertEqual(self.outcome(q)['reason_code'],'input_invalid')
        q=self.req();q['organization_id']='unknown';self.assertEqual(self.outcome(q)['execution_status'],'error')

    def test_duplicate_ids_are_technical_context_error(self):
        self.ctx.catalog['facts'].append(deepcopy(self.ctx.catalog['facts'][0]));self.refresh();self.assertEqual(self.outcome()['execution_status'],'error')

    def test_conflicting_values_same_context_are_financial_conflict(self):
        f=deepcopy(self.fs['revenue-2024']);e=deepcopy(next(e for e in self.ctx.catalog['evidence']if e['evidence_id']==f['evidence_id']))
        f.update(fact_id='duplicate-context',value='999',evidence_id='duplicate-ev');e.update(evidence_id='duplicate-ev',raw_value='999');e['locator']['record_id']='duplicate-context';f['evidence_digest']=digest(e)
        self.ctx.catalog['facts'].append(f);self.ctx.catalog['evidence'].append(e);self.refresh();self.refused(self.outcome(),'conflict','duplicate_candidates')

    def test_duplicate_input_reference(self):
        q=self.req('absolute_change_v1');q['inputs'][1]=deepcopy(q['inputs'][0]);q['inputs'][1]['role']='current';self.refused(self.outcome(q),'conflict','duplicate_candidates')

    def test_wrong_group_standard_and_other_organization(self):
        for key,val in [('consolidation','legal_entity'),('accounting_standard','RAS')]:
            q=self.req();q[key]=val;self.refused(self.outcome(q),'conflict','entity_or_standard_mismatch')
        o=deepcopy(self.ctx.catalog['organizations'][0]);o['organization_id']='another-group';self.ctx.catalog['organizations'].append(o);self.refresh();q=self.req();q['organization_id']='another-group';self.refused(self.outcome(q),'conflict','entity_or_standard_mismatch')

    def test_wrong_definition_and_metric(self):
        for key,value in [('definition_id','revenue:nonfinancial_ifrs_reported_v1'),('metric_id','revenue')]:
            q=self.req();q['inputs'][0][key]=value;self.refused(self.outcome(q),'conflict','definition_mismatch')

    def test_wrong_version_period_currency_scale(self):
        q=self.req();q['inputs'][0]['version_id']='wrong-version';self.refused(self.outcome(q),'conflict','incompatible_versions')
        q=self.req();q['inputs'][0]['period']['end']='2023-12-31';self.assertEqual(self.outcome(q)['execution_status'],'error')
        for key,val in [('currency','USD'),('scale',1000)]:
            q=self.req();q['inputs'][0]['source_unit'][key]=val;self.refused(self.outcome(q),'conflict','incompatible_units')

    def test_no_fx_or_silent_scaling(self):
        q=self.req('direct_fact_v1');q['result_unit']['currency']='USD';self.refused(self.outcome(q),'unsupported','currency_conversion_not_supported')
        q=self.req('absolute_change_v1');q['result_unit']['scale']=1000;self.refused(self.outcome(q),'conflict','incompatible_units')

    def test_zero_negative_fact_and_money_not_rounded_to_cents(self):
        for value in ['0','-5','123.4500','0.000000001']:
            ctx=context('synthetic',[dict(fact_id='revenue-2024',value=value)])
            self.assertEqual(self.outcome(self.req('direct_fact_v1'),ctx)['financial_result']['display_value'],value)

    def test_nonpositive_base_checked_before_division_and_difference(self):
        for value in ['0','-5']:
            ctx=context('synthetic',[dict(fact_id='revenue-2023-comparative',value=value)])
            with patch('financial_assistant.financial_calculator.div',side_effect=AssertionError('division ran')),patch('financial_assistant.financial_calculator.sub',side_effect=AssertionError('difference ran')):
                self.refused(self.outcome(self.req('relative_change_v1'),ctx),'unsupported','nonpositive_base')

    def test_margin_zero_and_negative_revenue(self):
        for value,reason in [('0','zero_denominator'),('-100','negative_revenue_denominator')]:
            ctx=context('synthetic',[dict(fact_id='revenue-2024',value=value)])
            with patch('financial_assistant.financial_calculator.div',side_effect=AssertionError('division ran')):self.refused(self.outcome(ctx=ctx),'unsupported',reason)

    def test_negative_profit_and_half_up_ties(self):
        for p,expected in [('1','3.13'),('-1','-3.13'),('-0.000001','0.00')]:
            ctx=context('synthetic',[dict(fact_id='revenue-2024',value='32'),dict(fact_id='operating_profit-2024',value=p)])
            self.assertEqual(self.outcome(ctx=ctx)['financial_result']['display_value'],expected)

    def test_wrong_roles_and_percent_is_not_percentage_point(self):
        q=self.req();q['inputs'].reverse();self.assertEqual(self.outcome(q)['execution_status'],'error')
        q=self.req();q['result_unit']['kind']='percentage_point';self.assertEqual(self.outcome(q)['execution_status'],'error')

    def test_period_order_overlap_ytd_quarter_and_custom(self):
        q=self.req('relative_change_v1');q['inputs'].reverse();q['inputs'][0]['role']='previous';q['inputs'][1]['role']='current';self.refused(self.outcome(q),'conflict','incompatible_periods')
        for p in [dict(kind='instant',date='2024-12-31'),dict(kind='duration',duration_type='custom',start='2024-02-01',end='2024-12-31')]:
            ctx=context('synthetic');f=next(f for f in ctx.catalog['facts']if f['fact_id']=='revenue-2024');e=next(e for e in ctx.catalog['evidence']if e['evidence_id']==f['evidence_id']);f['period']=p;e['period']=p;f['evidence_digest']=digest(e);ctx.admission['component_digests']['catalog']=digest(ctx.catalog)
            q=self.req('direct_fact_v1');q['inputs'][0]['period']=p;self.assertNotEqual(self.outcome(q,ctx)['financial_status'],'answered')
        # A valid full-period request cannot reinterpret YTD as a separate quarter.
        q=self.req('direct_fact_v1');q['inputs'][0]['period']=dict(kind='duration',duration_type='quarter',start='2024-04-01',end='2024-06-30');self.refused(self.outcome(q),'conflict','incompatible_periods')

    def test_cross_original_different_sha_requires_trusted_proof(self):
        q=self.req('absolute_change_v1',['revenue-2023','revenue-2024']);self.refused(self.outcome(q),'conflict','comparability_not_established')
        q['comparability_id']='own-revenue';r=self.outcome(q);self.assertEqual(r['financial_result']['display_value'],'20');self.assertNotEqual(r['financial_result']['inputs'][0]['document_sha256'],r['financial_result']['inputs'][1]['document_sha256'])
        q['comparability_id']='own-operating_profit';self.refused(self.outcome(q),'conflict','comparability_not_established')

    def test_cross_document_comparative_not_original(self):
        # Another explicitly OWN exact 2024 version; prior input remains a comparative of the first version.
        d=deepcopy(self.ctx.catalog['documents'][1]);d.update(document_id='own-alternate-2024',version_id='own-alternate-v1',sha256='a'*64);self.ctx.catalog['documents'].append(d)
        f=deepcopy(self.fs['revenue-2024']);e=deepcopy(next(e for e in self.ctx.catalog['evidence']if e['evidence_id']==f['evidence_id']))
        f.update(fact_id='own-alternate-revenue',document_id=d['document_id'],version_id=d['version_id'],evidence_id='own-alternate-ev')
        e.update(evidence_id=f['evidence_id'],document_id=d['document_id'],version_id=d['version_id'],document_sha256=d['sha256']);e['locator']['record_id']=f['fact_id'];f['evidence_digest']=digest(e)
        self.ctx.catalog['facts'].append(f);self.ctx.catalog['evidence'].append(e);self.fs[f['fact_id']]=f;self.refresh()
        q=self.req('absolute_change_v1',['revenue-2023-comparative','own-alternate-revenue']);self.refused(self.outcome(q),'conflict','incompatible_versions')

    def test_margin_different_exact_versions_rejected(self):
        q=self.req('operating_margin_v1',['operating_profit-2023','revenue-2023-comparative']);self.refused(self.outcome(q),'conflict','incompatible_versions')

    def test_original_policy_does_not_take_comparative(self):
        q=self.req('direct_fact_v1',['revenue-2023-comparative'],policy='original_period_documents');self.refused(self.outcome(q),'missing','original_version_missing')

    def test_unknown_publication_snapshot_and_historical(self):
        self.assertEqual(self.outcome()['financial_status'],'answered')
        q=self.req();q.update(mode='historical',as_of='2026-11-10T00:00:00+03:00');self.refused(self.outcome(q),'missing','publication_unknown')
        q['as_of']=None;self.assertEqual(self.outcome(q)['execution_status'],'awaiting_clarification')
        q['as_of']='2026-11-10T00:00:00';self.assertEqual(self.outcome(q)['execution_status'],'error')

    def test_candidate_structure_and_document_unchecked(self):
        for status in ['candidate','structure_checked']:
            ctx=context('synthetic');ctx.admission['comparability_records']=[];f=next(f for f in ctx.catalog['facts']if f['fact_id']=='revenue-2024');e=next(e for e in ctx.catalog['evidence']if e['evidence_id']==f['evidence_id']);f['provenance']['status']=status;e['provenance']['status']=status;f['evidence_digest']=digest(e);ctx.admission['component_digests']['catalog']=digest(ctx.catalog)
            self.refused(self.outcome(self.req('direct_fact_v1'),ctx),'missing','unverified_candidate')
        self.ctx.catalog['documents'][1]['preparation_status']='candidate';self.refresh();self.assertNotEqual(self.outcome()['financial_status'],'answered')

    def test_missing_evidence_or_wrong_hash_no_answer(self):
        for mutation in ['missing','hash','page','header']:
            ctx=context('synthetic');f=next(f for f in ctx.catalog['facts']if f['fact_id']=='revenue-2024');e=next(e for e in ctx.catalog['evidence']if e['evidence_id']==f['evidence_id'])
            if mutation=='missing':ctx.catalog['evidence'].remove(e)
            elif mutation=='hash':e['document_sha256']='0'*64
            elif mutation=='page':e['locator']['record_id']='other-cell'
            else:e['locator']['unit_header']=''
            ctx.admission['component_digests']['catalog']=digest(ctx.catalog);r=self.outcome(self.req('direct_fact_v1'),ctx);self.assertEqual(r['execution_status'],'error');self.assertIsNone(r['financial_result'])

    def test_context_manifest_tampering_fails_before_math(self):
        self.ctx.catalog['facts'][0]['value']='999'
        with patch('financial_assistant.financial_calculator.from_decimal',side_effect=AssertionError('arithmetic admission bypass')):self.assertEqual(self.outcome()['execution_status'],'error')

    def test_runtime_never_loads_gold(self):
        import inspect
        from financial_assistant import financial_calculator,fact_admission
        code=inspect.getsource(financial_calculator)+inspect.getsource(fact_admission)
        self.assertNotIn('evaluation/',code);self.assertNotIn('gold.json',code);self.assertNotIn('eval(',code);self.assertNotIn('exec(',code)

    def test_outcome_tamper_rejected_including_false_refusal(self):
        q=self.req();out=self.outcome(q);validate_calculation_binding(out,self.ctx,q)
        for kind in ['value','ratio','source','period','unit','false_refusal']:
            r=deepcopy(out)
            if kind=='value':r['financial_result']['display_value']='999'
            elif kind=='ratio':r['financial_result']['exact_result']['numerator']='999'
            elif kind=='source':r['financial_result']['sources'][0]['evidence']['locator']['record_id']='wrong'
            elif kind=='period':r['financial_result']['inputs'][0]['period']['end']='2024-06-30'
            elif kind=='unit':r['financial_result']['result_unit']['kind']='percentage_point'
            else:r.update(financial_status='missing',reason_code='value_missing',financial_result=None)
            with self.assertRaises(ContractError):validate_calculation_binding(r,self.ctx,q)

    def test_technical_or_refusal_cannot_hide_result(self):
        for status in ['error','awaiting_clarification','completed']:
            r=self.outcome();r['execution_status']=status;r['financial_status']=None if status!='completed'else 'missing'
            with self.assertRaises(ContractError):validate_outcome(r)

    def test_private_prepared_retrieval_integration_and_stale_index(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp')as td:
            td=Path(td);cat=deepcopy(self.ctx.catalog);resources={}
            # Owned byte identity fixtures only, never real PDF contents.
            for d in cat['documents']:
                import hashlib
                p=td/(d['document_id']+'.fixture');p.write_bytes(b'%PDF-OWN-SYNTHETIC-NOT-PARSED '+d['document_id'].encode());d.update(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),byte_length=p.stat().st_size,pdf_pages=1);d['availability'].update(local_resource_id=d['document_id'],file_status='available');resources[d['document_id']]=str(p)
                for e in cat['evidence']:
                    if e['document_id']==d['document_id']:e['document_sha256']=d['sha256']
            for f in cat['facts']:f['evidence_digest']=digest(next(e for e in cat['evidence']if e['evidence_id']==f['evidence_id']))
            a=deepcopy(self.ctx.admission);a['comparability_records']=[];a['component_digests']['catalog']=digest(cat);ctx=CalculationContext(cat,self.ctx.dictionary,a,resources=resources)
            cfg=read('data/extraction/kp3_pdf_v1/config.json');lex=read('data/extraction/kp3_pdf_v1/search_lexicon.json');db=td/'prepared.sqlite';build_index(db,cat,resources,cfg,lex,'prepared');gate=dict(db_path=db,config=cfg,lexicon=lex,export_paths=None)
            q=request(cat,'operating_margin_v1',[next(f for f in cat['facts']if f['fact_id']==k)for k in ['operating_profit-2024','revenue-2024']],'retrieval-test')
            r=calculate(ctx,q,retrieval_gate=gate);self.assertEqual(r['financial_status'],'answered',r);self.assertEqual(len(r['financial_result']['retrieval_resolution']['matched_evidence_ids']),2)
            with db.open('ab')as stream:stream.write(b'changed')
            r=calculate(ctx,q,retrieval_gate=gate);self.assertEqual(r['execution_status'],'error');self.assertEqual(r['reason_code'],'artifact_integrity_error');self.assertIsNone(r['financial_result'])

    def test_mocked_partial_and_automatic_retrieval_never_calculate(self):
        gate=dict(db_path='trusted-test-only',config={},lexicon={},export_paths=None)
        for hits,reason in [(dict(source_kind='automatic',status='found',results=[]),'unverified_candidate'),(dict(source_kind='prepared',status='partial',results=[]),'retrieval_context_missing')]:
            with patch('financial_assistant.financial_calculator.search_index',return_value=hits),patch('financial_assistant.financial_calculator.from_decimal',side_effect=AssertionError('calculated partial')):self.refused(calculate(self.ctx,self.req(),retrieval_gate=gate),'missing',reason)

    def test_loaded_context_files_are_guarded(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp')as td:
            paths=[]
            for i,v in enumerate([self.ctx.catalog,self.ctx.dictionary,self.ctx.admission]):
                p=Path(td)/(str(i)+'.json');p.write_text(json.dumps(v),encoding='utf8');paths.append(p)
            ctx=load_context(*paths);paths[0].write_text('{}',encoding='utf8');r=self.outcome(ctx=ctx);self.assertEqual(r['reason_code'],'context_invalid');self.assertIsNone(r['financial_result'])

    def test_scale_negative_zero_invalid_target_and_fx(self):
        for value,expected in [('-5','-0.000000005'),('0','0')]:
            ctx=context('synthetic',[dict(fact_id='revenue-2024',value=value)])
            q=self.req('scale_v1',target_scale=1000000000);self.assertEqual(self.outcome(q,ctx)['financial_result']['display_value'],expected)
        q=self.req('scale_v1');q['result_unit']['scale']=0;self.assertEqual(self.outcome(q)['execution_status'],'error')
        q=self.req('scale_v1');q['result_unit']['currency']='USD';self.refused(self.outcome(q),'unsupported','currency_conversion_not_supported')

    def test_exact_bound_synthetic_publication_date_conservative_zone_gate(self):
        # Purely own fixture: this does not establish a real report publication.
        d=self.ctx.catalog['documents'][1];d['publication']=dict(precision='date',value='2038-01-01',timezone='Europe/Moscow',binding='document_version',record_id='own-pub',source_url=None,version_id=d['version_id'],document_sha256=d['sha256']);self.refresh()
        q=self.req();q.update(mode='historical',as_of='2038-01-01T23:59:59+03:00');self.refused(self.outcome(q),'missing','not_yet_available')
        q['as_of']='2038-01-01T21:00:00+00:00';self.assertEqual(self.outcome(q)['financial_status'],'answered')

    def test_signed_approved_and_fetched_not_publication(self):
        d=self.ctx.catalog['documents'][1];d.update(signed_on='2025-01-01',approved_on='2025-01-01',fetched_at='2025-01-01T10:00:00+03:00');self.refresh()
        q=self.req();q.update(mode='historical',as_of='2026-01-01T00:00:00+03:00');self.refused(self.outcome(q),'missing','publication_unknown')

    def test_real_source_check_page_header_and_composition_binding_guards(self):
        for mutation in ['page','header','definition','nonfinancial','group','check']:
            ctx=context('real');f=ctx.catalog['facts'][0];ev=ctx.catalog['evidence'][0]
            if mutation in {'page','header'}:
                if mutation=='page':ev['locator']['pdf_page']+=1
                else:ev['locator']['unit_header']='wrong nonempty header'
                f['evidence_digest']=digest(ev)
            elif mutation=='definition':ctx.bindings['bindings'][0]['definition_ids']=[]
            elif mutation=='nonfinancial':ctx.bindings['bindings'][0]['nonfinancial_group']=False
            elif mutation=='group':ctx.bindings['bindings'][0]['organization_id']='segezha_group'
            else:ctx.checks['source_checks'][0]['checks']['header_visible']=False
            ctx.admission['component_digests']={k:digest(v)for k,v in dict(catalog=ctx.catalog,dictionary=ctx.dictionary,bindings=ctx.bindings,checks=ctx.checks).items()}
            q=request(ctx.catalog,'direct_fact_v1',[f],'real-tamper-negative')
            with patch.object(ctx,'check_local_source',side_effect=AssertionError('invalid proof reached file admission')):r=calculate(ctx,q)
            self.assertEqual(r['execution_status'],'error',r);self.assertIsNone(r['financial_result'])

    def test_real_missing_and_changed_source_technical_not_financial_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp')as td:
            ctx=context('real');f=ctx.catalog['facts'][0];q=request(ctx.catalog,'direct_fact_v1',[f],'real-source-negative')
            r=calculate(ctx,q);self.assertEqual(r['reason_code'],'source_missing');self.assertIsNone(r['financial_status'])
            p=Path(td)/'owned-tamper-fixture.pdf';p.write_bytes(b'%PDF-OWN-INVALID-HASH-FIXTURE')
            ctx.resources[f['document_id']]=str(p);r=calculate(ctx,q);self.assertEqual(r['reason_code'],'source_version_mismatch');self.assertIsNone(r['financial_result'])

    def test_prepared_hit_from_other_cell_rejected(self):
        from financial_assistant.retrieval_v2 import prepared_records
        hits=dict(source_kind='prepared',status='found',results=deepcopy(prepared_records(self.ctx.catalog)),index_sha256='a'*64)
        hit=next(h for h in hits['results']if h['evidence_id']=='operating_profit-2024-ev');hit['locator']['record_id']='other-cell'
        gate=dict(db_path='trusted-test-only',config={},lexicon={},export_paths=None)
        with patch('financial_assistant.financial_calculator.search_index',return_value=hits),patch('financial_assistant.financial_calculator.from_decimal',side_effect=AssertionError('wrong hit calculated')):r=calculate(self.ctx,self.req(),retrieval_gate=gate)
        self.assertEqual(r['reason_code'],'artifact_integrity_error');self.assertIsNone(r['financial_result'])


if __name__=='__main__':unittest.main()
