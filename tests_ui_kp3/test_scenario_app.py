"""Separate existing UI-venv AppTest; not main core regression or real CUA."""
from pathlib import Path
import os,unittest
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]


class ScenarioAppTests(unittest.TestCase):
    def app(self):return AppTest.from_file(str(ROOT/'app_kp3/scenario_app.py'),default_timeout=30).run()
    def own(self):a=self.app();a.selectbox[0].select('Собственные искусственные данные').run();return a
    def test_initial_requires_explicit_mode(self):
        a=self.app();self.assertTrue(a.button[0].disabled);self.assertIsNone(a.session_state['scenario_result']);self.assertFalse(a.exception)
    def test_own_vertical_path(self):
        a=self.own();a.button[0].click().run();self.assertFalse(a.exception);out=a.session_state['scenario_result'];self.assertEqual(out['status'],'completed');self.assertEqual(out['scenario']['final_equity'],'10098.00')
    def test_change_clears_result_and_false_signal(self):
        a=self.own();a.button[0].click().run();a.text_input[2].set_value('20').run();self.assertIsNone(a.session_state['scenario_result']);a.button[0].click().run();self.assertFalse(a.session_state['scenario_result']['signal'])
    def test_invalid_capital_is_error_without_ledger(self):
        a=self.own();a.text_input[0].set_value('-1').run();a.button[0].click().run();out=a.session_state['scenario_result'];self.assertEqual(out['reason_code'],'invalid_capital');self.assertIsNone(out['scenario']);self.assertFalse(a.exception)
    def test_change_to_real_does_not_reuse_synthetic_result(self):
        a=self.own();a.button[0].click().run();a.selectbox[0].select('Проверка реального источника').run();self.assertIsNone(a.session_state['scenario_result']);self.assertTrue(a.button[0].disabled)
    @unittest.skipUnless(os.environ.get('KP3_SCENARIO_REAL_CONTEXT'),'Explicit local real setup required')
    def test_real_financial_answer_remains_scenario_blocked(self):
        a=self.app();a.selectbox[0].select('Проверка реального источника').run();a.selectbox[1].select('phosagro-2024').run();a.text_input[0].set_value('2026-11-10T12:00:00+03:00').run();a.button[0].click().run();self.assertFalse(a.exception);out=a.session_state['scenario_result'];self.assertEqual(out['reason_code'],'publication_unknown');self.assertEqual(out['financial']['financial_result']['display_value'],'15.30');self.assertIsNone(out['scenario'])


if __name__=='__main__':unittest.main()
