"""Optional Streamlit tests in the existing separate UI venv; real browser evidence is separate."""
import os,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from streamlit.testing.v1 import AppTest
from financial_assistant.contracts_v2 import read_json

class ServiceAppTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.environ.get('KP3_SERVICE_CONTEXT'),'Explicit trusted local test context required')
        self.app=AppTest.from_file(str(ROOT/'app_kp3/service_b_app.py'),default_timeout=30).run();self.assertFalse(self.app.exception)
    def text(self,q):
        self.app.radio(key='input_mode').set_value('Русский вопрос').run();self.app.text_area(key='question').set_value(q).run();self.app.button(key='execute').click().run();self.assertFalse(self.app.exception);return self.app.session_state['view'].answer
    def test_direct(self):
        a=self.text('Покажи выручку ФосАгро за 2024 год из отчёта за 2024 год. Снимок.');self.assertEqual(a['financial_status'],'answered');self.assertEqual(self.app.metric[0].value,'507689 млн руб.')
    def test_margin(self):
        a=self.text('Какова операционная маржа Сегежи за 2022 год из отчёта за 2022 год? Снимок.');self.assertEqual(a['financial_status'],'answered');self.assertIn('%',self.app.metric[0].value)
    def test_premise(self):
        a=self.text('Почему выручка ФосАгро снизилась за 2023 и 2024 годы из отчёта за 2024 год? Снимок.');self.assertEqual(a['assumption_checks'][0]['status'],'contradicted');self.assertTrue(self.app.warning)
    def test_clarification(self):
        a=self.text('Покажи выручку за 2024 год. Снимок.');self.assertEqual(a['execution_status'],'awaiting_clarification');self.assertIsNone(a['financial_result']);self.assertFalse(self.app.metric)
    def test_historical(self):
        a=self.text('Покажи выручку ФосАгро за 2024 год из отчёта за 2024 год на дату 2026-11-10T01:00:00+03:00.');self.assertEqual(a['reason_code'],'publication_unknown');self.assertFalse(self.app.metric)
    def test_stale_answer_hidden_on_changed_input(self):
        self.test_direct();self.app.text_area(key='question').set_value('Покажи выручку Сегежи за 2022 год.').run();self.assertIsNone(self.app.session_state['view'].answer);self.assertFalse(self.app.metric)
    def test_empty_form_no_hidden_defaults(self):
        self.assertIsNone(self.app.selectbox(key='organization').value);self.assertIsNone(self.app.selectbox(key='operation').value);self.app.button(key='execute').click().run();self.assertEqual(self.app.session_state['view'].answer['execution_status'],'awaiting_clarification');self.assertFalse(self.app.metric)

if __name__=='__main__':unittest.main()
