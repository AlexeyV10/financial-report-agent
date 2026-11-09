"""Independent source/version/context guard scenarios; no private reports or model required."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import ClarificationRequired,ContractError,digest
from financial_assistant.document_extraction import SCHEMA,ExtractionError,column_period,fingerprint,load_config,parse_region,source_number
from financial_assistant.retrieval_v2 import (RetrievalError,SEARCH_SCHEMA,_unique_records,automatic_records,build_index,normalize_query,private_path,search_index,validate_export)


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def fixture(directory):
    # Existing explicitly OWN synthetic method inputs, never real issuer facts.
    c=load(ROOT/'data/catalogs/kp3_finance_dev_v1/runtime_catalog.json');resources={}
    for d in c['documents']:
        p=directory/(d['document_id']+'.hash-fixture')
        data=('%PDF-OWN-SYNTHETIC-HASH-FIXTURE-NOT-PARSED '+d['document_id']).encode()
        p.write_bytes(data);d['sha256']=hashlib.sha256(data).hexdigest();d['byte_length']=len(data);d['pdf_pages']=1
        d['preparation_status']='ready';d['availability']['local_resource_id']=d['document_id'];resources[d['document_id']]=str(p)
        for e in c['evidence']:
            if e['document_id']==d['document_id']:e['document_sha256']=d['sha256']
    for f in c['facts']:f['evidence_digest']=digest(next(e for e in c['evidence'] if e['evidence_id']==f['evidence_id']))
    return c,resources


def spec_for(c,facts=None):
    fs=facts or c['facts'];dids=list(dict.fromkeys(f['document_id'] for f in fs));mids=list(dict.fromkeys(f['metric_id'] for f in fs))
    docs={d['document_id']:d for d in c['documents']};org=next(o for o in c['organizations'] if o['organization_id']==fs[0]['organization_id'])
    periods=list({digest(f['period']):f['period'] for f in fs}.values())
    units=list({digest(dict(currency=f['currency'],scale=f['scale'])):dict(currency=f['currency'],scale=f['scale']) for f in fs}.values())
    return dict(schema_version=SEARCH_SCHEMA,query='выручка и операционная прибыль и CFO',organization_id=org['organization_id'],consolidation='group',accounting_standard='IFRS',metrics=[dict(metric_id=m,definition_id=next(f['definition_id'] for f in fs if f['metric_id']==m)) for m in mids],periods=periods,documents=[dict(document_id=did,version_id=docs[did]['version_id']) for did in dids],source_units=units,version_policy='explicit_versions',mode='snapshot',as_of=None,top_k=32)


class RetrievalV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name)
        self.catalog,self.resources=fixture(self.dir);self.cfg=load_config(ROOT/'data/extraction/kp3_pdf_v1/config.json');self.lex=load(ROOT/'data/extraction/kp3_pdf_v1/search_lexicon.json')
        self.db=self.dir/'prepared.sqlite';build_index(self.db,self.catalog,self.resources,self.cfg,self.lex,'prepared')

    def search(self,spec=None,**kwargs):
        values=dict(db_path=self.db,catalog=self.catalog,resources=self.resources,cfg=self.cfg,lexicon=self.lex,spec=spec or spec_for(self.catalog));values.update(kwargs)
        return search_index(**values)

    def test_all_required_evidence_across_two_documents(self):
        r=self.search();self.assertEqual(r['status'],'found');self.assertEqual(len(r['results']),6)
        self.assertEqual({x['evidence_id'] for x in r['results']},{f['evidence_id'] for f in self.catalog['facts']})
        self.assertIsNone(r['financial_status']);self.assertFalse(r['reverification_performed'])

    def test_partial_top_k_is_not_complete_evidence(self):
        s=spec_for(self.catalog);s['top_k']=1;r=self.search(s)
        self.assertEqual(len(r['results']),1)
        self.assertEqual(r['status'],'partial');self.assertTrue(r['requested_context_coverage']['missing_contexts'])
        self.assertNotEqual({x['evidence_id'] for x in r['results']},{f['evidence_id'] for f in self.catalog['facts']})

    def test_period_units_definition_and_version_are_not_keywords(self):
        f=self.catalog['facts'][0];s=spec_for(self.catalog,[f]);r=self.search(s)
        self.assertEqual([x['evidence_id'] for x in r['results']],[f['evidence_id']])
        s['source_units']=[dict(currency='USD',scale=1)];self.assertEqual(self.search(s)['status'],'not_found')
        s['source_units']=[dict(currency=f['currency'],scale=1000)];self.assertEqual(self.search(s)['status'],'not_found')
        s['source_units']=[dict(currency=f['currency'],scale=f['scale'])];s['periods']=[column_period(2039,'','за 2039 год')]
        self.assertEqual(self.search(s)['reason_code'],'no_matching_evidence_context')

    def test_missing_fields_request_clarification_without_defaults(self):
        for k in ['organization_id','periods','documents','metrics','source_units','version_policy']:
            s=spec_for(self.catalog);s.pop(k)
            with self.subTest(k=k),self.assertRaises(ClarificationRequired) as e:self.search(s)
            self.assertIn(k,e.exception.fields)

    def test_unknown_ids_duplicate_selections_and_wrong_scope(self):
        for field,value,code in [('organization_id','unknown','unknown_organization_id'),('consolidation','legal_entity','entity_or_standard_mismatch'),('accounting_standard','RAS','entity_or_standard_mismatch')]:
            s=spec_for(self.catalog);s[field]=value
            with self.subTest(field=field),self.assertRaises(RetrievalError) as e:self.search(s)
            self.assertEqual(e.exception.code,code)
        for what in ['documents','metrics','periods','source_units']:
            s=spec_for(self.catalog);s[what].append(deepcopy(s[what][0]))
            with self.subTest(what=what),self.assertRaises((RetrievalError,ContractError)):self.search(s)
        for field,value in [('document_id','unknown'),('version_id','other-version')]:
            s=spec_for(self.catalog);s['documents'][0][field]=value
            with self.subTest(field=field),self.assertRaises(RetrievalError):self.search(s)
        s=spec_for(self.catalog);s['metrics'][0]['definition_id']='another-definition'
        with self.assertRaises(RetrievalError):self.search(s)

    def test_empty_or_injection_like_query_cannot_select_all(self):
        for value in ['','!!!',"' OR 1=1 --",'несуществующее слово','CFO metricunknown']:
            s=spec_for(self.catalog);s['query']=value
            if value in {'','!!!'}:
                with self.assertRaises((ClarificationRequired,RetrievalError)):self.search(s)
            else:self.assertEqual(self.search(s)['results'],[])

    def test_historical_unknown_and_known_synthetic_date_gate(self):
        s=spec_for(self.catalog);s.update(mode='historical',as_of='2038-01-01T00:00:00Z')
        self.assertEqual(self.search(s)['reason_code'],'publication_unknown')
        c=deepcopy(self.catalog)
        for d in c['documents']:
            d['publication']=dict(precision='date',value='2038-01-01',timezone='UTC',binding='document_version',record_id='own-publication-'+d['document_id'],source_url=None,version_id=d['version_id'],document_sha256=d['sha256'])
        db=self.dir/'dated.sqlite';build_index(db,c,self.resources,self.cfg,self.lex,'prepared')
        self.assertEqual(self.search(s,db_path=db,catalog=c)['reason_code'],'not_yet_available')
        s['as_of']='2038-01-02T00:00:00Z';self.assertEqual(self.search(s,db_path=db,catalog=c)['status'],'found')

    def test_snapshot_cannot_claim_as_of_and_instant_wrong_metric(self):
        s=spec_for(self.catalog);s['as_of']='2038-01-02T00:00:00Z'
        with self.assertRaises(RetrievalError):self.search(s)
        s['as_of']=None;s['periods']=[dict(kind='instant',date='2038-01-01')]
        with self.assertRaises(RetrievalError) as e:self.search(s)
        self.assertEqual(e.exception.code,'metric_period_mismatch')

    def test_missing_or_changed_source_is_technical(self):
        p=Path(next(iter(self.resources.values())));old=p.read_bytes();p.write_bytes(old+b'changed')
        with self.assertRaises(ExtractionError) as e:self.search()
        self.assertEqual(e.exception.code,'source_version_mismatch')
        p.unlink()
        with self.assertRaises(ExtractionError) as e:self.search()
        self.assertEqual(e.exception.code,'source_missing')

    def test_changed_index_or_missing_manifest_is_technical(self):
        original=self.db.read_bytes();self.db.write_bytes(original+b'changed')
        with self.assertRaises(RetrievalError) as e:self.search()
        self.assertEqual(e.exception.code,'index_hash_mismatch')
        self.db.write_bytes(original);Path(str(self.db)+'.manifest.json').unlink()
        with self.assertRaises(RetrievalError) as e:self.search()
        self.assertEqual(e.exception.code,'index_manifest_missing')

    def test_changed_config_lexicon_or_catalog_invalidates_index(self):
        cfg=deepcopy(self.cfg);cfg['x_tolerance']=9
        with self.assertRaises(RetrievalError) as e:self.search(cfg=cfg)
        self.assertEqual(e.exception.code,'index_configuration_mismatch')
        lex=deepcopy(self.lex);lex['metrics']['revenue']['search_aliases'].append('оборот')
        with self.assertRaises(RetrievalError) as e:self.search(lexicon=lex)
        self.assertEqual(e.exception.code,'index_configuration_mismatch')
        c=deepcopy(self.catalog);c['organizations'][0]['name']+=' modified'
        with self.assertRaises(RetrievalError) as e:self.search(catalog=c)
        self.assertEqual(e.exception.code,'index_catalog_mismatch')
        from financial_assistant import retrieval_v2
        real_hash=retrieval_v2.file_sha
        with patch.object(retrieval_v2,'file_sha',side_effect=lambda p:'0'*64 if Path(p).name=='contracts_v2.py' else real_hash(p)):
            with self.assertRaises(RetrievalError) as e:self.search()
        self.assertEqual(e.exception.code,'index_configuration_mismatch')

    def test_candidate_and_structure_checked_are_not_prepared(self):
        for status in ['candidate','structure_checked']:
            c=deepcopy(self.catalog);c['facts'][0]['provenance']['status']=status
            with self.subTest(status=status),self.assertRaises(RetrievalError):build_index(self.dir/(status+'.db'),c,self.resources,self.cfg,self.lex,'prepared')
        c=deepcopy(self.catalog);c['evidence'][0]['provenance']['status']='candidate'
        c['facts'][0]['evidence_digest']=digest(c['evidence'][0])
        with self.assertRaises(RetrievalError):build_index(self.dir/'ev.db',c,self.resources,self.cfg,self.lex,'prepared')

    def test_conflicting_prepared_facts_not_chosen_by_ranking(self):
        c=deepcopy(self.catalog);f=deepcopy(c['facts'][0]);f['fact_id']+='-duplicate';c['facts'].append(f)
        with self.assertRaises(RetrievalError) as e:build_index(self.dir/'dups.db',c,self.resources,self.cfg,self.lex,'prepared')
        self.assertEqual(e.exception.code,'prepared_fact_conflict')

    def test_duplicate_fragment_does_not_count_twice(self):
        row=self.search()['results'][0];second=deepcopy(row);second['record_id']='new-fragment-id'
        self.assertEqual(len(_unique_records([row,second])),1)
        second['value']='123456'
        with self.assertRaises(RetrievalError):_unique_records([row,second])

    def test_private_artifact_boundary_and_no_implicit_fallback(self):
        with self.assertRaises(RetrievalError):private_path(ROOT/'data/leaked-index.db')
        with self.assertRaises(RetrievalError):build_index(self.dir/'bad.db',self.catalog,self.resources,self.cfg,self.lex,None)
        with self.assertRaises(RetrievalError):build_index(self.dir/'auto.db',self.catalog,self.resources,self.cfg,self.lex,'automatic')
        with self.assertRaises(RetrievalError):build_index(self.db,self.catalog,self.resources,self.cfg,self.lex,'prepared')

    def test_keyword_normalization_is_not_a_question_parser(self):
        self.assertEqual(normalize_query('ВЫРУЧКИ и Операционной прибыли и CFO',self.lex),['metricrv','metricop','metriccfo'])
        self.assertNotIn('organization_id',normalize_query('выручка ФосАгро за 2024',self.lex))


class GeometryTests(unittest.TestCase):
    def test_annual_and_interim_columns_keep_full_periods(self):
        self.assertEqual(column_period(2037,'','за 2037 год')['start'],'2037-01-01')
        h1=column_period(2037,'Шесть месяцев, закончившихся 30 июня','interim')
        q2=column_period(2037,'Три месяца, закончившихся 30 июня','interim')
        self.assertEqual((h1['duration_type'],h1['start']),('year_to_date','2037-01-01'))
        self.assertEqual((q2['duration_type'],q2['start']),('quarter','2037-04-01'))
        for hdr in ['30 июня','Три месяца','Три месяца, закончившихся 29 июня']:
            with self.subTest(hdr=hdr),self.assertRaises(ExtractionError):column_period(2037,hdr,'interim')

    def test_raw_numbers_preserve_sign_without_guessing(self):
        for raw,value in [('1,234','1234'),('(1 234)','-1234'),('-12.5','-12.5'),('0','0')]:self.assertEqual(source_number(raw)[0],value)
        for raw in ['1 23','1,23','1\u00a0234','-','–','(1,234','NaN','12 OR 1=1','(-12)']:
            with self.subTest(raw=raw),self.assertRaises(ExtractionError):source_number(raw)

    def test_geometry_without_known_issuer_years_or_expected_amounts(self):
        cfg=load_config(ROOT/'data/extraction/kp3_pdf_v1/config.json')
        def word(txt,x,y,width=25):return dict(text=txt,x0=x,x1=x+width,top=y,bottom=y+8)
        words=[word('Консолидированный отчет о прибыли или убытке и прочем совокупном доходе за 2037 год',20,30,550),word('Млн руб.',20,70,70),word('2037',420,70),word('2036',500,70),word('Выручка',20,90,70),word('1,111',410,90,35),word('2,222',490,90,35)]
        r=parse_region(words,(0,6,600,854),1,'full_page',cfg)
        self.assertEqual(r['status'],'structured');t=r['tables'][0]
        self.assertEqual([x['period']['end'] for x in t['columns']],['2037-12-31','2036-12-31'])
        self.assertEqual([x['value'] for x in t['rows'][0]['cells']],['1111','2222'])
        without_unit=[w for w in words if w['text']!='Млн руб.']
        self.assertEqual(parse_region(without_unit,(0,6,600,854),1,'full_page',cfg)['status'],'unsupported_layout')

    def test_empty_scan_is_not_a_zero_fact(self):
        cfg=load_config(ROOT/'data/extraction/kp3_pdf_v1/config.json');r=parse_region([],(0,0,600,850),1,'full_page',cfg)
        self.assertEqual(r['status'],'unsupported_layout');self.assertEqual(r['tables'],[])

    def test_four_columns_require_both_duration_headers(self):
        cfg=load_config(ROOT/'data/extraction/kp3_pdf_v1/config.json')
        def w(txt,x,y,width=25):return dict(text=txt,x0=x,x1=x+width,top=y,bottom=y+8)
        words=[w('Консолидированный отчет о прибыли или убытке и прочем совокупном доходе за три и шесть месяцев, закончившихся 30 июня 2037 года',20,30,550),w('Шесть месяцев, закончившихся 30 июня',300,60,100),w('Три месяца, закончившихся 30 июня',460,60,90),w('Млн руб.',20,100,70)]
        words += [w(y,x,100) for y,x in [('2037',300),('2036',360),('2037',460),('2036',520)]]
        words += [w('Выручка',20,120,70)]+[w(str(v),x,120) for v,x in [(11,300),(22,360),(33,460),(44,520)]]
        parsed=parse_region(words,(0,0,600,850),1,'full_page',cfg)
        periods=[c['period'] for c in parsed['tables'][0]['columns']]
        self.assertEqual([p['start'][5:] for p in periods],['01-01','01-01','04-01','04-01'])
        damaged=[w for w in words if not w['text'].startswith('Шесть месяцев')]
        self.assertEqual(parse_region(damaged,(0,0,600,850),1,'full_page',cfg)['status'],'unsupported_layout')


class AutomaticIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name)
        self.catalog,self.resources=fixture(self.dir);self.cfg=load_config(ROOT/'data/extraction/kp3_pdf_v1/config.json');self.lex=load(ROOT/'data/extraction/kp3_pdf_v1/search_lexicon.json')
        self.exports={};self.payloads={}
        def w(txt,x,y,width=25):return dict(text=txt,x0=x,x1=x+width,top=y,bottom=y+8)
        for d in self.catalog['documents']:
            year=int(d['report_period']['end'][:4])
            # Own geometry fixture: the amounts deliberately disagree with the prepared method facts.
            words=[w(f'Консолидированный отчет о прибыли или убытке и прочем совокупном доходе за {year} год',20,30,550),w('Млн руб.',20,70,70),w(str(year),420,70),w(str(year-1),500,70),w('Выручка',20,90,70),w('999',420,90),w('888',500,90)]
            region=parse_region(words,(0,0,600,850),1,'full_page',self.cfg)
            e=dict(schema_version=SCHEMA,document_sha256=d['sha256'],byte_length=d['byte_length'],pdf_pages=1,extractor_fingerprint=fingerprint(ROOT,self.cfg),config=self.cfg,environment=dict(python=self.cfg['worker_python'],pdfplumber=self.cfg['pdfplumber'],pdfminer_six=self.cfg['pdfminer_six']),origin='automatic_pdf_geometry_candidates',pages=[dict(pdf_page=1,width=600,height=850,bbox=[0,0,600,850],regions=[region])])
            p=self.dir/(d['document_id']+'.json');p.write_text(json.dumps(e,ensure_ascii=False),encoding='utf-8');self.exports[d['document_id']]=str(p);self.payloads[d['document_id']]=e
        self.db=self.dir/'automatic.sqlite';build_index(self.db,self.catalog,self.resources,self.cfg,self.lex,'automatic',self.exports)

    def test_candidates_are_not_gold_or_checked_facts(self):
        f=self.catalog['facts'][0];s=spec_for(self.catalog,[f]);s['query']='выручка';s['source_units']=[dict(currency='RUB',scale=1000000)]
        r=search_index(self.db,self.catalog,self.resources,self.cfg,self.lex,s,self.exports)
        self.assertEqual(r['status'],'found');self.assertEqual(len(r['results']),1);row=r['results'][0]
        self.assertEqual(row['value'],'999');self.assertNotEqual(row['value'],f['value'])
        self.assertEqual(row['verification_status'],'candidate');self.assertIsNone(row['evidence_id']);self.assertIsNone(r['financial_status'])

    def test_export_changed_or_missing_invalidates_automatic_index(self):
        s=spec_for(self.catalog);p=Path(next(iter(self.exports.values())));p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaises(RetrievalError) as e:search_index(self.db,self.catalog,self.resources,self.cfg,self.lex,s,self.exports)
        self.assertEqual(e.exception.code,'extraction_hash_mismatch');p.unlink()
        with self.assertRaises(RetrievalError) as e:search_index(self.db,self.catalog,self.resources,self.cfg,self.lex,s,self.exports)
        self.assertEqual(e.exception.code,'extraction_missing')

    def test_wrong_export_hash_version_config_environment_or_mode(self):
        d=self.catalog['documents'][0];base=self.payloads[d['document_id']]
        for key,value in [('document_sha256','0'*64),('extractor_fingerprint','0'*64),('origin','manual_reference_v1'),('pdf_pages',2),('environment',{})]:
            e=deepcopy(base);e[key]=value
            with self.subTest(key=key),self.assertRaises(RetrievalError):validate_export(e,d,self.cfg)
        e=deepcopy(base);e['expected']='not an extraction input'
        with self.assertRaises(RetrievalError):validate_export(e,d,self.cfg)

    def test_wrong_cell_page_header_unit_period_bbox_and_provenance(self):
        d=self.catalog['documents'][0];base=self.payloads[d['document_id']]
        for change in ['page','header','unit','period','bbox','review','duplicate_column','gold']:
            e=deepcopy(base);table=e['pages'][0]['regions'][0]['tables'][0];cell=table['rows'][0]['cells'][0]
            if change=='page':e['pages'][0]['pdf_page']=2
            elif change=='header':table['unit_header']=''
            elif change=='unit':table['scale']=1000
            elif change=='period':cell['period']['end']='2023-09-30'
            elif change=='bbox':cell['bbox']=[-100,0,1,1]
            elif change=='review':cell['provenance']='assistant_checked'
            elif change=='duplicate_column':table['rows'][0]['cells'].append(deepcopy(cell))
            else:cell['gold']='999'
            with self.subTest(change=change),self.assertRaises((RetrievalError,ExtractionError,ContractError)):validate_export(e,d,self.cfg)

    def test_empty_table_cannot_be_marked_successful(self):
        d=self.catalog['documents'][0];e=deepcopy(self.payloads[d['document_id']]);e['pages'][0]['regions'][0]['tables'][0]['rows']=[]
        with self.assertRaises(RetrievalError):validate_export(e,d,self.cfg)

    def test_missing_cash_flow_table_is_unsupported_not_financial_absence(self):
        s=spec_for(self.catalog,[next(f for f in self.catalog['facts'] if f['metric_id']=='operating_cash_flow')]);s['query']='CFO';s['source_units']=[dict(currency='RUB',scale=1000000)]
        r=search_index(self.db,self.catalog,self.resources,self.cfg,self.lex,s,self.exports)
        self.assertEqual(r['status'],'unsupported_layout');self.assertEqual(r['reason_code'],'statement_table_unavailable');self.assertIsNone(r['financial_status'])

    def test_extractor_has_no_catalog_gold_or_execution_imports(self):
        import ast
        worker=(ROOT/'scripts/extract_pdf_v2.py').read_text(encoding='utf-8');core=(ROOT/'src/financial_assistant/document_extraction.py').read_text(encoding='utf-8')
        for token in ['runtime_catalog.json','source_bindings.json','source-checks.json','reference_bundle.json','evaluation/fixtures']:
            self.assertNotIn(token,worker+core)
        for tree in [ast.parse(worker),ast.parse(core)]:
            for node in ast.walk(tree):
                if isinstance(node,(ast.Import,ast.ImportFrom)):
                    modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or '']
                    self.assertFalse(any(m.split('.')[0] in {'subprocess','socket','urllib','requests','runpy'} for m in modules))

    def test_positive_used_cash_label_is_not_signed_net_cfo_by_alias(self):
        d=self.catalog['documents'][0];export=deepcopy(self.payloads[d['document_id']]);t=export['pages'][0]['regions'][0]['tables'][0]
        t['statement_type']='cash_flow';t['rows'][0]['row_label']='Чистые денежные средства, использованные в операционной деятельности'
        org=self.catalog['organizations'][0];metrics={m['metric_id']:m for m in self.catalog['metrics']}
        rows,_=automatic_records(d,org,metrics,export,self.lex)
        self.assertEqual(rows,[])


if __name__=='__main__':unittest.main()
