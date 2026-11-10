"""Human tables and paired stability from sealed actual observations; never calls a model."""
from pathlib import Path
from collections import Counter
from statistics import median
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_protocol_v1.common import read,write_new,require,file_sha,digest
from kp3_protocol_v1.freeze import verify_freeze,read_raw
from kp3_protocol_v1.metrics import summarize


def fraction(row):return str(row['x'])+'/'+str(row['n'])+' ('+row['status']+')'
def run(freeze,raw_dir,receipt,output):
    f=verify_freeze(ROOT,freeze);inputs=read(ROOT/f['inputs_path']);gold=read(ROOT/f['gold_path']);protocol=read(ROOT/f['protocol_path']);observations=read_raw(raw_dir,freeze,receipt);metrics=summarize(inputs,gold,protocol,observations);methods=[];errors=[];lookup={}
    for row in observations:
        slot=row['attempt_id'];a=row['answer'];lookup[(row['case_id'],row['method'],row['phase'])]=row
        if not isinstance(a,dict):errors.append(dict(attempt_id=slot,case_id=row['case_id'],method=row['method'],reason='malformed_or_interrupted',runner=row['measurement']))
    lines=['# КП3-16: сравнение на известном корпусе','Все40 вопросов и48Fact уже известны разработчику;32exact cells/28economic contexts/8versions/2lineages. Reserved/unseen0. Это сравнение данного прототипа, не качество рынка или unseen.','| Метод / этап | Числовой строгий ответ | Правильный отказ | Техническое завершение | Полнота32 | Claim support (наблюдённые) | Медиана end-to-end, мс | Chat |','|---|---|---|---|---|---|---:|---:|']
    for key,m in metrics['method_metrics'].items():
        lines.append('| '+key+' | '+fraction(m['numeric_correct'])+' | '+fraction(m['correct_refusal'])+' | '+fraction(m['technical_completion'])+' | '+fraction(m['answer_completeness'])+' | '+fraction(m['claim_support'])+' | '+str(round(m['elapsed']['median_ms'],2))+' | '+str(m['model_usage']['known_chat_requests'])+' |')
        for score in m['scores']:
            if not score['matched']:errors.append(dict(case_id=score['case_id'],method=score['method'],phase=key.split(':')[1],errors=score['errors'],numeric_correct=score['numeric_correct'],refusal_correct=score['refusal_correct']))
    stability=[]
    for method in ['B','A','C']:
        pairs=[]
        for (cid,met,phase),warm in lookup.items():
            if met!=method or phase!='warm_repeat':continue
            primary=lookup[(cid,method,'primary')]
            def signature(row):
                a=row['answer']
                if not isinstance(a,dict):return None
                r=a['financial_result'];return {k:a[k]for k in ['execution_status','request_status','financial_status','reason_code','original_question','assumption_checks','unfulfilled_requests']}|dict(result=None if r is None else {k:r[k]for k in ['operation_id','exact_result','display_value','result_unit','rounding']},input_fact_ids=None if r is None else [x['fact_id']for x in r['inputs']])
            pairs.append(dict(case_id=cid,stable=signature(primary)==signature(warm),primary_attempt=primary['attempt_id'],warm_attempt=warm['attempt_id'],primary_execution=primary['answer'].get('execution_status')if primary['answer']else None,warm_execution=warm['answer'].get('execution_status')if warm['answer']else None))
        stability.append(dict(method=method,x=sum(p['stable']for p in pairs),n=len(pairs),pairs=pairs))
    states=Counter(r['measurement']['cold_warm']for r in observations);stages={}
    for method in ['B','A','C']:
        agg={}
        for r in observations:
            if r['method']!=method or not isinstance(r['answer'],dict):continue
            for s in r['answer']['trace']:
                a=agg.setdefault(s['stage'],dict(statuses=Counter(),values=[]));a['statuses'][s['status']]+=1
                if s['status']!='skipped':a['values'].append(s['elapsed_ms'])
        stages[method]={k:dict(statuses=dict(a['statuses']),performed=len(a['values']),median_ms=median(a['values'])if a['values']else None)for k,a in agg.items()}
    search_counts=[]
    for method in ['A','C']:
        rows=[r for r in observations if r['method']==method and isinstance(r['answer'],dict)];values=[]
        for r in rows:
            a=r['answer']
            if method=='A':d=a['selection'];values.append(dict(attempt_id=r['attempt_id'],primary_searches=d['primary_searches'],validation_searches=d['validation_searches'],unknown_steps=d['unknown_search_steps'],choices=d['model_attempts']))
            else:d=a['agent'];values.append(dict(attempt_id=r['attempt_id'],search_tools=sum(e['kind']=='tool'and e.get('tool')=='search_evidence'for e in d['events']),decisions=d['decisions'],finished=d['finished'],receipt_id=d['receipt_id']))
        search_counts.append(dict(method=method,observations=values))
    analysis=dict(schema_version='kp3-comparison-analysis-0.1',scope='known_corpus_only',raw_manifest_sha256=file_sha(receipt),raw_count=len(observations),strict_metrics=metrics,errors=errors,stability=stability,model_load_states=dict(states),stage_timings=stages,search_method_diagnostics=search_counts,independent_source_clusters=2,reserved_unseen_real=0,confidence_interval='Not claimed: dependent facts/operations on2knownlineages',cost='Hardware/electricity/full monetary cost not measured',old_QA07='unchanged; new separate16 series',model_quality_limit='A metadata vs C checked values; task operations bounded; prepared pool often unambiguous')
    write_new(output,analysis);text='\n\n'.join(lines[:2])+'\n\n'+'\n'.join(lines[2:])+'\n\nПовторы: '+', '.join(x['method']+' '+str(x['x'])+'/'+str(x['n'])for x in stability)+'. Это6 прежних вопросов, не новый n.\n\nОшибка/limit не правильный финансовый отказ; отсутствие ответа остаётся в32. Claim support использует наблюдённые утверждения; потеря ответа учитывается полнотой32. Время — данного компьютера и фактических попыток; стадия не считается выполненной при skipped.\n';target=Path(output).with_suffix('.md')
    with target.open('x',encoding='utf8',newline='\n')as stream:stream.write(text)
    return dict(raw_count=len(observations),errors=len(errors),stability=stability,model_load_states=dict(states))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--raw-manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.freeze,a.raw_dir,a.raw_manifest,a.output),ensure_ascii=False))
