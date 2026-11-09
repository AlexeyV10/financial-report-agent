"""Trusted prepared context and source proofs, not a fact extractor or evaluation oracle."""
from copy import deepcopy
from pathlib import Path
import hashlib

from .catalog import validate_catalog
from .contracts_v2 import CHECKED,digest,identifier,need,period,read_json,shape,text
from .document_extraction import source_identity


def file_sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


class CalculationContext:
    """Created by trusted setup/CLI, never from a model request or a search hit."""
    def __init__(self,catalog,dictionary,admission,bindings=None,checks=None,resources=None,file_guards=None):
        self.catalog=deepcopy(catalog);self.dictionary=deepcopy(dictionary);self.admission=deepcopy(admission)
        self.bindings=deepcopy(bindings);self.checks=deepcopy(checks);self.resources=dict(resources or {})
        self.file_guards=dict(file_guards or {});self.validate()

    def validate(self):
        for path,h in self.file_guards.items():need(Path(path).is_file() and file_sha(path)==h,'context_artifact_changed')
        validate_catalog(self.catalog)
        a=self.admission;shape(a,'admission_version context_id data_origin catalog_id component_digests resource_policy comparability_records')
        need(a['admission_version']=='1.0' and a['catalog_id']==self.catalog['catalog_id'],'admission_version_mismatch')
        need(a['data_origin'] in {'real','synthetic'} and a['resource_policy']=='required_for_real','invalid_admission_scope')
        components={'catalog':self.catalog,'dictionary':self.dictionary,'bindings':self.bindings,'checks':self.checks}
        need(a['component_digests']=={k:digest(v)for k,v in components.items()},'context_digest_mismatch')
        need(self.dictionary['dictionary_version']=='1.0','unsupported_dictionary_version')
        defs=self.dictionary['definitions'];need(len({d['definition_id']for d in defs})==len(defs),'duplicate_definition')
        for d in self.catalog['documents']:need(d['data_origin']==a['data_origin'],'admission_origin_mismatch')
        need(type(a['comparability_records']) is list,'invalid_comparability_records')
        ids=[r['comparability_id']for r in a['comparability_records']];need(len(ids)==len(set(ids)),'duplicate_comparability_id')
        docs={d['document_id']:d for d in self.catalog['documents']}
        evidence={e['evidence_id'] for e in self.catalog['evidence']}
        for r in a['comparability_records']:
            shape(r,'comparability_id organization_id metric_id definition_id review_status documents periods basis support_evidence_ids same_definition_and_classification source_checks_reviewed')
            identifier(r['comparability_id']);text(r['basis'])
            need(r['review_status'] in CHECKED and r['same_definition_and_classification'] is True and r['source_checks_reviewed'] is True,'admission_comparability_unproven')
            need(len(r['documents'])==len(r['periods'])==2 and len({d['document_id'] for d in r['documents']})==2,'admission_comparability_context')
            for d,p in zip(r['documents'],r['periods']):
                shape(d,'document_id version_id document_sha256');period(p)
                actual=docs.get(d['document_id'])
                need(actual is not None and d['version_id']==actual['version_id'] and d['document_sha256']==actual['sha256'] and r['organization_id']==actual['organization_id'],'admission_comparability_context')
            need(type(r['support_evidence_ids']) is list and len(r['support_evidence_ids'])>=2 and set(r['support_evidence_ids'])<=evidence,'admission_comparability_evidence')
            for d,p in zip(r['documents'],r['periods']):
                need(any(e['evidence_id'] in r['support_evidence_ids'] and e['document_id']==d['document_id'] and e['version_id']==d['version_id'] and e['metric_id']==r['metric_id'] and e['definition_id']==r['definition_id'] and e['period']==p and e['provenance']['status'] in CHECKED for e in self.catalog['evidence']),'admission_comparability_evidence')
        if a['data_origin']=='real':
            need(type(self.bindings) is dict and self.bindings['binding_version']=='1.0' and self.bindings['catalog_id']==a['catalog_id'],'bindings_required')
            need(type(self.checks) is dict and self.checks['record_version']=='1.0','source_checks_required')
            need(len({b['document_id']for b in self.bindings['bindings']})==len(self.bindings['bindings']),'duplicate_source_binding')
            need(len({r['fact_id']for r in self.checks['source_checks']})==len(self.checks['source_checks']),'duplicate_source_check')

    def check_local_source(self,doc):
        if doc['data_origin']=='real':
            resource=doc['availability']['local_resource_id']
            need(resource in self.resources,'source_missing')
            source_identity(self.resources[resource],doc)

    def source_proof(self,fact,ev,doc):
        if doc['data_origin']=='synthetic':return
        bs=[b for b in self.bindings['bindings']if b['document_id']==doc['document_id']]
        need(len(bs)==1,'source_binding_missing');b=bs[0]
        need(b['document_sha256']==doc['sha256'] and b['organization_id']==doc['organization_id'] and b['standard']==doc['accounting_standard'] and b['nonfinancial_group'] is True,'source_binding_mismatch')
        need(b['review_status'] in CHECKED and fact['fact_id'] in b['fact_ids'] and fact['definition_id'] in b['definition_ids'],'source_definition_unproven')
        need(fact['period'] in b['periods'] and fact['currency']==b['currency'] and fact['scale']==b['scale'],'source_context_mismatch')
        records=[r for r in self.checks['source_checks']if r['fact_id']==fact['fact_id']]
        need(len(records)==1,'source_check_missing');r=records[0]
        need(r['status'] in CHECKED and r['binding_id']==b['binding_id'] and r['evidence_id']==ev['evidence_id'] and r['evidence_digest']==digest(ev),'source_check_mismatch')
        need(r['document_sha256']==doc['sha256'] and r['locator']==ev['locator'] and r['source_cell']==ev['raw_value'] and r['normalized_value']==fact['value'],'source_cell_mismatch')
        need(set(r['checks'])=={'group','standard','definition','period','column','currency','scale','raw_sign','exact_pdf','header_visible'} and all(v is True for v in r['checks'].values()),'source_header_unproven')


def load_context(catalog_path,dictionary_path,admission_path,bindings_path=None,checks_path=None,resources_path=None):
    paths=[catalog_path,dictionary_path,admission_path]+([bindings_path]if bindings_path else [])+([checks_path]if checks_path else [])+([resources_path]if resources_path else [])
    guards={str(Path(p).resolve()):file_sha(p)for p in paths}
    return CalculationContext(read_json(Path(catalog_path)),read_json(Path(dictionary_path)),read_json(Path(admission_path)),read_json(Path(bindings_path))if bindings_path else None,read_json(Path(checks_path))if checks_path else None,read_json(Path(resources_path))if resources_path else None,guards)
