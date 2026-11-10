"""Offline replay only. No answering implementation, model, retrieval engine or network imports."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'evaluation'))
from kp3_protocol_v1.common import read,write_new
from kp3_protocol_v1.freeze import verify_freeze,read_raw
from kp3_protocol_v1.suite import validate_suite
from kp3_protocol_v1.metrics import summarize

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--raw-dir',type=Path,required=True);p.add_argument('--raw-manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--evaluator-controls',action='store_true');a=p.parse_args()
    m=verify_freeze(ROOT,a.freeze);inputs=read(ROOT/m['inputs_path']);gold=read(ROOT/m['gold_path']);protocol=read(ROOT/m['protocol_path']);validate_suite(inputs,gold,protocol);raw=read_raw(a.raw_dir,a.freeze,a.raw_manifest,a.evaluator_controls);metrics=summarize(inputs,gold,protocol,raw,a.evaluator_controls);write_new(a.output,metrics);print(json.dumps(dict(scope=metrics['scope'],raw_count=len(raw),model_calls_during_replay=0)));return 0

if __name__=='__main__':raise SystemExit(main())
