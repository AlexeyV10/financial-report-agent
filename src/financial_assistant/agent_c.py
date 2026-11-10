"""Model-controlled C. Bound IDs and receipts, mandatory live search, no B/manual fallback."""
from copy import deepcopy
from itertools import permutations
import hashlib,json
from time import perf_counter
from uuid import uuid4
from .contracts_v2 import ContractError,digest,identifier,need,shape
from .agent import bounded,encoded
from .agent_contracts_v2 import VERSION,PROTOCOL,PROMPT,AgentLimits,validate_agent_answer
from .service_contracts import STAGES,assumption_checks
from .service_b import search_spec,resolve_evidence,_source_question
from .input_contracts import clarification
from .input_binding import resolve_input
from .russian_input import parse_form,parse_text
from .retrieval_v2 import search_index
from .financial_calculator import calculate,validate_calculation_binding


def candidate_metadata(ctx,req,hits):
    if not hits or hits['source_kind']!='prepared':return []
    evidence_ids={r['evidence_id']for r in hits['results']};out=[]
    for f in ctx.catalog['facts']:
        if f['evidence_id']not in evidence_ids:continue
        # The search/filter scope is immutable, but does not give the model the selected IDs.
        if f['document_id']not in {r['document_id']for r in req['inputs']}:continue
        out.append({k:deepcopy(f[k])for k in ['fact_id','document_id','version_id','metric_id','definition_id','period','currency','scale','evidence_id']})
    return sorted(out,key=lambda f:f['fact_id'])


def _tool(ctx,req,task,tool,args,hits,outcome):
    """Trusted subprocess entry; only validated registered actions reach here."""
    try:
        ctx.validate();c=ctx.calculation;gate=ctx.retrieval
        fresh=resolve_input(task,c.catalog,c.dictionary);need(fresh['status']=='resolved'and fresh['request']==req,'binding_changed_after_search')
        if tool=='search_evidence':
            spec=search_spec(req);spec.update(query=args['query'],top_k=args['top_k'])
            return dict(ok=True,hits=search_index(gate['db_path'],c.catalog,c.resources,gate['config'],gate['lexicon'],spec,gate['export_paths']))
        need(hits is not None,'search_required');resolve_evidence(c,req,hits)
        # Re-run the same bound search, not an implicit manual fallback.
        spec=search_spec(req);spec['top_k']=hits['requested_top_k']
        live=search_index(gate['db_path'],c.catalog,c.resources,gate['config'],gate['lexicon'],spec,gate['export_paths'])
        resolve_evidence(c,req,live);need(digest(live['results'])==digest(hits['results']),'search_changed')
        facts={f['fact_id']:f for f in c.catalog['facts']};evs={e['evidence_id']:e for e in c.catalog['evidence']};docs={d['document_id']:d for d in c.catalog['documents']}
        if tool=='get_verified_fact':
            need(args['fact_id']in {f['fact_id']for f in candidate_metadata(c,req,live)},'fact_not_retrieved');selected=[dict(fact_id=args['fact_id'])]
        else:selected=req['inputs']
        for ref in selected:
            f=facts[ref['fact_id']];e=evs[f['evidence_id']];d=docs[f['document_id']];c.source_proof(f,e,d);c.check_local_source(d)
        if tool=='get_verified_fact':
            f=facts[args['fact_id']];return dict(ok=True,fact={k:deepcopy(f[k])for k in ['fact_id','document_id','version_id','metric_id','definition_id','period','currency','scale','value','evidence_id']},source_checked=True)
        if tool=='calculate':
            need(args['operation_id']==req['operation_id']and args['inputs']==[dict(role=r['role'],fact_id=r['fact_id'])for r in req['inputs']],'selected_binding_conflict')
            out=calculate(c,req,req['request_id'],gate);validate_calculation_binding(out,c,req,gate)
            return dict(ok=True,outcome=out,recomputed=True)
        if tool=='finish':
            if outcome is not None:validate_calculation_binding(outcome,c,req,gate)
            return dict(ok=True,validated=True)
        raise ContractError('unknown_tool')
    except Exception as e:return dict(ok=False,error=getattr(e,'code','tool_execution_failed'),error_type=type(e).__name__)


def _schema(tool,props):
    return dict(type='object',properties=dict(tool=dict(const=tool),arguments=dict(type='object',properties=props,required=list(props),additionalProperties=False)),required=['tool','arguments'],additionalProperties=False)


def schemas(req,state,fetched,top,limits,receipt,pool=None):
    if receipt:return dict(oneOf=[_schema('finish',dict(receipt_id=dict(const=receipt['receipt_id'])))])
    choices=[]
    if top<limits.max_search_results:
        choices.append(_schema('search_evidence',dict(query=dict(const=search_spec(req)['query']),top_k=dict(type='integer',minimum=max(1,top+1),maximum=limits.max_search_results))))
    if state=='searched':
        for ref in pool or []:
            if ref['fact_id']not in fetched:choices.append(_schema('get_verified_fact',dict(fact_id=dict(const=ref['fact_id']))))
        if len(fetched)>=len(req['inputs']):
            combinations=[[dict(role=ref['role'],fact_id=fid)for ref,fid in zip(req['inputs'],ids)]for ids in permutations(fetched,len(req['inputs']))]
            choices.append(_schema('calculate',dict(operation_id=dict(const=req['operation_id']),inputs=dict(type='array',enum=combinations))))
    return dict(oneOf=choices)


def _validate_action(action,schema):
    shape(action,'tool arguments');need(type(action['tool'])is str and type(action['arguments'])is dict,'invalid_action')
    options=[o for o in schema['oneOf']if o['properties']['tool']['const']==action['tool']]
    need(options,'tool_not_allowed')
    for o in options:
        props=o['properties']['arguments']['properties'];args=action['arguments']
        if set(args)!=set(props):continue
        if all((args[k]==s['const']and type(args[k])is type(s['const']))if 'const'in s else (type(args[k])is list and args[k]in s['enum'])if 'enum'in s else type(args[k])is int and s['minimum']<=args[k]<=s['maximum']for k,s in props.items()):return
    raise ContractError('invalid_tool_arguments')


def execute_c(source,context,adapter,answers=None,run_id=None,limits=None):
    limits=limits or AgentLimits();rid=run_id or 'c-'+uuid4().hex;handle=None;start=perf_counter();req=None;hits=None;pending=None;receipt=None;fetched=[];pool=[];top=0;state='ready';task=None;invalid_rid=False
    try:identifier(rid)
    except ContractError:rid='c-'+uuid4().hex;invalid_rid=True
    meta=deepcopy(adapter.metadata)
    a=dict(schema_version=VERSION,run_id=rid,task_id=rid,method='C',execution_status='completed',request_status='pending',financial_status=None,reason_code='ok',original_question=_source_question(source),normalized_input=None,clarifications=[],financial_result=None,outcome=None,assumption_checks=[],unfulfilled_requests=[],retrieval=None,trace=[],context_digest=context.identity,source_input_digest=None,saved_run=None,model_calls=0,agent=dict(protocol=PROTOCOL,prompt=PROMPT,adapter=meta,limits={},decisions=0,model_attempts=0,mock_decisions=0,usage=dict(known_input_tokens=0,known_output_tokens=0,unknown_usage=0,known_chat_requests=0,unknown_requests=0),events=[],stop_reason='not_started',finished=False,receipt_id=None))
    ag=a['agent'];stages={};active_stage=None
    def mark(name,status,reason,ms=0,**details):
        previous=stages.get(name,{});stages[name]=dict(stage=name,run_id=rid,status=status,elapsed_ms=round(previous.get('elapsed_ms',0)+ms,4),reason_code=reason,details={**previous.get('details',{}),**details})
    def event(kind,**details):ag['events'].append(dict(kind=kind,run_id=rid,**details))
    def terminal(status,reason,execution='completed',outcome=None):
        nonlocal state,receipt
        receipt=dict(request_status=status,reason_code=reason,execution_status=execution,outcome=deepcopy(outcome));receipt['receipt_id']='receipt-'+digest(dict(run_id=rid,revision=top,payload=receipt))[:24];state='terminal';ag['receipt_id']=receipt['receipt_id'];event('receipt',receipt_id=receipt['receipt_id'],request_status=status,reason_code=reason,execution_status=execution)
    def time_left():return limits.timeout_s-(perf_counter()-start)
    def worker(tool,args):return bounded(_tool,(context,req,task,tool,args,hits,pending),min(limits.per_call_s,max(0,time_left())))
    try:
        ag['limits']=limits.validate();need(not invalid_rid,'invalid_run_id');need(meta.get('kind')in {'local_llm','mock'},'invalid_adapter_kind')
        context.run_dir.mkdir(parents=True,exist_ok=True);target=context.run_dir/(hashlib.sha256(rid.encode()).hexdigest()+'.json')
        try:handle=target.open('x',encoding='utf8')
        except FileExistsError:raise ContractError('run_id_exists')from None
        a['saved_run']=dict(resource_id=target.name,status='written',private=True);a['source_input_digest']=digest(dict(source=source,answers=answers))
        src=deepcopy(source);t=perf_counter();active_stage='input'
        if src.get('kind')=='text':shape(src,'kind input_id question');task=parse_text(src['question'],context.calculation.catalog,rid)
        else:shape(src,'kind form');need(src['kind']=='form','invalid_input_kind');src['form']['input_id']=rid;task=parse_form(src['form'],context.calculation.catalog)
        a['normalized_input']=task;mark('input','completed','ok',(perf_counter()-t)*1000);active_stage=None
        t=perf_counter();active_stage='catalog_filters';context.validate();binding=resolve_input(task,context.calculation.catalog,context.calculation.dictionary);patches=[]if answers is None else answers;need(type(patches)is list and len(patches)<=16,'clarification_limit')
        for patch in patches:binding=resolve_input(clarification(binding['normalized_input'],patch),context.calculation.catalog,context.calculation.dictionary)
        task=binding['normalized_input'];a.update(normalized_input=task,clarifications=binding['clarifications'],unfulfilled_requests=task['unfulfilled_requests'])
        mark('catalog_filters','completed'if binding['status']=='resolved'else 'awaiting_clarification'if binding['status']=='awaiting_clarification'else 'blocked',binding['reason_code'],(perf_counter()-t)*1000,preliminary_only=True)
        active_stage=None
        if binding['status']!='resolved':
            a.update(request_status=binding['status'],reason_code=binding['reason_code'],execution_status='awaiting_clarification'if binding['status']=='awaiting_clarification'else 'error'if binding['status']=='error'else 'completed');ag['stop_reason']='input_not_resolved'
        else:
            req=binding['request'];context.validate()
            if meta['kind']=='local_llm':
                t=perf_counter();probe=bounded(adapter.probe,(min(5,max(0,time_left())),),min(6,max(0,time_left())));event('setup_probe',elapsed_ms=round((perf_counter()-t)*1000,3),result=probe)
            while ag['decisions']<limits.max_calls:
                need(time_left()>0,'total_timeout')
                if ag['decisions']==limits.max_calls-1 and receipt is None:terminal('error','call_limit','limit')
                sc=schemas(req,state,fetched,top,limits,receipt,pool);need(sc['oneOf'],'no_allowed_transition')
                scope={k:deepcopy(req[k])for k in ['organization_id','consolidation','accounting_standard','operation_id','mode','as_of','version_policy','result_unit']}
                scope['required_contexts']=[{k:deepcopy(ref[k])for k in ['role','metric_id','definition_id','period','source_unit']}for ref in req['inputs']]
                scope['documents']=list({r['document_id']:dict(document_id=r['document_id'],version_id=r['version_id'])for r in req['inputs']}.values())
                obs=dict(protocol=PROTOCOL,run_id=rid,state=state,task=scope,candidates=deepcopy(pool),search_keywords=search_spec(req)['query'],limits=ag['limits'],remaining_calls=limits.max_calls-ag['decisions'],fetched_fact_ids=list(fetched),receipt={k:v for k,v in receipt.items()if k!='outcome'}if receipt else None,last_result=ag['events'][-1].get('result')if ag['events']else None,tool_schemas=sc)
                need(len(encoded(obs))<=limits.max_observation_bytes,'observation_too_large')
                ag['decisions']+=1;real=meta['kind']=='local_llm';ag['model_attempts']+=int(real);ag['mock_decisions']+=int(not real);t=perf_counter();reply=None
                try:reply=bounded(adapter.decide,(obs,min(limits.per_call_s,max(0,time_left()))),min(limits.per_call_s,max(0,time_left())))
                except Exception as e:
                    event('decision',number=ag['decisions'],state=state,action=None,error=getattr(e,'code','adapter_error'),usage=dict(input_tokens=None,output_tokens=None),chat_requests=None if real else 0,elapsed_ms=round((perf_counter()-t)*1000,3));ag['usage']['unknown_usage']+=1;ag['usage']['unknown_requests']+=int(real);raise
                try:
                    shape(reply,'action usage chat_requests error');usage=reply['usage'];shape(usage,'input_tokens output_tokens');chat=reply['chat_requests'];need(type(chat)is int and chat==(1 if real else 0),'invalid_chat_accounting')
                    need(all(v is None or type(v)is int and v>=0 for v in usage.values()),'invalid_usage')
                except Exception:
                    event('decision',number=ag['decisions'],state=state,action=None,error='invalid_adapter_reply',usage=dict(input_tokens=None,output_tokens=None),chat_requests=None if real else 0,elapsed_ms=round((perf_counter()-t)*1000,3));ag['usage']['unknown_usage']+=1;ag['usage']['unknown_requests']+=int(real);raise ContractError('invalid_adapter_reply')from None
                ag['usage']['known_chat_requests']+=chat
                for key,label in [('input_tokens','known_input_tokens'),('output_tokens','known_output_tokens')]:
                    value=usage[key];need(value is None or type(value)is int and value>=0,'invalid_usage')
                    if value is not None:ag['usage'][label]+=value
                ag['usage']['unknown_usage']+=int(any(v is None for v in usage.values()))
                # Never log free narrative/reasoning; only size-bounded structured action.
                action=reply['action']
                if len(encoded(action))>limits.max_action_bytes:
                    event('decision',number=ag['decisions'],state=state,action=None,error='action_too_large',usage=usage,chat_requests=chat,elapsed_ms=round((perf_counter()-t)*1000,3));raise ContractError('action_too_large')
                row=dict(number=ag['decisions'],state=state,action=action,error=reply['error'],usage=usage,chat_requests=chat,elapsed_ms=round((perf_counter()-t)*1000,3));event('decision',**row)
                if reply['error']in {'timeout','adapter_unavailable','invalid_model_response'}:raise ContractError(reply['error'])
                try:_validate_action(action,sc)
                except Exception as e:event('rejected_action',reason_code=getattr(e,'code','malformed_action'));continue
                tool=action['tool'];args=action['arguments'];t=perf_counter()
                if tool=='calculate'and args['inputs']!=[dict(role=r['role'],fact_id=r['fact_id'])for r in req['inputs']]:event('rejected_action',reason_code='selected_binding_conflict');continue
                if tool=='finish'and (pending is None):result=dict(ok=True,validated=True) # early refusal has no arithmetic to recompute
                else:
                    try:result=worker(tool,args)
                    except Exception as e:event('tool',tool=tool,arguments=args,result=dict(ok=False,error=getattr(e,'code','tool_error')),elapsed_ms=round((perf_counter()-t)*1000,3));raise
                elapsed=(perf_counter()-t)*1000
                if not result['ok']:
                    event('tool',tool=tool,arguments=args,result=result,elapsed_ms=round(elapsed,3));mark('search'if tool=='search_evidence'else 'source_validation','error',result['error'],elapsed);pending=None;terminal('error',result['error'],'error');continue
                if tool=='search_evidence':
                    hits=result['hits'];hits['requested_top_k']=args['top_k'];top=args['top_k'];fetched=[];pending=None;receipt=None;pool=candidate_metadata(context.calculation,req,hits)
                    a['retrieval']=dict(run_id=rid,status=hits['status'],reason_code=hits['reason_code'],source_kind=hits['source_kind'],index_sha256=hits['index_sha256'],result_count=len(hits['results']),spec={**search_spec(req),'top_k':top})
                    summary=dict(status=hits['status'],reason_code=hits['reason_code'],source_kind=hits['source_kind'],top_k=top,evidence_ids=[r['evidence_id']for r in hits['results']],candidate_metadata=pool,fetched_invalidated=True)
                    if hits['source_kind']!='prepared':terminal('missing','unverified_candidate')
                    elif hits['status']=='found':state='searched'
                    elif top==limits.max_search_results or hits['status']not in {'partial','not_found'}:terminal('missing',hits['reason_code'])
                    else:state='partial'
                    mark('search','completed'if state=='searched'else 'blocked',hits['reason_code'],elapsed,mandatory=True,source_kind=hits['source_kind'])
                elif tool=='get_verified_fact':
                    fetched.append(args['fact_id']);summary=result;mark('fact_resolution','completed','ok',elapsed,evidence_required=True);mark('source_validation','completed','ok',0,checked_before_values=True)
                elif tool=='calculate':
                    pending=result['outcome'];summary=dict(status=pending['financial_status'],reason_code=pending['reason_code'],registered_operation=req['operation_id'],validated=True)
                    terminal('evaluated',pending['reason_code'],pending['execution_status'],pending if pending['execution_status']=='completed'else None);mark('calculation','completed'if pending['execution_status']=='completed'else 'error',pending['reason_code'],elapsed,registered_operation_executed=pending['financial_status']=='answered');mark('result_validation','completed','ok',0,recomputation=True)
                else:
                    need(receipt is not None,'receipt_required');context.validate()
                    a.update(request_status=receipt['request_status'],reason_code=receipt['reason_code'],execution_status=receipt['execution_status'],outcome=receipt['outcome'])
                    if receipt['outcome']:a.update(financial_status=receipt['outcome']['financial_status'],financial_result=receipt['outcome']['financial_result'])
                    ag.update(finished=True,stop_reason='finished');summary=dict(validated=True,receipt_id=receipt['receipt_id']);state='finished'
                need(len(encoded(summary))<=limits.max_tool_bytes,'tool_summary_too_large');event('tool',tool=tool,arguments=args,result=summary,elapsed_ms=round(elapsed,3))
                if state=='finished':break
            if not ag['finished']:raise ContractError('call_limit')
    except Exception as e:
        code=getattr(e,'code','agent_execution_failed')
        if active_stage:mark(active_stage,'error',code,(perf_counter()-t)*1000)
        a.update(execution_status='limit'if code in {'call_limit','timeout','total_timeout','observation_too_large','tool_summary_too_large','action_too_large','clarification_limit'}else 'error',request_status='error',reason_code=code,financial_status=None,financial_result=None,outcome=None);ag['stop_reason']=code
    a['model_calls']=None if ag['usage']['unknown_requests']else ag['usage']['known_chat_requests']
    a['assumption_checks']=assumption_checks(task['assumptions']if task else [],a['outcome'])
    mark('answer','completed',a['reason_code'],0,financial_result_present=a['financial_result']is not None)
    a['trace']=[stages.get(k,dict(stage=k,run_id=rid,status='skipped',elapsed_ms=0,reason_code='not_reached',details={}))for k in STAGES]
    try:
        validate_agent_answer(a)
        if handle:json.dump(a,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n');handle.close()
    except Exception as e:
        if handle:handle.close()
        a.update(execution_status='error',request_status='error',reason_code=getattr(e,'code','run_write_failed'),financial_status=None,financial_result=None,outcome=None,saved_run=None);a['assumption_checks']=assumption_checks(task['assumptions']if task else [],None);ag['stop_reason']=a['reason_code'];a['trace'][-1].update(status='error',reason_code=a['reason_code'],details=dict(financial_result_present=False))
    return a
