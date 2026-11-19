"""Typed JSONL boundary tests with only scripted, test-owned child processes."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from time import monotonic
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from financial_assistant import typed_ipc as ipc


CONTEXT = 'a' * 64
OTHER_CONTEXT = 'b' * 64
RUN = 'run-ipc-1'
RESULT = dict(workspace_id='own-test-vault', source_id='own-demo-v1', source_sha256='c' * 64,
              source_page=1, source_highlight=[2, 3, 20, 31], operation='operating_margin_v1',
              display='15.00', financial_status='answered', model_calls=0)

# The child only checks its input and writes test-owned pipe bytes.
CHILD = '''
import sys
import time

mode, reply, expected_request, limit = sys.argv[1:]
payload = bytes.fromhex(reply)
request = bytes.fromhex(expected_request)
if sys.stdin.buffer.read(len(request) + 1) != request:
    raise SystemExit(12)
if mode == 'response-overflow':
    payload = b'x' * (int(limit) + 1)
sys.stdout.buffer.write(payload)
sys.stdout.buffer.flush()
if mode == 'stderr-overflow':
    sys.stderr.buffer.write(b'x' * (int(limit) + 1))
    sys.stderr.buffer.flush()
elif mode == 'warning':
    sys.stderr.buffer.write(b'own test-only diagnostic')
elif mode == 'nonzero':
    raise SystemExit(11)
elif mode == 'wait-after-success':
    time.sleep(15)
'''


def raw_record(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


class WireTests(unittest.TestCase):
    def setUp(self):
        self.request = ipc.make_request(CONTEXT, RUN)

    def assert_code(self, code, call, *args, **kwargs):
        with self.assertRaises(ipc.TypedIpcError) as raised:
            call(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)

    def test_valid_request_round_trips_exactly(self):
        encoded = ipc.encode_request(self.request)
        self.assertIsInstance(encoded, bytes)
        self.assertTrue(encoded.endswith(b'\n'))
        self.assertEqual(ipc.decode_request(encoded), self.request)

    def test_extra_command_fields_and_unknown_command_are_denied(self):
        variants = [dict(self.request, command='unknown'), dict(self.request, extra='opaque'),
                    dict(self.request, run_id=True)]
        for malformed_context in ('../outside', CONTEXT[:-1], CONTEXT + 'a', CONTEXT.upper(), 'g' * 64):
            self.assert_code('invalid_request', ipc.make_request, malformed_context, RUN)
            variants.append(dict(self.request, context_id=malformed_context))
        for extra_key in ('path', 'sql', 'argv'):
            request = deepcopy(self.request)
            request['arguments'][extra_key] = 'not part of this protocol'
            variants.append(request)
        for request in variants:
            with self.subTest(request=request):
                self.assert_code('invalid_request', ipc.encode_request, request)
                self.assert_code('invalid_request', ipc.decode_request, raw_record(request))

    def test_malformed_request_frames_are_denied(self):
        encoded = ipc.encode_request(self.request)
        invalid_frames = (
            encoded[:-1], encoded[:-2] + b'\n', encoded[:-1] + b'\r\n',
            encoded + b'\n', encoded + encoded, b'\xef\xbb\xbf' + encoded,
            encoded[:-2] + b',"run_id":"duplicate"}\n',
            encoded.replace(b'"own-demo-v1"', b'"\xff"'),
            encoded.replace(b'"own-demo-v1"', b'NaN'),
        )
        for frame in invalid_frames:
            with self.subTest(frame=frame[-96:]):
                self.assert_code('invalid_request', ipc.decode_request, frame)

    def test_wire_size_limits_apply_before_decoding(self):
        too_big_request = b' ' * ipc.MAX_REQUEST_BYTES + b'\n'
        too_big_response = b' ' * ipc.MAX_RESPONSE_BYTES + b'\n'
        self.assert_code('request_too_large', ipc.decode_request, too_big_request)
        self.assert_code('response_too_large', ipc.decode_response, too_big_response, self.request)

    def test_valid_success_and_failure_have_distinct_result_invariants(self):
        success = ipc.decode_response(ipc.encode_response(self.request, result=RESULT), self.request)
        self.assertEqual(success['status'], 'completed')
        self.assertEqual(success['result'], RESULT)
        self.assertIsNone(success['error'])

        failure = ipc.decode_response(ipc.encode_response(self.request, error='source_missing'), self.request)
        self.assertEqual(failure['status'], 'failed')
        self.assertEqual(failure['error'], 'source_missing')
        self.assertIsNone(failure['result'])

        self.assert_code('invalid_response', ipc.decode_response, raw_record(dict(success, result=None)), self.request)
        self.assert_code('invalid_response', ipc.decode_response, raw_record(dict(failure, result=RESULT)), self.request)
        self.assert_code('invalid_response', ipc.decode_response,
                         raw_record(dict(success, error='source_missing')), self.request)

    def test_response_does_not_accept_other_run_or_context(self):
        for request in (ipc.make_request(OTHER_CONTEXT, RUN), ipc.make_request(CONTEXT, 'other-run')):
            with self.subTest(request=request):
                reply = ipc.encode_response(request, result=RESULT)
                self.assert_code('response_mismatch', ipc.decode_response, reply, self.request)
        reply = ipc.decode_response(ipc.encode_response(self.request, result=RESULT), self.request)
        self.assert_code('response_mismatch', ipc.decode_response,
                         raw_record(dict(reply, context_id=CONTEXT.upper())), self.request)

    def test_response_rejects_untyped_or_extraneous_result_fields(self):
        success = ipc.decode_response(ipc.encode_response(self.request, result=RESULT), self.request)
        cases = (
            dict(RESULT, source_page=True), dict(RESULT, source_sha256='bad'),
            dict(RESULT, source_highlight=[2, 3, 1, 31]), dict(RESULT, model_calls=1),
            dict(RESULT, display='15'), dict(RESULT, source_path='unexpected metadata'),
        )
        for result in cases:
            with self.subTest(result=result):
                self.assert_code('invalid_response', ipc.decode_response,
                                 raw_record(dict(success, result=result)), self.request)

    def argv(self, mode, reply, limit=0):
        return [sys.executable, '-I', '-B', '-c', CHILD, mode, reply.hex(),
                ipc.encode_request(self.request).hex(), str(limit)]

    def test_real_child_valid_reply_with_small_stderr_is_accepted(self):
        reply = ipc.encode_response(self.request, result=RESULT)
        result = ipc.exchange(self.argv('warning', reply), self.request, cwd=ROOT)
        self.assertEqual(result['result'], RESULT)
        self.assertNotIn('diagnostic', json.dumps(result))

        reply = ipc.encode_response(self.request, error='source_missing')
        failure = ipc.exchange(self.argv('reply', reply), self.request, cwd=ROOT)
        self.assertEqual(failure['error'], 'source_missing')
        self.assertIsNone(failure['result'])

    def test_real_child_nonzero_exit_discards_an_otherwise_valid_reply(self):
        reply = ipc.encode_response(self.request, result=RESULT)
        self.assert_code('worker_exit', ipc.exchange, self.argv('nonzero', reply), self.request, cwd=ROOT)

    def test_real_child_unterminated_malformed_or_multiple_replies_are_rejected(self):
        good = ipc.encode_response(self.request, result=RESULT)
        malformed = (b'{\n', b'{"value":"\xff"}\n', good[:-1], good + good, good + b'\n',
                     good[:-2] + b',"status":"completed"}\n')
        for reply in malformed:
            with self.subTest(reply=reply[-90:]):
                self.assert_code('invalid_response', ipc.exchange, self.argv('reply', reply),
                                 self.request, cwd=ROOT)

    def test_real_child_response_and_stderr_caps_are_enforced(self):
        good = ipc.encode_response(self.request, result=RESULT)
        for mode, cap, code in (('response-overflow', ipc.MAX_RESPONSE_BYTES, 'response_too_large'),
                                ('stderr-overflow', ipc.MAX_STDERR_BYTES, 'stderr_too_large')):
            with self.subTest(mode=mode):
                self.assert_code(code, ipc.exchange, self.argv(mode, good, cap), self.request, cwd=ROOT)

    def test_real_child_hanging_after_reply_still_hits_the_deadline(self):
        reply = ipc.encode_response(self.request, result=RESULT)
        start = monotonic()
        self.assert_code('worker_timeout', ipc.exchange, self.argv('wait-after-success', reply),
                         self.request, cwd=ROOT, timeout=0.35)
        self.assertLess(monotonic() - start, 5.0)


if __name__ == '__main__':
    unittest.main()
