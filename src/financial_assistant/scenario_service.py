"""Validated finance-to-scenario bridge. Real readiness is blocked; only own data can simulate."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib,json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from .contracts_v2 import ContractError,digest,identifier,instant,need,read_json,shape
from .catalog import available_from
from .fact_admission import file_sha,load_context
from .financial_calculator import calculate,validate_calculation_binding
from .calculation_contracts import validate_outcome as validate_financial_outcome
from .service_contracts import validate_answer,assumption_checks
from .agent_contracts_v2 import validate_agent_answer
from .one_shot_contracts import validate_one_shot_answer
from .input_binding import resolve_input
from .scenario_contracts_v1 import REQUEST,OUTCOME,ELIGIBILITY,LABEL,REAL_LABEL,STAGES,validate_request,validate_outcome,dec
from .scenario_ledger import ScenarioBlocked,validate_dataset,schedule,simulate_paths

ROOT=Path(__file__).resolve().parents[2]
OWN=ROOT/'data/scenarios/kp3_scenario_v1'


class ScenarioContext:
    """Only trusted setup supplies this object; no paths/dataset/admissions in the request."""
    def __init__(self,financial,run_dir,dataset=None,source_path=None,guards=None):
        self.service=financial if hasattr(financial,'calculation')else None;self.calculation=financial.calculation if self.service else financial;self.dataset=deepcopy(dataset);self.source_path=Path(source_path).resolve()if source_path else None;self.guards=dict(guards or {});self.run_dir=Path(run_dir).resolve();need(self.run_dir.is_relative_to((ROOT/'tmp').resolve()),'private_run_dir_required');self.identity=self.current_identity();self.validate()
    def current_identity(self):return digest(dict(catalog=digest(self.calculation.catalog),admission=digest(self.calculation.admission),dictionary=digest(self.calculation.dictionary),dataset=self.dataset,source_path=str(self.source_path),guards=self.guards,service_identity=self.service.identity if self.service else None,run_dir=str(self.run_dir)))
    def validate(self):
        need(self.current_identity()==self.identity,'scenario_context_changed')
        for p,h in self.guards.items():need(Path(p).is_file()and file_sha(p)==h,'scenario_setup_changed')
        self.calculation.validate()
        if self.service:self.service.validate()
        if self.calculation.admission['data_origin']=='real':need(self.dataset is None and self.source_path is None,'real_synthetic_mixing_forbidden');need(self.service is not None,'real_retrieval_required');return
        validate_dataset(self.dataset);cat=self.calculation.catalog;need(cat['catalog_id']=='scenario12-own-financial-v1'and len(cat['documents'])==1 and all(f['fact_id'].startswith('scenario12-')for f in cat['facts']),'own_scenario_source_required');doc=cat['documents'][0];src=self.dataset['financial_source']
        need(self.source_path is not None and self.source_path.is_file(),'source_missing');need(file_sha(self.source_path)==src['sha256']==doc['sha256']and self.source_path.stat().st_size==src['byte_length']==doc['byte_length'],'source_version_mismatch');need(src['document_id']==doc['document_id']and src['version_id']==doc['version_id']and src['publication_digest']==digest(doc['publication']),'synthetic_availability_binding_mismatch')
        raw=self.source_path.read_text(encoding='utf8').splitlines()
        for f in cat['facts']:need('|'.join([f['fact_id'],f['period']['start'],f['period']['end'],f['metric_id'],f['value'],f['currency'],str(f['scale'])])in raw,'own_source_row_mismatch')
        stamp=available_from(doc)
        if stamp:need(stamp.date()>date.fromisoformat(doc['report_period']['end']),'publication_before_period_end')


def load_own_context(run_dir=None):
    setup=OWN/'setup.json';cfg=read_json(setup);shape(cfg,'schema_version catalog dictionary admission dataset source financial_request');need(cfg['schema_version']=='kp3-scenario-setup-0.1','unsupported_scenario_setup')
    paths={k:(ROOT/cfg[k]).resolve()for k in ['catalog','dictionary','admission','dataset','source','financial_request']};need(all(p.is_relative_to((ROOT/'data').resolve())for p in paths.values()),'untrusted_scenario_setup_path');calc=load_context(paths['catalog'],paths['dictionary'],paths['admission']);return ScenarioContext(calc,run_dir or ROOT/'tmp/scenario-runs',read_json(paths['dataset']),paths['source'],{str(p):file_sha(p)for p in [setup,*paths.values()]})


def own_financial(context,run_id='scenario12-own-financial'):
    context.validate();need(context.calculation.admission['data_origin']=='synthetic','own_scenario_source_required');req=read_json(OWN/'financial_request.json');req['request_id']=run_id;out=calculate(context.calculation,req,run_id);validate_calculation_binding(out,context.calculation,req);return out


def bridge(envelope,context,financial_run_id):
    schema=envelope.get('schema_version');method='calculation_v03';assumptions=[];unfulfilled=[];declared_context=None
    source_usage=dict(model_calls=envelope.get('model_calls',0),details=deepcopy(envelope.get('agent',envelope.get('selection',{})).get('usage')))
    if schema=='0.3':validate_financial_outcome(envelope);out=envelope;original_run_id=envelope['run_id']
    else:
        validators={'kp3-answer-0.1':validate_answer,'kp3-answer-0.2':validate_agent_answer,'kp3-a-answer-0.1':validate_one_shot_answer};need(schema in validators,'unsupported_financial_envelope');validators[schema](envelope);out=envelope['outcome'];original_run_id=envelope['run_id'];method=envelope['method'];assumptions=envelope['assumption_checks'];unfulfilled=envelope['unfulfilled_requests'];declared_context=envelope['context_digest']
    need(original_run_id==financial_run_id,'financial_run_mismatch')
    if out is None or out['execution_status']!='completed'or out['financial_status']!='answered':return dict(method=method,run_id=original_run_id,status='not_answered',source_execution_status=envelope.get('execution_status'),source_financial_status=envelope.get('financial_status'),source_request_status=envelope.get('request_status'),original_question=envelope.get('original_question'),reason_code=envelope['reason_code'],source_usage=source_usage,assumption_checks=deepcopy(assumptions),unfulfilled_requests=deepcopy(unfulfilled)),None
    result=out['financial_result'];req=result['request'];gate=context.service.retrieval if context.service else None;validate_calculation_binding(out,context.calculation,req,gate)
    if schema!='0.3':
        normalized=envelope['normalized_input'];fresh=resolve_input(normalized,context.calculation.catalog,context.calculation.dictionary);need(fresh['status']=='resolved'and fresh['request']==req,'financial_task_binding_mismatch');need(assumption_checks(normalized['assumptions'],out)==assumptions,'financial_assumption_mismatch')
    return dict(method=method,run_id=original_run_id,request_id=out['request_id'],status='verified',original_question=req['original_question'],request=deepcopy(req),outcome_digest=digest(out),declared_original_context_digest=declared_context,source_usage=source_usage,financial_result=deepcopy(result),assumption_checks=deepcopy(assumptions),unfulfilled_requests=deepcopy(unfulfilled)),result


def eligibility(context,request,financial):
    result=dict(schema_version=ELIGIBILITY,status='blocked',reason_codes=[],decision_at=request['decision_at'],availability=[],execution_policy='strict_next_declared_session_open_after_decision',next_entry_at=None,requirements={})
    if financial is None:result['reason_codes']=['financial_not_answered'];return result
    docs={d['document_id']:d for d in context.calculation.catalog['documents']};selected=list({f['document_id']:docs[f['document_id']]for f in financial['inputs']}.values());decision=instant(request['decision_at']);reasons=[]
    for d in selected:
        available=available_from(d);result['availability'].append(dict(document_id=d['document_id'],version_id=d['version_id'],document_sha256=d['sha256'],publication=deepcopy(d['publication']),available_from=None if available is None else available.isoformat(),semantics='fictional_own_availability'if d['data_origin']=='synthetic'else 'exact_issuer_publication'))
        if available is None:reasons.append('publication_unknown')
        elif decision<available:reasons.append('not_yet_available')
    if request['data_mode']=='real_source_readiness':
        result['requirements']=dict(verified_financial='ready',publication='unknown_or_time_checked',prices='unavailable',calendar='unavailable',corporate_actions='unchecked',price_rights='unconfirmed',execution='not_supported');reasons+=['real_prices_unavailable','real_calendar_unavailable','corporate_actions_unchecked','price_rights_unconfirmed','real_execution_not_supported']
    else:
        result['requirements']=dict(verified_financial='ready',prices='own_synthetic',calendar='own_synthetic_not_exchange_calendar',corporate_actions='none_in_declared_fixture',price_rights='self_created')
        if financial['operation_id']!='relative_change_v1'or financial['result_unit']!={'kind':'percent'}:reasons.append('scenario_rule_requires_relative_percent')
        if not reasons:
            try:times,entry,exit,prices=schedule(context.dataset,request);result['next_entry_at']=entry.isoformat()
            except ScenarioBlocked as e:reasons.append(e.code)
    result['reason_codes']=list(dict.fromkeys(reasons));result['status']='blocked'if reasons else 'eligible';return result


def evaluate(context,envelope,request,observed=None):
    """Stable pure-result portion with live finance/source validation, no run-file effects."""
    phases=observed if observed is not None else []
    def step(name,fn):
        start=perf_counter()
        try:value=fn();phases.append(dict(stage=name,status='completed',reason_code='ok',elapsed_ms=round((perf_counter()-start)*1000,4)));return value
        except Exception as e:phases.append(dict(stage=name,status='blocked'if isinstance(e,ScenarioBlocked)else 'error',reason_code=getattr(e,'code','scenario_execution_failed'),elapsed_ms=round((perf_counter()-start)*1000,4)));raise
    validate_request(request);context.validate();origin=context.calculation.admission['data_origin'];need((request['data_mode']=='own_synthetic')==(origin=='synthetic'),'real_synthetic_mixing_forbidden')
    fin,result=step('financial_validation',lambda:bridge(envelope,context,request['financial_run_id']));gate=step('eligibility',lambda:eligibility(context,request,result));base=dict(financial=fin,eligibility=gate,signal=None,scenario=None,comparisons=None)
    if gate['status']!='eligible':phases[-1].update(status='blocked',reason_code=gate['reason_codes'][0]);return dict(status='blocked',reason_code=gate['reason_codes'][0],**base)
    exact=result['exact_result'];signal=Fraction(int(exact['numerator']),int(exact['denominator']))>Fraction(dec(request['parameters']['threshold_pct']))
    try:main,comparisons=step('ledger',lambda:simulate_paths(context.dataset,request,signal))
    except ScenarioBlocked as e:return dict(status='blocked',reason_code=e.code,**base)
    base.update(signal=signal,scenario=main,comparisons=comparisons);return dict(status='completed',reason_code='signal_true'if signal else 'signal_false',**base)


def execute_scenario(envelope,request,context,run_id=None):
    rid=run_id or 'scenario-'+uuid4().hex;invalid=False;handle=None;phases=[]
    try:identifier(rid)
    except ContractError:rid='scenario-'+uuid4().hex;invalid=True
    mode=request.get('data_mode')if type(request)is dict else None;o=dict(schema_version=OUTCOME,run_id=rid,status='error',reason_code='invalid_request',data_mode=mode,label=LABEL if mode=='own_synthetic'else REAL_LABEL,request=deepcopy(request),context_digest=context.identity,financial=None,eligibility=None,signal=None,scenario=None,comparisons=None,trace=[],saved_run=None,model_calls=0)
    try:
        need(not invalid,'invalid_run_id');context.run_dir.mkdir(parents=True,exist_ok=True);p=context.run_dir/(hashlib.sha256(rid.encode()).hexdigest()+'.json')
        try:handle=p.open('x',encoding='utf8')
        except FileExistsError:raise ContractError('run_id_exists')from None
        o['saved_run']=dict(resource_id=p.name,private=True,status='written');core=evaluate(context,envelope,request,phases);o.update(core);start=perf_counter();expected=evaluate(context,envelope,request);need(digest(core)==digest(expected),'scenario_result_binding_mismatch');phases.append(dict(stage='result_validation',status='completed',reason_code='ok',elapsed_ms=round((perf_counter()-start)*1000,4)))
    except Exception as e:o.update(status='blocked'if isinstance(e,ScenarioBlocked)else 'error',reason_code=getattr(e,'code','scenario_execution_failed'),signal=None,scenario=None,comparisons=None)
    observed={p['stage']:p for p in phases};o['trace']=[dict(run_id=rid,**observed.get(name,dict(stage=name,status='skipped',reason_code='not_reached',elapsed_ms=0)))for name in STAGES];o['trace'][-1].update(status='completed'if handle else 'skipped',reason_code='written'if handle else 'run_not_reserved')
    try:
        validate_outcome(o)
        if handle:json.dump(o,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n');handle.close()
    except Exception as e:
        if handle:handle.close()
        o.update(status='error',reason_code=getattr(e,'code','scenario_write_failed'),signal=None,scenario=None,comparisons=None,saved_run=None);o['trace'][-1].update(status='error',reason_code=o['reason_code'])
    return o


def validate_scenario_binding(out,context,envelope,request):
    validate_outcome(out);need(out['request']==request and out['context_digest']==context.identity,'scenario_request_binding_mismatch');core=evaluate(context,envelope,request);need({k:out[k]for k in core}==core,'scenario_result_binding_mismatch')
