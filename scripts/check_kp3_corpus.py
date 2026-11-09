"""Integrity/admission audit of the manually prepared corpus05, not a PDF extractor."""
from pathlib import Path
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from financial_assistant.catalog import validate_catalog, available_from
from financial_assistant.contracts_v2 import digest, read_json
from financial_assistant.tasks import bind_task

BASE = ROOT / 'data/catalogs/kp3_corpus_v1'
EVAL = ROOT / 'evaluation/kp3_05_2026-11-09'


def require(ok, code):
    if not ok:
        raise ValueError(code)


def unique(rows, field):
    result = {r[field]: r for r in rows}
    require(len(result) == len(rows), 'duplicate_' + field)
    return result


def task_for(catalog, fact, mode='snapshot'):
    doc = next(d for d in catalog['documents'] if d['document_id'] == fact['document_id'])
    return dict(schema_version='0.2', task_id='corpus05-audit', original_question='Проверка допуска входа, без финансового ответа',
                operation_id='direct_fact_v1', organization_id=fact['organization_id'], consolidation='group',
                accounting_standard=doc['accounting_standard'], metric_id=fact['metric_id'], definition_id=fact['definition_id'],
                periods=[deepcopy(fact['period'])], documents=[dict(document_id=doc['document_id'], version_id=doc['version_id'])],
                version_policy='explicit_versions', result_unit=dict(currency=fact['currency'], scale=fact['scale']),
                mode=mode, as_of='2026-11-09T23:59:59+03:00' if mode == 'historical' else None)


def check_package(catalog, source_bindings, source_checks):
    """Compare declared cells to the separate recorded visual checks; no claim to re-review PDF pixels."""
    validate_catalog(catalog)
    require(source_bindings['binding_version'] == source_checks['record_version'] == '1.0', 'profile_version')
    require(source_bindings['catalog_id'] == catalog['catalog_id'], 'binding_catalog_mismatch')
    docs = unique(catalog['documents'], 'document_id')
    facts = unique(catalog['facts'], 'fact_id')
    evidence = unique(catalog['evidence'], 'evidence_id')
    bindings = unique(source_bindings['bindings'], 'document_id')
    checks = unique(source_checks['source_checks'], 'fact_id')
    require(set(bindings) == set(docs) and set(checks) == set(facts), 'coverage_mismatch')
    require(len({b['binding_id'] for b in bindings.values()}) == len(bindings), 'duplicate_binding_id')
    require(len({r['check_id'] for r in checks.values()}) == len(checks), 'duplicate_check_id')
    require({o['consolidation'] for o in catalog['organizations']} == {'group'}, 'group_required')
    columns = 0
    for did, doc in docs.items():
        b = bindings[did]
        require(doc['data_origin'] == 'real' and doc['accounting_standard'] == 'IFRS', 'real_ifrs_required')
        require(doc['preparation_status'] == 'ready' and doc['provenance']['status'] == 'assistant_checked', 'document_not_prepared')
        require(b['document_sha256'] == doc['sha256'] and b['organization_id'] == doc['organization_id']
                and b['standard'] == 'IFRS' and b['nonfinancial_group'] is True, 'source_binding_context_mismatch')
        require(b['review_status'] == 'assistant_checked' and b['human_reviewer'] is None, 'invented_review')
        require(b['official_anchor']['document_url'] == doc['document_url'] and b['official_anchor']['page_url'] == doc['source_url'], 'official_anchor_mismatch')
        these = {f['fact_id'] for f in facts.values() if f['document_id'] == did}
        require(set(b['fact_ids']) == these and len(b['fact_ids']) == len(these), 'binding_fact_coverage')
        for section, metric in [('op_composition', 'operating_profit'), ('cfo_composition', 'operating_cash_flow')]:
            proof = b[section]
            require(len(proof['signed_values_by_column']) == len(proof['reported_totals']) == len(b['periods']) == 2, 'composition_columns')
            for i, values in enumerate(proof['signed_values_by_column']):
                require(len(values) == len(proof['row_labels']) and all(type(v) is int for v in values), 'composition_rows')
                require(sum(values) == proof['reported_totals'][i], 'composition_total_mismatch')
                match = [f for f in facts.values() if f['document_id'] == did and f['metric_id'] == metric and f['period'] == b['periods'][i]]
                require(len(match) == 1 and match[0]['value'] == str(proof['reported_totals'][i]), 'composition_fact_mismatch')
                columns += 1
    for fid, f in facts.items():
        ev = evidence[f['evidence_id']]; r = checks[fid]; b = bindings[f['document_id']]
        require(f['provenance']['status'] == ev['provenance']['status'] == r['status'] == 'assistant_checked', 'fact_not_checked')
        require(r['binding_id'] == b['binding_id'] and r['evidence_id'] == ev['evidence_id']
                and r['evidence_digest'] == f['evidence_digest'] == digest(ev), 'check_evidence_mismatch')
        require(r['document_sha256'] == b['document_sha256'] and r['locator'] == ev['locator']
                and r['source_cell'] == ev['raw_value'] and r['normalized_value'] == f['value'], 'recorded_cell_mismatch')
        require(f['definition_id'] in b['definition_ids'] and f['currency'] == b['currency']
                and f['scale'] == b['scale'] and f['period'] in b['periods'], 'binding_fact_context_mismatch')
        expected_page = b['source_pages']['cash_flow' if f['metric_id'] == 'operating_cash_flow' else 'income']
        require(ev['locator']['pdf_page'] == expected_page and ev['locator']['unit_header'] == b['unit_header'], 'binding_page_or_header_mismatch')
        require(set(r['checks']) == {'group','standard','definition','period','column','currency','scale','raw_sign','exact_pdf','header_visible'}
                and all(v is True for v in r['checks'].values()) and r['automatic_extraction_success_claimed'] is False, 'incomplete_source_check')
        result = bind_task(catalog, task_for(catalog, f))
        require(result['binding_status'] == 'ready' and result['fact_ids'] == [fid] and result['calculations_performed'] is False, 'snapshot_binding_failed')
        require(available_from(docs[f['document_id']]) is None, 'unexpected_publication_upgrade')
        historical = bind_task(catalog, task_for(catalog, f, 'historical'))
        require(historical['reason_code'] == 'publication_unknown' and not historical['fact_ids'], 'historical_gate_failed')
    economic = {(f['organization_id'], f['metric_id'], digest(f['period'])) for f in facts.values()}
    return dict(catalog_id=catalog['catalog_id'], pdf_versions=len(docs), facts=len(facts), evidence=len(evidence),
                unique_organization_metric_period_contexts=len(economic), version_specific_additional_cells=len(facts)-len(economic),
                per_metric=dict(Counter(f['metric_id'] for f in facts.values())), source_bridge_controls=columns,
                snapshot_bindings=len(facts), historical_blocked=len(facts), human_reviewed=0,
                production_answer_calls=0, model_calls=0, general_extractor_evaluated=False, final_benchmark=False)


def check_local_files(catalog, resource_map):
    """Only local byte identity, never 'metric absent' or financial meaning."""
    results = []
    for d in catalog['documents']:
        p = resource_map.get(d['availability']['local_resource_id'])
        if p is None or not Path(p).is_file():
            results.append(dict(document_id=d['document_id'], file_status='missing', extraction_status='not_run'))
            continue
        try:
            data = Path(p).read_bytes()
            ok = len(data) == d['byte_length'] and hashlib.sha256(data).hexdigest() == d['sha256'] and data.startswith(b'%PDF-')
            results.append(dict(document_id=d['document_id'], file_status='available' if ok else 'hash_mismatch',
                                extraction_status='not_run', bytes_checked=len(data)))
        except OSError:
            results.append(dict(document_id=d['document_id'], file_status='not_checked', extraction_status='error'))
    return results


def check_controls(catalog, controls):
    """Independent preparation arithmetic; never call a production answer/formula."""
    from fractions import Fraction
    from decimal import Decimal, localcontext, ROUND_HALF_UP
    facts = {f['fact_id']: f for f in catalog['facts']}
    require(len(controls['margin_controls']) == len(catalog['documents']), 'control_coverage')
    seen = set()
    for row in controls['margin_controls']:
        op, revenue = (facts[fid] for fid in row['input_fact_ids'])
        require(op['metric_id'] == 'operating_profit' and revenue['metric_id'] == 'revenue', 'control_metric_mismatch')
        require(all(op[k] == revenue[k] for k in ['document_id','version_id','organization_id','period','currency','scale'])
                and op['origin_role'] == revenue['origin_role'] == 'reported_period', 'control_context_mismatch')
        require(op['document_id'] not in seen and int(revenue['value']) > 0, 'control_duplicate_or_denominator')
        seen.add(op['document_id'])
        exact = Fraction(int(op['value']) * 100, int(revenue['value']))
        q, r = divmod(abs(exact.numerator) * 100, exact.denominator)
        q += 2 * r >= exact.denominator
        rounded = ('-' if exact < 0 else '') + f'{q//100}.{q%100:02d}'
        with localcontext() as context:
            context.prec = 80
            decimal = str((Decimal(op['value']) / Decimal(revenue['value']) * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        require(rounded == decimal == row['rounded_percent'] and str(exact) == row['exact_fraction'], 'independent_control_mismatch')
        require(row['production_calls'] == 0 and row['independent_decimal80_matches'] is True, 'control_origin_mismatch')
    return len(seen)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-map', type=Path, help='optional trusted local path map, kept in tmp/')
    args = parser.parse_args()
    cat = read_json(BASE/'runtime_catalog.json')
    result = check_package(cat, read_json(BASE/'source_bindings.json'), read_json(EVAL/'source-checks.json'))
    result['independent_margin_controls'] = check_controls(cat, read_json(EVAL/'control-calculations.json'))
    manifest = read_json(BASE/'manifest.json')
    for rel, expected in manifest['file_sha256'].items():
        require(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest() == expected, 'manifest_mismatch:' + rel)
    if args.resource_map:
        result['local_files'] = check_local_files(cat, read_json(args.resource_map))
        require(all(x['file_status'] == 'available' for x in result['local_files']), 'local_resource_unavailable')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
