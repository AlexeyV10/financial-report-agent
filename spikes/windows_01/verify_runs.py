"""Validate recorded actual component runs, independently of GUI probe completion."""
from pathlib import Path
import argparse,json
ROOT=Path(__file__).resolve().parents[2]
EXPECTED=json.loads((Path(__file__).parent/'expected.json').read_text(encoding='utf8'))
def verify(label):
    events=json.loads((ROOT/'tmp/runs'/label/'ui.json').read_text(encoding='utf8'))
    calculations=[e for e in events if e['event']=='calculation']
    assert len(calculations)==2 and all(e['display']=='15.00' for e in calculations),label
    rendered=[e for e in events if e['event']=='render']
    assert [(e['rotation'],e['zoom']) for e in rendered]==[(0,1),(90,2),(180,2),(270,2),(0,2)],label
    for e in rendered:
        expected=[x*e['zoom']*e['dpi'] for x in EXPECTED['profit_pixel_rect_at_scale1'][str(e['rotation'])]]
        assert e['rect']==expected,(label,e)
    errors=[e for e in events if e['event']=='job_error']
    assert len(errors)==1 and errors[0]['exit']==23,label
    assert len([e for e in events if e['event']=='cancel'])==1,label
    assert not next(e for e in events if e['event']=='cancel_exit_probe')['still_running'],label
    assert next(e for e in events if e['event']=='table_probe')['selected']==1,label
    assert any(e['event']=='probe_complete' for e in events) and events[-1]['event']=='closed',label
    return dict(label=label,passed=True,calculations=2,render_states=5,crash_exit=23,cancelled_worker_gone_at_300ms=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('labels',nargs='+');a=p.parse_args()
    print(json.dumps([verify(x) for x in a.labels],indent=2))
