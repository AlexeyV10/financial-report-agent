"""Explicit multi-document retrieval CLI. All indexes, exports and result files stay in tmp/."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import ClarificationRequired,ContractError,read_json
from financial_assistant.document_extraction import ExtractionError,load_config
from financial_assistant.retrieval_v2 import RetrievalError,build_index,private_path,search_index


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['index','search'])
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--resources',type=Path,required=True,help='explicit local_resource_id to PDF path map')
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--kind',choices=['prepared','automatic'],help='required for index; never an implicit fallback')
    parser.add_argument('--exports',type=Path,help='automatic-only document_id to private worker export path map')
    parser.add_argument('--spec',type=Path,help='strict structured search spec; no inferred entity/year/version')
    parser.add_argument('--config',type=Path,default=ROOT/'data/extraction/kp3_pdf_v1/config.json')
    parser.add_argument('--lexicon',type=Path,default=ROOT/'data/extraction/kp3_pdf_v1/search_lexicon.json')
    parser.add_argument('--output',type=Path,help='optional new result file below tmp/')
    args=parser.parse_args()
    try:
        if args.output:
            private_path(args.output)
            if args.output.exists():raise RetrievalError('output_exists')
        catalog=read_json(args.catalog);resources=read_json(args.resources);cfg=load_config(args.config);lexicon=read_json(args.lexicon)
        exports=read_json(args.exports) if args.exports else None
        if args.action=='index':
            if args.kind is None:raise RetrievalError('explicit_index_kind_required')
            if args.spec is not None:raise RetrievalError('unexpected_search_spec')
            result=build_index(args.db,catalog,resources,cfg,lexicon,args.kind,exports)
        else:
            if args.spec is None:raise RetrievalError('search_spec_required')
            if args.kind is not None:raise RetrievalError('unexpected_index_kind')
            result=search_index(args.db,catalog,resources,cfg,lexicon,read_json(args.spec),exports)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except ClarificationRequired as exc:
        print(json.dumps(dict(status='awaiting_clarification',reason_code=exc.code,fields=list(exc.fields),financial_status=None,results=[]),ensure_ascii=False));return 2
    except (RetrievalError,ExtractionError,ContractError,OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps(dict(status='error',reason_code=getattr(exc,'code','invalid_input_or_io'),financial_status=None,results=[]),ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
