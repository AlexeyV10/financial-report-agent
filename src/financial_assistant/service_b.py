"""Fixed B pipeline. Mandatory search, no model, arbitrary tool calls or cached answer input."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .contracts_v2 import CHECKED,ContractError,digest,identifier,need,read_json,shape
from .fact_admission import file_sha,load_context
from .input_contracts import clarification
from .russian_input import parse_form,parse_text
from .input_binding import resolve_input,syntax_status
from .financial_calculator import calculate,validate_calculation_binding
from .retrieval_v2 import RetrievalError,search_index
from .document_extraction import ExtractionError
from .service_contracts import VERSION,STAGES,assumption_checks,validate_answer

ROOT=Path(__file__).resolve().parents[2]


class ServiceContext:
    def __init__(self,calculation,retrieval,run_dir,config_guard=None):
        self.calculation=calculation;self.retrieval=deepcopy(retrieval);self.run_dir=Path(run_dir).resolve();self.config_guard=config_guard
        need(self.run_dir.is_relative_to((ROOT/'tmp').resolve()),'private_run_dir_required')
        shape(self.retrieval,'db_path config lexicon export_paths')
        self.identity=self.current_identity()

    def current_identity(self):
        calculation=self.calculation
        return digest(dict(catalog=digest(calculation.catalog),dictionary=digest(calculation.dictionary),admission=digest(calculation.admission),resources=calculation.resources,file_guards=calculation.file_guards,run_dir=str(self.run_dir),config_guard=self.config_guard,retrieval_configuration=dict(config=self.retrieval['config'],lexicon=self.retrieval['lexicon'],db_path=str(self.retrieval['db_path']),export_paths=self.retrieval['export_paths'])))

    def validate(self):
        if self.config_guard:
            path,h=self.config_guard;need(Path(path).is_file()and file_sha(path)==h,'service_configuration_changed')
        self.calculation.validate()
        need(self.current_identity()==self.identity,'service_context_changed')


def load_service_context(path):
    p=Path(path).resolve();cfg=read_json(p)
    shape(cfg,'schema_version catalog dictionary admission bindings checks resources retrieval run_dir');need(cfg['schema_version']=='kp3-service-context-0.1','unsupported_service_context')
    shape(cfg['retrieval'],'db_path config lexicon exports')
    def local(value):return (ROOT/value).resolve()if value is not None else None
    ctx=load_context(*(local(cfg[k])for k in ['catalog','dictionary','admission','bindings','checks','resources']))
    gate=dict(db_path=local(cfg['retrieval']['db_path']),config=read_json(local(cfg['retrieval']['config'])),lexicon=read_json(local(cfg['retrieval']['lexicon'])),export_paths=read_json(local(cfg['retrieval']['exports']))if cfg['retrieval']['exports']else None)
    return ServiceContext(ctx,gate,local(cfg['run_dir']),(str(p),file_sha(p)))


def search_spec(req):
    refs=req['inputs'];tags={'revenue':'выручка','operating_profit':'операционная прибыль','operating_cash_flow':'CFO'}
    return dict(schema_version='kp3-search-0.1',query=' и '.join(dict.fromkeys(tags[r['metric_id']]for r in refs)),organization_id=req['organization_id'],consolidation=req['consolidation'],accounting_standard=req['accounting_standard'],metrics=list({r['metric_id']:dict(metric_id=r['metric_id'],definition_id=r['definition_id'])for r in refs}.values()),periods=list({digest(r['period']):r['period']for r in refs}.values()),documents=list({r['document_id']:dict(document_id=r['document_id'],version_id=r['version_id'])for r in refs}.values()),source_units=list({digest(r['source_unit']):r['source_unit']for r in refs}.values()),version_policy=req['version_policy'],mode=req['mode'],as_of=req['as_of'],top_k=32)


def resolve_evidence(ctx,req,hits):
    need(hits['source_kind']=='prepared'and hits['status']=='found','prepared_evidence_required')
    facts={f['fact_id']:f for f in ctx.catalog['facts']};evidence={e['evidence_id']:e for e in ctx.catalog['evidence']};matched=[]
    for ref in req['inputs']:
        f=facts[ref['fact_id']];ev=evidence[f['evidence_id']];rows=[r for r in hits['results']if r['evidence_id']==ev['evidence_id']]
        need(len(rows)==1,'required_evidence_not_unique');r=rows[0]
        need(r['source_kind']=='prepared_evidence'and r['verification_status']in CHECKED and r['evidence_digest']==digest(ev),'retrieved_evidence_mismatch')
        need(r['locator']==ev['locator']and all(r[k]==ev[k]for k in ['document_id','version_id','document_sha256','metric_id','definition_id','period','currency','scale','raw_value'])and r['value']==f['value'],'retrieved_cell_mismatch')
        matched.append(ev['evidence_id'])
    return matched


def _source_question(source):
    if type(source)is not dict:return ''
    value=source.get('question')if source.get('kind')=='text'else source.get('form',{}).get('original_question')if type(source.get('form'))is dict else ''
    return value if isinstance(value,str)else ''


def execute(source,method,context,answers=None,run_id=None):
    """Every call owns fresh task/trace and an exclusive private run file. No prior Answer accepted."""
    rid=run_id or 'run-'+uuid4().hex;handle=None;active=None;started=0;invalid_run_id=False
    try:identifier(rid)
    except ContractError:rid='run-'+uuid4().hex;invalid_run_id=True
    a=dict(schema_version=VERSION,run_id=rid,task_id=rid,method=method if type(method)is str else 'invalid-method',execution_status='completed',request_status='pending',financial_status=None,reason_code='ok',original_question=_source_question(source),normalized_input=None,clarifications=[],financial_result=None,outcome=None,assumption_checks=[],unfulfilled_requests=[],retrieval=None,trace=[],context_digest=context.identity,source_input_digest=None,saved_run=None,model_calls=0)
    def stage(name):
        nonlocal active,started
        active=name;started=perf_counter()
    def finish(status='completed',reason='ok',**details):
        nonlocal active
        a['trace'].append(dict(stage=active,run_id=rid,status=status,elapsed_ms=round((perf_counter()-started)*1000,4),reason_code=reason,details=details));active=None
    def stop(request_status,reason,execution='completed'):
        a.update(request_status=request_status,reason_code=reason,execution_status=execution)
    try:
        need(not invalid_run_id,'invalid_run_id');need(type(method)is str,'invalid_method');a['source_input_digest']=digest(dict(source=source,answers=answers))
        context.run_dir.mkdir(parents=True,exist_ok=True)
        target=context.run_dir/(hashlib.sha256(rid.encode()).hexdigest()+'.json')
        try:handle=target.open('x',encoding='utf8')
        except FileExistsError:raise ContractError('run_id_exists')from None
        a['saved_run']=dict(resource_id=target.name,status='written',private=True)
        if method!='B':stop('unsupported','method_not_supported')
        else:
            stage('input');tasksource=deepcopy(source)
            if tasksource.get('kind')=='text':
                shape(tasksource,'kind input_id question');task=parse_text(tasksource['question'],context.calculation.catalog,rid)
            else:
                shape(tasksource,'kind form');need(tasksource['kind']=='form','invalid_input_kind');tasksource['form']['input_id']=rid;task=parse_form(tasksource['form'],context.calculation.catalog)
            a['normalized_input']=task;finish(syntax_status=syntax_status(task))
            stage('catalog_filters');context.validate();binding=resolve_input(task,context.calculation.catalog,context.calculation.dictionary)
            patches=[]if answers is None else answers;need(type(patches)is list and len(patches)<=16,'clarification_limit')
            for patch in patches:binding=resolve_input(clarification(binding['normalized_input'],patch),context.calculation.catalog,context.calculation.dictionary)
            a.update(normalized_input=binding['normalized_input'],clarifications=binding['clarifications'],unfulfilled_requests=binding['normalized_input']['unfulfilled_requests'])
            if binding['status']!='resolved':
                finish('awaiting_clarification'if binding['status']=='awaiting_clarification'else 'error'if binding['status']=='error'else 'blocked',binding['reason_code'],binding_status=binding['status'],preliminary_only=True)
                stop(binding['status'],binding['reason_code'],'awaiting_clarification'if binding['status']=='awaiting_clarification'else 'error'if binding['status']=='error'else 'completed')
            else:
                req=binding['request'];finish(binding_status='resolved',preliminary_only=True,request_id=req['request_id'])
                stage('search');gate=context.retrieval;ctx=context.calculation;spec=search_spec(req)
                hits=search_index(gate['db_path'],ctx.catalog,ctx.resources,gate['config'],gate['lexicon'],spec,gate['export_paths'])
                a['retrieval']=dict(run_id=rid,status=hits['status'],reason_code=hits['reason_code'],source_kind=hits['source_kind'],index_sha256=hits['index_sha256'],result_count=len(hits['results']),spec=spec)
                if hits['source_kind']!='prepared':finish('blocked','unverified_candidate');stop('missing','unverified_candidate')
                elif hits['status']!='found':finish('blocked',hits['reason_code']);stop('missing',hits['reason_code'])
                else:
                    finish(results=len(hits['results']),source_kind='prepared')
                    stage('fact_resolution');matched=resolve_evidence(ctx,req,hits);fresh=resolve_input(binding['normalized_input'],ctx.catalog,ctx.dictionary);need(fresh==binding,'binding_changed_after_search');finish(evidence_ids=matched,checked_values_from_catalog=True)
                    stage('source_validation');ctx.validate();facts={f['fact_id']:f for f in ctx.catalog['facts']};evs={e['evidence_id']:e for e in ctx.catalog['evidence']};docs={d['document_id']:d for d in ctx.catalog['documents']}
                    for ref in req['inputs']:
                        f=facts[ref['fact_id']];d=docs[f['document_id']];ctx.source_proof(f,evs[f['evidence_id']],d);ctx.check_local_source(d)
                    finish(primary_reannotation=False,selected_documents=sorted({r['document_id']for r in req['inputs']}),source_bytes_checked=ctx.admission['data_origin']=='real')
                    stage('calculation');out=calculate(ctx,req,rid,gate);a.update(outcome=out,financial_result=out['financial_result'],financial_status=out['financial_status']);finish('error'if out['execution_status']=='error'else 'completed',out['reason_code'],registered_operation_executed=out['financial_status']=='answered',internal_live_retrieval_recheck=True)
                    stage('result_validation');validate_calculation_binding(out,ctx,req,gate);finish(recomputation=True,internal_live_retrieval_recheck=True)
                    stop('evaluated',out['reason_code'],out['execution_status'])
        assumptions=a['normalized_input']['assumptions']if a['normalized_input']else []
        a['assumption_checks']=assumption_checks(assumptions,a['outcome'])
    except Exception as exc:
        code=getattr(exc,'code','internal_error')
        if active:finish('error',code,error_type=type(exc).__name__)
        stop('error',code,'limit'if code=='clarification_limit'else 'error');a.update(financial_status=None,financial_result=None,outcome=None)
        a['assumption_checks']=assumption_checks(a['normalized_input']['assumptions']if a['normalized_input']else [],None)
    # A skipped stage is explicit and has no fabricated execution time.
    answer_started=perf_counter();observed={row['stage']:row for row in a['trace']}
    for name in STAGES:
        if name not in observed:observed[name]=dict(stage=name,run_id=rid,status='skipped',elapsed_ms=0,reason_code='not_reached',details={})
    observed['answer']=dict(stage='answer',run_id=rid,status='completed',elapsed_ms=round((perf_counter()-answer_started)*1000,4),reason_code=a['reason_code'],details=dict(financial_result_present=a['financial_result']is not None))
    a['trace']=[observed[name]for name in STAGES]
    try:
        validate_answer(a)
        if handle:
            json.dump(a,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n');handle.close()
    except Exception as exc:
        if handle:handle.close()
        a.update(execution_status='error',request_status='error',reason_code=getattr(exc,'code','run_write_failed'),financial_status=None,financial_result=None,outcome=None,saved_run=None)
        a['assumption_checks']=assumption_checks(a['normalized_input']['assumptions']if a['normalized_input']else [],None)
        a['trace'][-1].update(status='error',reason_code=a['reason_code'],details=dict(financial_result_present=False))
    return a
