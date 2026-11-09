"""Corpus05 admission regressions; no private PDFs/network/model needed."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('corpus05_checker', ROOT/'scripts/check_kp3_corpus.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
from financial_assistant.catalog import validate_catalog, _raw_number
from financial_assistant.contracts_v2 import ContractError, digest
from financial_assistant.tasks import bind_task


class Corpus05Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((audit.BASE/'runtime_catalog.json').read_text(encoding='utf-8'))
        cls.bindings = json.loads((audit.BASE/'source_bindings.json').read_text(encoding='utf-8'))
        cls.checks = json.loads((audit.EVAL/'source-checks.json').read_text(encoding='utf-8'))

    def package(self, cat=None, bindings=None, checks=None):
        return audit.check_package(cat or self.catalog, bindings or self.bindings, checks or self.checks)

    def test_all_real_cells_bind_snapshot_and_block_history(self):
        result = self.package()
        self.assertEqual((result['pdf_versions'],result['facts'],result['unique_organization_metric_period_contexts']), (8,48,39))
        self.assertEqual((result['snapshot_bindings'],result['historical_blocked'],result['source_bridge_controls']), (48,48,32))

    def test_strict_explicit_space_notation_and_parentheses(self):
        for raw, value in [('92 442 267','92442267'),('(19 999 990)','-19999990'),('0','0')]:
            self.assertEqual(str(_raw_number(dict(raw_value=raw,numeric_encoding='space_thousands_integer'))),value)
        for raw in ['92 44 267','92,442,267','1.234','1 234.5','-1 234','(1 23)','1\t234','1\u00a0234','1\u202f234','1 234 ',' 1 234','1  234','+1 234','(1 234','NaN',None]:
            with self.subTest(raw=raw), self.assertRaises(ContractError):
                _raw_number(dict(raw_value=raw,numeric_encoding='space_thousands_integer'))

    def test_unknown_and_duplicate_identifiers(self):
        for collection in ['documents','evidence','facts','organizations','metrics']:
            c=deepcopy(self.catalog);c[collection].append(deepcopy(c[collection][0]))
            with self.subTest(collection=collection),self.assertRaises(ContractError):validate_catalog(c)
        for key in ['document_id','organization_id','evidence_id','metric_id']:
            c=deepcopy(self.catalog);c['facts'][0][key]='not-known'
            with self.subTest(key=key),self.assertRaises(ContractError):validate_catalog(c)

    def test_conflicting_value_or_sign_rejected(self):
        for value in ['1','-440304']:
            c=deepcopy(self.catalog);c['facts'][0]['value']=value
            with self.subTest(value=value),self.assertRaises(ContractError):validate_catalog(c)

    def test_wrong_fact_context_rejected(self):
        for key,value in [('organization_id','segezha_group'),('definition_id','some-other-definition'),('currency','USD'),('scale',1000),('version_id','other-version')]:
            c=deepcopy(self.catalog);c['facts'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ContractError):validate_catalog(c)
        c=deepcopy(self.catalog);c['facts'][0]['period']['end']='2023-09-30'
        with self.assertRaises(ContractError):validate_catalog(c)

    def test_wrong_evidence_cell_even_after_digest_update(self):
        for key,value in [('pdf_page',6),('column_label','2024'),('row_label','Валовая прибыль'),('page_region','right_half_of_spread')]:
            c=deepcopy(self.catalog);ev=c['evidence'][0];ev['locator'][key]=value
            c['facts'][0]['original_label']=ev['locator']['row_label'];c['facts'][0]['evidence_digest']=digest(ev)
            with self.subTest(key=key),self.assertRaises(ValueError):self.package(cat=c)

    def test_wrong_hash_or_version_rejected(self):
        for key in ['document_sha256','version_id']:
            c=deepcopy(self.catalog);c['evidence'][0][key]='0'*64
            c['facts'][0]['evidence_digest']=digest(c['evidence'][0])
            with self.subTest(key=key),self.assertRaises(ContractError):validate_catalog(c)

    def test_checked_fact_without_evidence_rejected(self):
        c=deepcopy(self.catalog);c['facts'][0].update(evidence_id=None,evidence_digest=None)
        with self.assertRaises(ContractError):validate_catalog(c)

    def test_candidate_and_structure_checked_cannot_be_inputs(self):
        for status in ['candidate','structure_checked']:
            c=deepcopy(self.catalog);c['facts'][0]['provenance']['status']=status
            outcome=bind_task(c,audit.task_for(c,c['facts'][0]))
            self.assertEqual(outcome['reason_code'],'unverified_candidate')
            self.assertEqual(outcome['fact_ids'],[])
            with self.assertRaises(ValueError):self.package(cat=c)

    def test_candidate_evidence_cannot_be_upgraded_by_fact(self):
        c=deepcopy(self.catalog);c['evidence'][0]['provenance']['status']='structure_checked'
        c['facts'][0]['evidence_digest']=digest(c['evidence'][0])
        self.assertEqual(bind_task(c,audit.task_for(c,c['facts'][0]))['reason_code'],'unverified_candidate')

    def test_lost_header_and_missing_context_not_defaulted(self):
        for key in ['table_title','column_label','unit_header']:
            c=deepcopy(self.catalog);c['evidence'][0]['locator'][key]='';c['facts'][0]['evidence_digest']=digest(c['evidence'][0])
            with self.subTest(key=key),self.assertRaises(ContractError):validate_catalog(c)
        for key in ['organization_id','definition_id','period','currency','scale']:
            c=deepcopy(self.catalog);c['facts'][0].pop(key)
            with self.subTest(key=key),self.assertRaises(ContractError):validate_catalog(c)

    def test_binding_scope_standard_and_document_identity(self):
        for key,value in [('nonfinancial_group',False),('standard','RAS'),('organization_id','segezha_group'),('document_sha256','0'*64)]:
            b=deepcopy(self.bindings);b['bindings'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.package(bindings=b)
        c=deepcopy(self.catalog);t=audit.task_for(c,c['facts'][0]);t['accounting_standard']='RAS'
        self.assertEqual(bind_task(c,t)['reason_code'],'entity_or_standard_mismatch')

    def test_pre_tax_cfo_is_not_accepted_as_net_cfo(self):
        c=deepcopy(self.catalog);ev=c['evidence'][4];f=c['facts'][4]
        ev['raw_value']='177,796';f['value']='177796';f['evidence_digest']=digest(ev)
        # Basic JSON consistency alone would pass; source composition/cell record must reject it.
        validate_catalog(c)
        with self.assertRaises(ValueError):self.package(cat=c)

    def test_original_comparative_policy_and_duplicate_selection(self):
        c=self.catalog;f=c['facts'][1];t=audit.task_for(c,f);t['version_policy']='original_period_documents'
        self.assertEqual(bind_task(c,t)['reason_code'],'original_version_missing')
        f=next(f for f in c['facts'] if f['fact_id']=='phosagro-2024-revenue-2023');t=audit.task_for(c,f)
        first=c['documents'][0];t['documents'].append(dict(document_id=first['document_id'],version_id=first['version_id']))
        self.assertEqual(bind_task(c,t)['reason_code'],'duplicate_candidates')
        t['version_policy']='original_period_documents'
        self.assertEqual(bind_task(c,t)['fact_ids'],['phosagro-2023-revenue-2023'])

    def test_approval_and_fetch_do_not_remove_temporal_unknown(self):
        c=deepcopy(self.catalog);c['documents'][0]['approved_on']='2020-01-01';c['documents'][0]['signed_on']='2020-01-01';c['documents'][0]['fetched_at']='2020-01-01T00:00:00Z'
        self.assertEqual(bind_task(c,audit.task_for(c,c['facts'][0],'historical'))['reason_code'],'publication_unknown')
        c['documents'][0]['publication']['value']='2020-01-01'
        with self.assertRaises(ContractError):validate_catalog(c)

    def test_local_missing_and_changed_pdf_are_technical_states(self):
        cat=deepcopy(self.catalog);cat['documents']=cat['documents'][:1];did=cat['documents'][0]['document_id']
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as td:
            p=Path(td)/'source.pdf';p.write_bytes(b'%PDF- changed')
            self.assertEqual(audit.check_local_files(cat,{did:str(p)})[0]['file_status'],'hash_mismatch')
            self.assertEqual(audit.check_local_files(cat,{did:str(p.parent/'absent.pdf')})[0]['file_status'],'missing')
            self.assertEqual(audit.check_local_files(cat,{})[0]['extraction_status'],'not_run')

    def test_extraction_failure_does_not_erase_verified_annotation(self):
        c=deepcopy(self.catalog);c['documents'][0]['availability']['extraction_status']='error'
        result=bind_task(c,audit.task_for(c,c['facts'][0]))
        self.assertEqual(result['binding_status'],'ready')
        self.assertEqual(c['documents'][0]['availability']['extraction_status'],'error')
        # This is a prepared snapshot fact; future06 must report its own extraction failure.

    def test_registry_does_not_admit_excluded_candidates(self):
        registry=json.loads((audit.EVAL/'candidates.json').read_text(encoding='utf-8'))['candidates']
        for row in registry:
            if row['decision'].startswith('excluded'):
                self.assertEqual(row['fact_count'],0)
                self.assertNotIn(row['candidate_id'],{d['document_id'] for d in self.catalog['documents']})

    def test_source_check_not_just_present_or_marked_true(self):
        for change in ['missing','duplicate','wrong_digest','header_false','automated_claim']:
            s=deepcopy(self.checks)
            if change=='missing':s['source_checks'].pop()
            elif change=='duplicate':s['source_checks'].append(deepcopy(s['source_checks'][0]))
            elif change=='wrong_digest':s['source_checks'][0]['evidence_digest']='0'*64
            elif change=='header_false':s['source_checks'][0]['checks']['header_visible']=False
            else:s['source_checks'][0]['automatic_extraction_success_claimed']=True
            with self.subTest(change=change),self.assertRaises(ValueError):self.package(checks=s)

    def test_real_comparative_cfo_difference_is_preserved(self):
        fs={f['fact_id']:f for f in self.catalog['facts']}
        original=fs['segezha-2021-operating_cash_flow-2021'];later=fs['segezha-2022-operating_cash_flow-2021']
        self.assertEqual(int(later['value'])*later['scale']-int(original['value'])*original['scale'],-23925000)
        self.assertNotEqual(original['version_id'],later['version_id'])
        for f in [original,later]:self.assertEqual(bind_task(self.catalog,audit.task_for(self.catalog,f))['fact_ids'],[f['fact_id']])
        controls=json.loads((audit.EVAL/'control-calculations.json').read_text(encoding='utf-8'))
        self.assertEqual(audit.check_controls(self.catalog,controls),8)
        controls['margin_controls'][0]['rounded_percent']='999.99'
        with self.assertRaises(ValueError):audit.check_controls(self.catalog,controls)


if __name__=='__main__': unittest.main()
