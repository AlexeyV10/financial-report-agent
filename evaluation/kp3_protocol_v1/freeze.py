"""Content-addressed freeze and raw receipts. Replay needs no model/source/network."""
from pathlib import Path
from datetime import datetime,timezone
import ast
from .common import read,write_new,exact,require,file_sha,digest

def local(root,rel):
    require(type(rel)is str and '\\'not in rel and not Path(rel).is_absolute(),'unsafe_manifest_path');p=(Path(root)/rel).resolve();require(p.is_relative_to(Path(root).resolve()),'unsafe_manifest_path');return p

def runtime_isolation(root):
    paths=sorted((Path(root)/'src').rglob('*.py'))+sorted((Path(root)/'app_kp3').glob('*.py'));checked=[]
    for p in paths:
        text=p.read_text(encoding='utf8');ast.parse(text)
        require(not any(x in text for x in ['kp3_protocol_v1','kp3_eval_v1','kp3-gold-0.1','kp3-suite-0.1']),'runtime_reads_new_evaluator_or_gold');checked.append(p.relative_to(root).as_posix())
    return dict(checked_files=checked,new_gold_imports=0,scope='New14 evaluator isolated from existing answer paths; old legacy replay remains unchanged')

def create_freeze(root,output,files,logical_resources,protocol_path,inputs_path,gold_path):
    root=Path(root).resolve();out=Path(output).resolve();require(out.is_relative_to(root)and not out.exists(),'new_freeze_path_required');isolation=runtime_isolation(root);names=sorted(set(files));require(len(names)==len(files),'duplicate_freeze_file');require(out.relative_to(root).as_posix()not in names,'circular_manifest')
    hashes={name:file_sha(local(root,name))for name in names};require(all(type(x)is dict and set(x)=={'sha256','byte_length','kind'}for x in logical_resources.values()),'invalid_logical_resource')
    m=dict(schema_version='kp3-freeze-0.1',freeze_id='kp3-known-corpus-v1',created_at=datetime.now(timezone.utc).isoformat(),scope='Controlled known-corpus comparison; not unseen; no final answers yet',source_base_commit='053350a751a33c3ba4bbe11445444ef10efb4ce5',file_sha256=hashes,logical_resources=logical_resources,protocol_path=protocol_path,inputs_path=inputs_path,gold_path=gold_path,runtime_isolation=isolation,actual_final_method_attempts=0,reserved_unseen_real=0)
    for p in [protocol_path,inputs_path,gold_path]:require(p in hashes,'unhashed_core_artifact')
    write_new(out,m);return m

def verify_freeze(root,path,resources=None):
    m=read(path);exact(m,'schema_version freeze_id created_at scope source_base_commit file_sha256 logical_resources protocol_path inputs_path gold_path runtime_isolation actual_final_method_attempts reserved_unseen_real');require(m['schema_version']=='kp3-freeze-0.1'and m['actual_final_method_attempts']==0 and m['reserved_unseen_real']==0,'freeze_scope_invalid')
    for name,h in m['file_sha256'].items():require(file_sha(local(root,name))==h,'frozen_file_changed:'+name)
    if resources is not None:
        require(set(resources)==set(m['logical_resources']),'resource_binding_set_mismatch')
        for key,row in m['logical_resources'].items():
            p=Path(resources[key]);require(p.is_file()and p.stat().st_size==row['byte_length']and file_sha(p)==row['sha256'],'frozen_resource_changed:'+key)
    return m

def seal_raw(directory,freeze_path,observation_files,receipt_path,scope='actual'):
    directory=Path(directory).resolve();require(scope in {'actual','evaluator_control'},'invalid_raw_scope');rows={}
    for rel in observation_files:
        p=local(directory,rel);require(rel.endswith('.json')and rel not in rows,'invalid_raw_path');rows[rel]=file_sha(p)
    receipt=dict(schema_version='kp3-raw-manifest-0.1',freeze_sha256=file_sha(freeze_path),scope=scope,file_sha256=rows)
    write_new(receipt_path,receipt);return receipt

def read_raw(directory,freeze_path,receipt_path,allow_controls=False):
    receipt=read(receipt_path);exact(receipt,'schema_version freeze_sha256 scope file_sha256');require(receipt['schema_version']=='kp3-raw-manifest-0.1'and receipt['freeze_sha256']==file_sha(freeze_path),'raw_freeze_mismatch');require(receipt['scope']=='actual'or allow_controls and receipt['scope']=='evaluator_control','control_raw_not_actual');out=[]
    for rel,h in receipt['file_sha256'].items():
        p=local(directory,rel);require(file_sha(p)==h,'raw_hash_mismatch');row=read(p);require(row['source']==receipt['scope'],'raw_scope_mismatch');out.append(row)
    return out
