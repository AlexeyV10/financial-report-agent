"""Audit06 and optional reproducible local dev run; gold is loaded only by evaluator."""
from pathlib import Path
from collections import Counter
from copy import deepcopy
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.catalog import validate_catalog
from financial_assistant.contracts_v2 import digest,read_json
from financial_assistant.document_extraction import canonical,load_config,normalized,read_private_json
from financial_assistant.retrieval_v2 import _lexicon,automatic_records,build_index,private_path,search_index,validate_export,validate_search

CATALOG=ROOT/'data/catalogs/kp3_corpus_v1/runtime_catalog.json'
CONFIG=ROOT/'data/extraction/kp3_pdf_v1/config.json'
LEXICON=ROOT/'data/extraction/kp3_pdf_v1/search_lexicon.json'
CASES=ROOT/'data/dev_cases/kp3_retrieval_v1/cases.json'
TARGETS=ROOT/'evaluation/fixtures/kp3_retrieval_v1/targets.json'


def inputs():
    cat=read_json(CATALOG);validate_catalog(cat);cfg=load_config(CONFIG);lex=_lexicon(read_json(LEXICON))
    cases=read_json(CASES);targets=read_json(TARGETS)
    assert targets['catalog_digest']==digest(cat)
    ids=[c['case_id'] for c in cases['cases']];assert len(set(ids))==len(ids)
    assert set(ids)=={r['case_id'] for r in targets['cases']}
    assert len(targets['cases'])==len(ids)
    known={e['evidence_id'] for e in cat['evidence']}
    for row in targets['cases']:assert set(row['required_evidence_ids'])<=known and len(row['required_evidence_ids'])==len(set(row['required_evidence_ids']))
    for row in cases['cases']:validate_search(row['spec'],cat)
    return cat,cfg,lex,cases,targets


def exact_match(row,ev,cat):
    """Evaluator-only comparison; retrieval/worker never receive ev or targets."""
    fact=next(f for f in cat['facts'] if f['evidence_id']==ev['evidence_id'])
    equal=['document_id','version_id','metric_id','definition_id','period','currency','scale','raw_value']
    if any(row[k]!=ev[k] for k in equal):return False
    if row['document_sha256']!=ev['document_sha256'] or row['organization_id']!=fact['organization_id'] or row['value']!=fact['value']:return False
    loc=row['locator'];target=ev['locator']
    return loc.get('pdf_page')==target.get('pdf_page') and loc.get('page_region')==target.get('page_region') and normalized(row['row_label'])==normalized(target['row_label'])


def local_dev(resources,exports,work_dir):
    cat,cfg,lex,cases,targets=inputs();work_dir=private_path(work_dir)
    assert not work_dir.exists(),'Use a new immutable run directory'
    work_dir.mkdir(parents=True)
    targetmap={r['case_id']:r['required_evidence_ids'] for r in targets['cases']};evs={e['evidence_id']:e for e in cat['evidence']}
    report=dict(purpose='Open dev diagnostics, not final benchmark/model quality',prepared={},automatic={},extraction={},cases=[],production_answers=0,model_calls=0,new_facts_admitted=0)
    automatic=[];matrix=[]
    for doc in cat['documents']:
        export=read_private_json(private_path(exports[doc['document_id']]));validate_export(export,doc,cfg)
        org=next(o for o in cat['organizations'] if o['organization_id']==doc['organization_id'])
        rows,diagnostics=automatic_records(doc,org,{m['metric_id']:m for m in cat['metrics']},export,lex)
        automatic+=rows;matrix.append(dict(document_id=doc['document_id'],table_counts=diagnostics['table_counts'],candidate_cells=len(rows),pdf_sha256=doc['sha256'],extractor_fingerprint=export['extractor_fingerprint'],export_sha256=hashlib.sha256(Path(exports[doc['document_id']]).read_bytes()).hexdigest()))
    coverage=[]
    for ev in cat['evidence']:
        matches=[r for r in automatic if exact_match(r,ev,cat)]
        coverage.append(dict(evidence_id=ev['evidence_id'],exact_cell_matches=len(matches),matched=len(matches)==1))
    outside=[r for r in automatic if not any(exact_match(r,e,cat) for e in cat['evidence'])]
    report['extraction']=dict(target_cells=len(coverage),matched=sum(c['matched'] for c in coverage),not_extracted=sum(not c['matched'] for c in coverage),candidate_cells=len(automatic),out_of_catalog_subperiod_candidates=len(outside),other_wrong_target_context_candidates=sum(r['origin_role']!='subperiod_not_admitted' and r['period']['duration_type']!='quarter' for r in outside),matrix=matrix,cell_coverage=coverage,annotation_reused_as_extraction=False)
    for kind in ['prepared','automatic']:
        db=work_dir/(kind+'.sqlite');build=build_index(db,cat,resources,cfg,lex,kind,exports if kind=='automatic' else None)
        summary=dict(index=build,case_count=0,complete_evidence_cases=0,complete_table_cases=0,by_family={},historical_blocked=0,case_status_counts={})
        statuses=Counter();families={}
        for case in cases['cases']:
            # Only spec goes into the engine; target IDs/values are evaluator-only.
            out=search_index(db,cat,resources,cfg,lex,case['spec'],exports if kind=='automatic' else None)
            required=[evs[eid] for eid in targetmap[case['case_id']]]
            matched={ev['evidence_id'] for ev in required if any(exact_match(row,ev,cat) for row in out['results'])}
            tables={(ev['document_id'],ev['locator']['pdf_page'],ev['locator']['page_region']) for ev in required}
            found={(row['document_id'],row['locator'].get('pdf_page'),row['locator'].get('page_region')) for row in out['results']}
            all_ev=len(matched)==len(required);all_tables=tables<=found
            item=dict(case_id=case['case_id'],kind=kind,status=out['status'],reason_code=out['reason_code'],required_evidence=len(required),matched_evidence=len(matched),all_required_evidence=all_ev,all_required_tables=all_tables,result_count=len(out['results']))
            report['cases'].append(item);summary['case_count']+=1;summary['complete_evidence_cases']+=all_ev;summary['complete_table_cases']+=all_tables;statuses[out['status']]+=1
            family=families.setdefault(case['family'],dict(cases=0,all_required_evidence=0,all_required_tables=0));family['cases']+=1;family['all_required_evidence']+=all_ev;family['all_required_tables']+=all_tables
            historical=deepcopy(case['spec']);historical.update(mode='historical',as_of='2026-11-09T23:59:59+03:00')
            blocked=search_index(db,cat,resources,cfg,lex,historical,exports if kind=='automatic' else None)
            assert blocked['reason_code']=='publication_unknown' and not blocked['results'];summary['historical_blocked']+=1
        summary['by_family']=families;summary['case_status_counts']=dict(statuses);report[kind]=summary
    assert report['prepared']['complete_evidence_cases']==56
    # These are observed denominators; unsupported source cells remain in the all-source denominator.
    report['all_cells_known_to_developer']=True;report['final_eval_freeze']=False;report['reserved_unseen_real']=0
    (work_dir/'dev-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    sys.stdout.reconfigure(encoding='utf-8');parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-map',type=Path);parser.add_argument('--exports',type=Path);parser.add_argument('--work-dir',type=Path)
    args=parser.parse_args()
    if args.resource_map or args.exports or args.work_dir:
        assert args.resource_map and args.exports and args.work_dir,'All local dev options must be explicit'
        r=local_dev(read_json(args.resource_map),read_json(args.exports),args.work_dir)
        print(json.dumps(dict(extraction=r['extraction']|{'matrix':'kept in private run report','cell_coverage':'minimal evaluator records'},prepared=r['prepared'],automatic=r['automatic'],model_calls=0,new_facts=0),ensure_ascii=False,indent=2))
    else:
        cat,cfg,lex,cases,targets=inputs();print(json.dumps(dict(status='public_inputs_valid',case_count=len(cases['cases']),target_cells=len(cat['evidence']),worker_receives_targets=False,source_bytes_checked=False,general_pdf_extraction_executed=False),ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
