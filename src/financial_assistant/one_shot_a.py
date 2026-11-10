"""One primary search, one model choice, existing verified calculator. No repair dialogue."""
from copy import deepcopy
import hashlib,json,sys
from time import perf_counter
from uuid import uuid4
from .agent import bounded,encoded
from .contracts_v2 import ContractError,digest,identifier,need,shape
from .service_b import search_spec,resolve_evidence,_source_question
from .service_contracts import assumption_checks
from .input_contracts import clarification
from .input_binding import resolve_input
from .russian_input import parse_text,parse_form
from .agent_c import candidate_metadata
from . import retrieval_v2
from .financial_calculator import calculate,validate_calculation_binding
from .one_shot_contracts import VERSION,PROTOCOL,PROMPT,STAGES,SelectionLimits,choice_schema,bind_choice,validate_one_shot_answer


def _step(purpose,context,req,task,hits,top_k):
    """Trusted subprocess. Observe actual shared search calls without changing old code."""
    audit=[];frames={};code=retrieval_v2.search_index.__code__;previous=sys.getprofile();phase='catalog_filters'
    def observe(frame,event,arg):
        if frame.f_code is not code:return
        if event=='call':
            frames[id(frame)]=len(audit);audit.append(dict(purpose=purpose,spec_digest=digest(frame.f_locals['spec']),status='entered',reason_code=None,index_sha256=None))
        elif event=='return'and id(frame)in frames:
            row=audit[frames.pop(id(frame))];row.update(status=arg.get('status','unknown')if type(arg)is dict else 'raised',reason_code=arg.get('reason_code')if type(arg)is dict else None,index_sha256=arg.get('index_sha256')if type(arg)is dict else None)
    sys.setprofile(observe)
    try:
        context.validate();ctx=context.calculation;gate=context.retrieval
        fresh=resolve_input(task,ctx.catalog,ctx.dictionary);need(fresh['status']=='resolved'and fresh['request']==req,'binding_changed')
        if purpose=='primary':
            phase='search';spec=search_spec(req);spec['top_k']=top_k;hits=retrieval_v2.search_index(gate['db_path'],ctx.catalog,ctx.resources,gate['config'],gate['lexicon'],spec,gate['export_paths'])
            data=dict(hits=hits,pool=[])
            if hits['source_kind']=='prepared'and hits['status']=='found':
                phase='fact_resolution';resolve_evidence(ctx,req,hits);pool=candidate_metadata(ctx,req,hits);need(pool,'empty_prepared_pool')
                facts={f['fact_id']:f for f in ctx.catalog['facts']};evs={e['evidence_id']:e for e in ctx.catalog['evidence']};docs={d['document_id']:d for d in ctx.catalog['documents']}
                phase='source_validation'
                for item in pool:
                    f=facts[item['fact_id']];e=evs[f['evidence_id']];d=docs[f['document_id']];ctx.source_proof(f,e,d);ctx.check_local_source(d)
                data['pool']=pool
        else:
            phase='fact_resolution';need(purpose=='validation','invalid_worker_step');resolve_evidence(ctx,req,hits)
            phase='calculation';out=calculate(ctx,req,req['request_id'],gate);phase='result_validation';validate_calculation_binding(out,ctx,req,gate);context.validate();data=dict(outcome=out)
        return dict(ok=True,data=data,error=None,audit=audit,phase=phase)
    except Exception as e:return dict(ok=False,data=None,error=getattr(e,'code','tool_execution_failed'),audit=audit,phase=phase)
    finally:sys.setprofile(previous)


def execute_a(source,context,adapter,answers=None,run_id=None,limits=None):
    limits=limits or SelectionLimits();rid=run_id or 'a-'+uuid4().hex;invalid_rid=False;handle=None;start=perf_counter();active=None;started=0;task=None
    try:identifier(rid)
    except ContractError:rid='a-'+uuid4().hex;invalid_rid=True
    a=dict(schema_version=VERSION,run_id=rid,task_id=rid,method='A',execution_status='completed',request_status='pending',financial_status=None,reason_code='ok',original_question=_source_question(source),normalized_input=None,clarifications=[],financial_result=None,outcome=None,assumption_checks=[],unfulfilled_requests=[],retrieval=None,trace=[],context_digest=context.identity,source_input_digest=None,saved_run=None,model_calls=0,selection=dict(protocol=PROTOCOL,prompt=PROMPT,adapter=deepcopy(adapter.metadata),limits={},model_attempts=0,mock_choices=0,choice=None,choice_valid=False,usage=dict(input_tokens=None,output_tokens=None,known_chat_requests=0,unknown_requests=0),events=[],search_audit=[],primary_searches=0,validation_searches=0,unknown_search_steps=[],observation_digest=None,stop_reason='not_started'))
    s=a['selection'];stages={}
    def stage(name):
        nonlocal active,started
        active=name;started=perf_counter()
    def mark(status='completed',reason='ok',**details):
        nonlocal active
        stages[active]=dict(stage=active,run_id=rid,status=status,elapsed_ms=round((perf_counter()-started)*1000,4),reason_code=reason,details=details);active=None
    def event(kind,**details):s['events'].append(dict(kind=kind,run_id=rid,**details))
    def remaining():
        n=limits.timeout_s-(perf_counter()-start);need(n>0,'total_timeout');return min(limits.per_call_s,n)
    def worker(purpose,req,hits=None):
        nonlocal active
        t=perf_counter()
        try:r=bounded(_step,(purpose,context,req,task,hits,limits.top_k),remaining())
        except Exception as e:
            s['unknown_search_steps'].append(purpose);event('worker',purpose=purpose,status='error',reason_code=getattr(e,'code','worker_error'),elapsed_ms=round((perf_counter()-t)*1000,3),search_count=None);raise
        shape(r,'ok data error audit phase');s['search_audit'].extend(r['audit']);event('worker',purpose=purpose,status='completed'if r['ok']else 'error',phase=r['phase'],reason_code=r['error']or 'ok',elapsed_ms=round((perf_counter()-t)*1000,3),search_count=len(r['audit']))
        if not r['ok']:
            if purpose=='primary'and r['phase']in {'fact_resolution','source_validation'}:
                mark(actual_primary_search_completed=True);stage('fact_resolution')
                if r['phase']=='source_validation':mark(performed_in_primary_worker=True);stage('source_validation')
            elif r['phase']in STAGES:active=r['phase']
        need(r['ok'],r['error']or 'tool_execution_failed');return r['data']
    try:
        s['limits']=limits.validate();need(not invalid_rid,'invalid_run_id');need(s['adapter'].get('kind')in {'local_llm','mock'},'invalid_selection_adapter')
        context.run_dir.mkdir(parents=True,exist_ok=True);target=context.run_dir/(hashlib.sha256(rid.encode()).hexdigest()+'.json')
        try:handle=target.open('x',encoding='utf8')
        except FileExistsError:raise ContractError('run_id_exists')from None
        a['saved_run']=dict(resource_id=target.name,status='written',private=True);a['source_input_digest']=digest(dict(source=source,answers=answers))
        stage('input');src=deepcopy(source)
        if src.get('kind')=='text':shape(src,'kind input_id question');task=parse_text(src['question'],context.calculation.catalog,rid)
        else:shape(src,'kind form');need(src['kind']=='form','invalid_input_kind');src['form']['input_id']=rid;task=parse_form(src['form'],context.calculation.catalog)
        a['normalized_input']=task;mark()
        stage('catalog_filters');context.validate();binding=resolve_input(task,context.calculation.catalog,context.calculation.dictionary);patches=[]if answers is None else answers;need(type(patches)is list and len(patches)<=16,'clarification_limit')
        for patch in patches:binding=resolve_input(clarification(binding['normalized_input'],patch),context.calculation.catalog,context.calculation.dictionary)
        task=binding['normalized_input'];a.update(normalized_input=task,clarifications=binding['clarifications'],unfulfilled_requests=task['unfulfilled_requests'])
        if binding['status']!='resolved':
            status=binding['status'];mark('awaiting_clarification'if status=='awaiting_clarification'else 'error'if status=='error'else 'blocked',binding['reason_code'],preliminary_only=True)
            a.update(request_status=status,reason_code=binding['reason_code'],execution_status='awaiting_clarification'if status=='awaiting_clarification'else 'error'if status=='error'else 'completed');s['stop_reason']='input_not_resolved'
        else:
            req=binding['request'];mark(preliminary_only=True)
            stage('search');prepared=worker('primary',req);hits=prepared['hits'];pool=prepared['pool'];spec=search_spec(req);spec['top_k']=limits.top_k
            a['retrieval']=dict(run_id=rid,status=hits['status'],reason_code=hits['reason_code'],source_kind=hits['source_kind'],index_sha256=hits['index_sha256'],result_count=len(hits['results']),spec=spec)
            if hits['source_kind']!='prepared'or hits['status']!='found':
                reason='unverified_candidate'if hits['source_kind']!='prepared'else hits['reason_code'];mark('blocked',reason);a.update(request_status='missing',reason_code=reason);s['stop_reason']='search_blocked'
            else:
                mark(primary_search=True);stage('fact_resolution');mark(evidence_ids=[f['evidence_id']for f in pool],candidate_metadata=pool,source='found_prepared_only')
                stage('source_validation');mark(performed_in_primary_worker=True,primary_reannotation=False)
                stage('model_selection');scope={k:deepcopy(req[k])for k in ['organization_id','consolidation','accounting_standard','operation_id','mode','as_of','version_policy','result_unit']}
                scope['required_contexts']=[{k:deepcopy(r[k])for k in ['role','metric_id','definition_id','period','source_unit']}for r in req['inputs']];scope['documents']=list({r['document_id']:dict(document_id=r['document_id'],version_id=r['version_id'])for r in req['inputs']}.values())
                observation=dict(protocol=PROTOCOL,task=scope,candidates=pool,limits=s['limits'],choice_schema=choice_schema(req,pool));need(len(encoded(observation))<=limits.max_observation_bytes,'observation_too_large');s['observation_digest']=digest(observation)
                real=s['adapter']['kind']=='local_llm'
                if real:
                    t=perf_counter();probe=bounded(adapter.probe,(min(5,remaining()),),min(6,remaining()));event('setup_probe',result=probe,elapsed_ms=round((perf_counter()-t)*1000,3))
                s['model_attempts']=int(real);s['mock_choices']=int(not real);t=perf_counter()
                try:reply=bounded(adapter.choose,(observation,remaining()),remaining())
                except Exception as e:
                    event('choice',choice=None,usage=dict(input_tokens=None,output_tokens=None),chat_requests=None if real else 0,error=getattr(e,'code','adapter_error'),elapsed_ms=round((perf_counter()-t)*1000,3));s['usage']['unknown_requests']=int(real);raise
                try:
                    shape(reply,'choice usage chat_requests error diagnostic');shape(reply['usage'],'input_tokens output_tokens');need(all(v is None or type(v)is int and v>=0 for v in reply['usage'].values()),'invalid_usage');need(type(reply['chat_requests'])is int and reply['chat_requests']==int(real),'invalid_chat_accounting')
                except Exception:
                    event('choice',choice=None,usage=dict(input_tokens=None,output_tokens=None),chat_requests=None if real else 0,error='invalid_adapter_reply',elapsed_ms=round((perf_counter()-t)*1000,3));s['usage']['unknown_requests']=int(real);raise ContractError('invalid_adapter_reply')from None
                s['usage'].update(reply['usage']);s['usage']['known_chat_requests']=reply['chat_requests'];raw=reply['choice'];oversized=len(encoded(raw))>limits.max_choice_bytes
                s['choice']=None if oversized else deepcopy(raw);event('choice',choice=s['choice'],usage=reply['usage'],chat_requests=reply['chat_requests'],error='choice_too_large'if oversized else reply['error'],diagnostic=reply['diagnostic'],elapsed_ms=round((perf_counter()-t)*1000,3));need(not oversized,'choice_too_large');need(reply['error']is None,reply['error']or 'malformed_choice')
                selected=bind_choice(req,pool,raw);s['choice_valid']=True;mark(choice_valid=True,automatic_retries=0)
                stage('calculation');calculated=worker('validation',selected,hits);out=calculated['outcome'];mark('error'if out['execution_status']=='error'else 'completed',out['reason_code'],registered_operation_executed=out['financial_status']=='answered')
                stage('result_validation');mark(performed_in_calculation_worker=True,recomputation=True)
                a.update(outcome=out,financial_result=out['financial_result'],financial_status=out['financial_status'],request_status='evaluated'if out['execution_status']=='completed'else 'error',execution_status=out['execution_status'],reason_code=out['reason_code']);s['stop_reason']='completed'
    except Exception as e:
        code=getattr(e,'code','one_shot_execution_failed')
        if active:mark('error',code,error_type=type(e).__name__)
        a.update(execution_status='limit'if code in {'timeout','total_timeout','choice_too_large','observation_too_large','clarification_limit'}else 'error',request_status='error',reason_code=code,financial_status=None,financial_result=None,outcome=None);s['stop_reason']=code
    for purpose,key in [('primary','primary_searches'),('validation','validation_searches')]:s[key]=None if purpose in s['unknown_search_steps']else sum(r['purpose']==purpose for r in s['search_audit'])
    a['model_calls']=None if s['usage']['unknown_requests']else s['usage']['known_chat_requests'];a['assumption_checks']=assumption_checks(task['assumptions']if task else [],a['outcome'])
    stage('answer');mark(financial_result_present=a['financial_result']is not None)
    a['trace']=[stages.get(k,dict(stage=k,run_id=rid,status='skipped',elapsed_ms=0,reason_code='not_reached',details={}))for k in STAGES]
    try:
        validate_one_shot_answer(a)
        if handle:json.dump(a,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n');handle.close()
    except Exception as e:
        if handle:handle.close()
        a.update(execution_status='error',request_status='error',reason_code=getattr(e,'code','run_write_failed'),financial_status=None,financial_result=None,outcome=None,saved_run=None);a['assumption_checks']=assumption_checks(task['assumptions']if task else [],None);s['stop_reason']=a['reason_code'];a['trace'][-1].update(status='error',reason_code=a['reason_code'],details=dict(financial_result_present=False))
    return a
