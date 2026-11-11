"""Developer-only RC identity builder. Never overwrites an existing manifest."""
from datetime import datetime,timezone
from pathlib import Path
import json
from .verify import SCHEMA,need,sha,validate


def build(root,output,base_commit,release_id='kp3-rc1-2026-11-10'):
    from kp3_protocol_v1.freeze import verify_freeze
    root=Path(root).resolve();output=Path(output).resolve();need(output.is_relative_to(root/'tmp')and not output.exists(),'new_private_manifest_required')
    fpath='evaluation/protocols/kp3_eval_v1/freeze-manifest.json';freeze=verify_freeze(root,root/fpath)
    paths=set(freeze['file_sha256'])
    for pattern in ['src/**/*.py','app_kp3/*.py','app_kp3/*.css','scripts/*.py','scripts/*.ps1','data/**/*','evaluation/kp3_release_v1/*.py','evaluation/kp3_protocol_v1/*.py','evaluation/kp3_run_v1/*.py','evaluation/kp3_16_2026-11-10/raw/*.json']:
        for p in root.glob(pattern):
            name=p.relative_to(root).as_posix()
            if p.is_file()and '__pycache__'not in p.parts and not name.startswith('data/releases/'):paths.add(name)
    paths.update([fpath,'evaluation/kp3_16_2026-11-10/raw-manifest.json','evaluation/kp3_16_2026-11-10/metrics.json','evaluation/kp3_16_2026-11-10/run-manifest.json','docs/kp3/release_candidate_v1.md','docs/kp3/desktop_ui_v1.md','tests/test_release_candidate17.py'])
    resources=freeze['logical_resources'];B=sorted(k for k in resources if k.startswith('pdf:')or k in {'index:prepared','index_manifest:prepared'});model=sorted(k for k in resources if k.startswith('model:'))
    e=dict(freeze_path=fpath,freeze_sha256=sha(root/fpath),raw_manifest_path='evaluation/kp3_16_2026-11-10/raw-manifest.json',raw_manifest_sha256=sha(root/'evaluation/kp3_16_2026-11-10/raw-manifest.json'),metrics_path='evaluation/kp3_16_2026-11-10/metrics.json',metrics_sha256=sha(root/'evaluation/kp3_16_2026-11-10/metrics.json'),relation='Financial/retrieval/admission/prompt v1 evaluated14/16 unchanged; approved desktop UI is a separate later layer; RC17 verification/launcher only')
    inputs=dict(catalog='data/catalogs/kp3_corpus_v1/runtime_catalog.json',dictionary='data/dictionaries/kp3_finance_v1/definitions.json',admission='data/calculation/kp3_calculator_v1/real_admission.json',bindings='data/catalogs/kp3_corpus_v1/source_bindings.json',checks='evaluation/kp3_05_2026-11-09/source-checks.json',config='data/extraction/kp3_pdf_v1/config.json',lexicon='data/extraction/kp3_pdf_v1/search_lexicon.json')
    m=dict(schema_version=SCHEMA,release_id=release_id,created_at=datetime.now(timezone.utc).isoformat(),base_commit=base_commit,scope=dict(complete_original_P0=False,unseen_real=0,prepared_real_facts=48,exact_pdf_versions=8,human_reviewed=0,publication_unknown=8,arbitrary_pdf_admission_ui=False,historical_real_trading=False,package19=False,report_slides18=False),file_sha256={p:sha(root/p)for p in sorted(paths)},evaluation=e,resources=resources,profiles=dict(code=[],B=B,A=B+model,C=B+model,UI=B),environment=dict(core_python='3.14.7',core_sqlite='3.53.4',UI=dict(python='3.12.14',streamlit='1.67.0',pandas='3.1.1')),service_inputs=inputs,limits=dict(B_chat=0,A_choices=1,C_decisions=8,total_seconds=180,invocation_seconds=60,max_output_tokens=384,top_k=32,operations=['direct_fact_v1','absolute_change_v1','relative_change_v1','scale_v1','operating_margin_v1']))
    validate(root,m);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8',newline='\n')as f:json.dump(m,f,ensure_ascii=False,indent=2);f.write('\n')
    return m
