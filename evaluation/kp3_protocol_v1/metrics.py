"""Offline planned denominators, separate queries, actual/unknown usage and timing."""
from statistics import median
from .common import require,exact,digest
from .evaluator import evaluate_financial

def rate(x,n,observed,planned=None):return dict(x=x,n=n,status='not_measured'if n==0 or observed==0 else'partial'if observed<(n if planned is None else planned)else'measured')
def timings(values):return dict(n=len(values),minimum_ms=min(values)if values else None,median_ms=median(values)if values else None,maximum_ms=max(values)if values else None)

def summarize(inputs,gold,protocol,observations,allow_controls=False):
    cases={c['case_id']:c for c in inputs['cases']};gs={g['case_id']:g for g in gold['cases']};planned={r['attempt_id']:r for r in protocol['order']};seen={};run_ids=set();errors=[]
    for row in observations:
        exact(row,'schema_version attempt_id case_id method phase source answer measurement');require(row['schema_version']=='kp3-observation-0.1','observation_schema');require(row['source']=='actual'or allow_controls and row['source']=='evaluator_control','nonactual_observation_forbidden')
        key=row['attempt_id'];require(key in planned,'unknown_attempt_id');require(key not in seen,'duplicate_attempt_id');require(all(row[k]==planned[key][k]for k in ['case_id','method','phase']),'attempt_context_mismatch')
        if type(row['answer'])is dict and row['answer'].get('run_id')is not None:
            rid=row['answer']['run_id'];require(type(rid)is str and rid not in run_ids,'duplicate_service_run_id');run_ids.add(rid)
        seen[key]=row
    out={}
    for method in protocol['methods']:
        for phase in ['primary','warm_repeat']:
            slots=[p for p in protocol['order']if p['method']==method and p['phase']==phase];scores=[];elapsed=[];numeric_n=refusal_n=0;observed_numeric=observed_refusals=0;known_chats=unknown_requests=0;tokens={'input':0,'output':0,'unknown_records':0}
            for slot in slots:
                g=gs[slot['case_id']];isnum=g['result']is not None;numeric_n+=isnum;refusal_n+=not isnum
                row=seen.get(slot['attempt_id'])
                if row is None:continue
                require(row['measurement'].get('cold_warm')in {'cold','warm','unknown'},'cold_warm_required');ms=row['measurement'].get('elapsed_ms');require(ms is None or type(ms)in {int,float}and 0<=ms<86400000,'invalid_elapsed_ms')
                if ms is not None:elapsed.append(ms)
                score=evaluate_financial(cases[slot['case_id']],g,row['answer'])
                if score['method']!=method:
                    score['errors'].append('scheduled_method_mismatch');score.update(matched=False,numeric_correct=False,refusal_correct=False,technical_completed=False,complete_claims=False)
                scores.append(score);observed_numeric+=isnum;observed_refusals+=not isnum
                chats=score['usage']['chat_requests'];known_chats+=chats or 0;unknown_requests+=score['usage']['unknown_requests'];u=score['usage']['usage']
                if u is None:tokens['unknown_records']+=int(method!='B')
                elif method=='A':
                    for side,key in [('input','input_tokens'),('output','output_tokens')]:
                        if u.get(key)is None:tokens['unknown_records']+=1
                        else:tokens[side]+=u[key]
                else:tokens['input']+=u.get('known_input_tokens',0);tokens['output']+=u.get('known_output_tokens',0);tokens['unknown_records']+=u.get('unknown_usage',0)
            num=sum(s['numeric_correct']for s in scores);ref=sum(s['refusal_correct']for s in scores);claims=sum(s['observed_claims']for s in scores)
            out[method+':'+phase]=dict(planned_attempts=len(slots),observed_attempts=len(scores),missing_attempts=len(slots)-len(scores),numeric_correct=rate(num,numeric_n,observed_numeric),correct_refusal=rate(ref,refusal_n,observed_refusals),false_refusal=rate(sum(s['false_refusal']for s in scores),numeric_n,observed_numeric),technical_completion=rate(sum(s['technical_completed']for s in scores),len(slots),len(scores)),claim_support=rate(sum(s['supported_claims']for s in scores),claims,len(scores),len(slots)),answer_completeness=rate(sum(s['complete_claims']for s in scores),numeric_n,observed_numeric),elapsed=timings(elapsed),model_usage=dict(known_chat_requests=known_chats,unknown_requests=unknown_requests,tokens=tokens,total_cost='not_measured'),scores=scores)
    return dict(schema_version='kp3-metrics-0.1',scope='evaluator_controls_only'if allow_controls else'known_corpus_comparison',method_metrics=out,raw_count=len(observations),errors=errors,reserved_unseen_real=0)

def evaluate_retrieval(target,observation):
    required={e['evidence_id']:e for e in target['required_evidence']};covered=set();technical=observation.get('status')in {'error','limit'}
    if not technical and observation.get('source_kind')=='prepared'and observation.get('status')=='found':
        for row in observation.get('results',[]):
            e=required.get(row.get('evidence_id'))
            if e and row.get('source_kind')=='prepared_evidence'and row.get('verification_status')in {'assistant_checked','human_reviewed'}and row.get('evidence_digest')==digest(e)and row.get('locator')==e['locator']and all(row.get(k)==e[k]for k in ['document_id','version_id','document_sha256','metric_id','definition_id','period','currency','scale','raw_value']):covered.add(e['evidence_id'])
    return dict(query_id=target['query_id'],matched_evidence=len(covered),required_evidence=len(required),complete=covered==set(required)and not technical,technical_error=technical)

def retrieval_metrics(targets,observations):
    lookup={r['query_id']:r['observation']for r in observations};require(len(lookup)==len(observations),'duplicate_query_observation');required={q['query_id']for q in targets['queries']};require(set(lookup)<=required,'unknown_query_observation');rows=[]
    for q in targets['queries']:rows.append(evaluate_retrieval(q,lookup.get(q['query_id'],dict(status='not_observed',source_kind=None))))
    return dict(unique_queries=len(rows),observed_queries=len(lookup),evidence_at_k=rate(sum(r['matched_evidence']for r in rows),sum(r['required_evidence']for r in rows),len(lookup),len(rows)),complete_retrieval_at_k=rate(sum(r['complete']for r in rows),len(rows),len(lookup)),rows=rows)
