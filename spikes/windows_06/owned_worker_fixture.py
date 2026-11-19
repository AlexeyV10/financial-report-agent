"""Fixed test worker that starts one child only after accepting stdin."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from financial_assistant.typed_ipc import MAX_REQUEST_BYTES, decode_request, encode_response


def main():
    marker = Path(sys.argv[1])
    request = decode_request(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
    child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(60)'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        result = {
            'workspace_id': 'synthetic-owned-tree', 'source_id': 'own-demo-v1', 'source_sha256': 'a' * 64,
            'source_page': 1, 'source_highlight': [1, 1, 2, 2], 'operation': 'operating_margin_v1',
            'display': '15.00', 'financial_status': 'answered', 'model_calls': 0,
        }
        sys.stdout.buffer.write(encode_response(request, result=result))
        sys.stdout.buffer.flush()
        with marker.open('x', encoding='ascii') as stream:
            json.dump({'worker': os.getpid(), 'child': child.pid}, stream)
        time.sleep(60)
    finally:
        child.terminate()
        child.wait(timeout=5)


if __name__ == '__main__':
    main()
