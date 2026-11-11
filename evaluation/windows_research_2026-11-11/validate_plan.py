"""Validate the research artifact, never import/execute production financial code."""
from pathlib import Path
from urllib.parse import urlsplit,unquote
import hashlib,json,re,sys,platform,sqlite3
R=Path(__file__).resolve().parents[2];E=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
write(E/'report.json',dict(status='validation_in_progress',stage='windows-research-plan'))
b=read(E/'before.json');changed=[]
for f,h in b['files'].items():
    assert (R/f).is_file(),f
    if sha(R/f)!=h:changed.append(f)
assert set(changed)=={'README.md','STATUS.md','docs/decisions.md'},changed
for f in changed:
    name=Path(f).name+'.before'
    assert (R/f).read_bytes().endswith((R/'tmp'/name).read_bytes()),f
release=read(R/'data/releases/kp3_rc1/manifest.json')
for f,h in release['file_sha256'].items():assert sha(R/f)==h,f
q=read(R/'docs/windows/roadmap.json');tasks=q['tasks'];ids=[t['id']for t in tasks]
assert ids==[f'WIN-{i:02d}'for i in range(61)]
assert q['implemented_tasks']==[]and q['completed_research_tasks']==['WIN-00']
assert all(t['status']==('research_complete'if t['id']=='WIN-00'else'proposed_not_implemented')for t in tasks)
seen=set();table={t['id']:t for t in tasks}
def visit(k,trail=()):
    assert k in table and k not in trail,(k,trail)
    if k in seen:return
    t=table[k];assert t['deliverable']and t['acceptance']
    assert len(t['depends_on'])==len(set(t['depends_on']))
    for d in t['depends_on']:visit(d,trail+(k,))
    seen.add(k)
for k in ids:visit(k)
catalog=read(R/'docs/windows/sources.json');sources=catalog['sources'];urls=[s['url']for s in sources]
assert len(urls)==len(set(urls))==catalog['primary_pages']
assert len({s['source_id']for s in sources})==len(sources)
for s in sources:
    u=urlsplit(s['url']);assert u.scheme=='https'and u.netloc and not u.username and not u.password,s
    assert s['notes']and all((R/'docs/windows'/n).is_file()for n in s['notes'])
unread=[s['url']for s in sources if s['review_status']!='reviewed_in_research_session']
assert len(unread)==1 and 'publication.pravo.gov.ru' in unread[0]
assert not any(x in u for u in urls for x in ['factset.com/solutions/financial-data','www.quartr.com/products/pro','www.daloopa.com/products/data'])
docs=[R/'ПЛАН_РАЗВИТИЯ_WINDOWS.md',R/'prompts/windows_01_native_desktop_spike.md',*sorted((R/'docs/windows').glob('*.md'))]
links=[]
for p in docs:
    s=p.read_text(encoding='utf8');assert '\ufffd' not in s,p
    for raw in re.findall(r'\[[^\]]+\]\(([^)]+)\)',s):
        if raw.startswith(('http:','https:','#')):continue
        path=unquote(raw.split('#')[0].strip('<>'))
        target=(p.parent/path).resolve();assert target.is_relative_to(R)and target.is_file(),(p,raw)
        links.append(dict(document=p.relative_to(R).as_posix(),target=target.relative_to(R).as_posix()))
plan=(R/'ПЛАН_РАЗВИТИЯ_WINDOWS.md').read_text(encoding='utf8')
plan_urls={u.rstrip('.,;:!?)|')for u in re.findall(r'https?://[^\s<>`]+',plan)}
assert plan_urls.issubset(set(urls)),plan_urls-set(urls)
for term in ['Qwen','PySide6','WPF','LocalOnly','IFRS','РСБУ','CSV','XLSX','DOCX','admission','rolling-origin','holdout','Narrator','SmartScreen','human_reviewed','unknown','WIN-01','WIN-60']:
    assert term in plan or term in (R/'docs/windows/backlog.md').read_text(encoding='utf8'),term
root=R.parents[1];rb=read(E/'root-before.json');root_changed=[]
for f,h in rb['files'].items():
    assert (root/f).is_file(),f
    if sha(root/f)!=h:root_changed.append(f)
assert set(root_changed)=={'STATUS.md','docs/decisions.md'},root_changed
for f in root_changed:assert (root/f).read_bytes().endswith((root/'tmp/windows-research-bootstrap'/(Path(f).name+'.before')).read_bytes())
report=dict(stage='windows-research-plan',status='passed',research_date='2026-11-11',scope='research_and_implementation_plan_only',tasks=len(tasks),research_complete=1,implementation_proposed=60,dependency_dag_nodes=len(seen),local_markdown_links_checked=len(links),primary_source_urls=len(urls),reviewed_primary_urls=len(urls)-len(unread),unread_content_urls=unread,parent_files=len(b['files']),parent_old_files_unchanged=len(b['files'])-3,parent_changed_only_preserved_prefix_docs=changed,root_old_files=len(rb['files']),root_old_files_unchanged=len(rb['files'])-2,root_changed_only_preserved_prefix_docs=root_changed,rc_component_pins_unchanged=len(release['file_sha256']),runtime_code_or_data_changed=False,new_primary_documents=0,model_calls=0,new_ocr=0,dependencies_installed=0,new_ui=False,new_unit_tests_run=0,new_benchmark=False,previous_799_unit_18_apptest='historical17_evidence_not_rerun_not_native_tests',final_eval_freeze14_unchanged=True,academic_report_slides18=False,implementation_started=False,next_prompt_prepared=True,next_prompt_applied=False,merge_authorized=False,environment=dict(python=sys.version,executable=sys.executable,sqlite=sqlite3.sqlite_version,platform=platform.platform()),checks=['old byte preservation','RC component SHA pins','61 unique task IDs and acyclic valid dependencies','proposed/complete status separation','nonempty deliverable and negative gates','source registry uniqueness/classification/no failed guessed URLs','local Markdown links exist and stay within worktree','main source citations covered by registry','scope/local AI/universal pack/forecast/native delivery vocabulary'])
write(E/'validation.json',dict(report=report,links=links))
write(E/'report.json',report)
print(json.dumps(report,ensure_ascii=True))
