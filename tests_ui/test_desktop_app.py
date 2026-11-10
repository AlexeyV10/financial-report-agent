"""Actual Streamlit/service integration on existing admitted sources, no model calls."""
from pathlib import Path
import json,os,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
os.environ['KP3_DESKTOP_CONTEXT']=str(ROOT/'tmp/service-context.json')
from streamlit.testing.v1 import AppTest


class DesktopAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');os.environ['KP3_DESKTOP_HISTORY']=str(Path(self.tmp.name)/'history');self.app=AppTest.from_file(str(ROOT/'app_kp3/desktop_app.py')).run(timeout=40)
    def tearDown(self):
        for key in ['viewer','downloads']:
            try:self.app.session_state[key].close()
            except Exception:pass
        self.tmp.cleanup()
    def button(self,label):return next(b for b in self.app.button if b.label==label)
    def select(self,label):return next(b for b in self.app.selectbox if b.label==label)
    def sample(self):self.button('Заполнить пример').click().run(timeout=40);return self
    def calculate(self):self.button('Проверить и рассчитать').click().run(timeout=40);return self
    def record(self):return self.app.session_state['active_record']
    def test_empty_has_no_company_and_no_answer(self):
        self.assertIsNone(self.select('Компания').value);self.assertTrue(self.button('Проверить и рассчитать').disabled);self.assertIsNone(self.record());self.assertFalse(self.app.exception)
    def test_explicit_example_uses_real_service(self):
        self.sample().calculate();r=self.record()['payload']['result'];self.assertEqual(r['financial_status'],'answered',self.app.error);self.assertEqual(r['financial_result']['display_value'],'33.64');self.assertEqual(r['model_calls'],0);self.assertEqual(len(r['financial_result']['inputs']),2);self.assertFalse(self.app.exception)
    def test_repeated_click_returns_same_snapshot(self):
        self.sample().calculate();a=self.record();self.calculate();self.assertEqual(self.record(),a);self.assertEqual(len(list((Path(self.tmp.name)/'history').glob('*.json'))),1)
    def test_company_change_hides_answer(self):
        self.sample().calculate();self.select('Компания').set_value('segezha_group').run(timeout=40);self.assertIsNone(self.record());self.assertFalse(self.app.session_state['evidence_open']);self.assertFalse(self.app.exception)
    def test_method_change_hides_answer_without_calling_model(self):
        self.sample().calculate();self.select('Способ анализа').set_value('A').run(timeout=40);self.assertIsNone(self.record());self.assertFalse(self.app.exception)
    def test_source_button_only_displays_evidence(self):
        self.sample().calculate();rid=self.record()['record_id'];self.button('Посмотреть источник').click().run(timeout=40);self.assertTrue(self.app.session_state['evidence_open']);self.assertEqual(self.record()['record_id'],rid);self.assertFalse(self.app.exception)
    def test_another_question_resets_periods_and_result(self):
        self.sample().calculate();self.button('Другой вопрос').click().run(timeout=40);self.assertIsNone(self.record());self.assertIsNone(self.select('Компания').value);self.assertFalse(self.app.exception)
    def test_history_loads_without_new_run(self):
        self.sample().calculate();key=self.record()['record_id'];self.button('История').click().run(timeout=40);sel=self.select('Какой ответ открыть');sel.set_value(key).run(timeout=40);self.assertEqual(len(list((Path(self.tmp.name)/'history').glob('*.json'))),1);self.assertFalse(self.app.exception)
    def test_unknown_question_requires_company(self):
        next(t for t in self.app.text_area if t.label=='Ваш вопрос').set_value('Какая выручка за полный 2024 год?').run(timeout=40);self.calculate();r=self.record()['payload']['result'];self.assertEqual(r['execution_status'],'awaiting_clarification');self.assertIsNone(r['financial_result']);self.assertIn('Компания',[s.label for s in self.app.selectbox]);self.assertFalse(self.app.exception)
    def test_documents_and_help_pages(self):
        self.button('Документы').click().run(timeout=40);self.button('Проверить файлы и поиск').click().run(timeout=40);self.assertEqual(len(self.app.session_state['readiness']['documents']),8);self.button('Как это работает').click().run(timeout=40);self.assertFalse(self.app.exception)
    def test_own_scenario_service_and_history(self):
        self.button('Учебный сценарий').click().run(timeout=40);self.select('На каких данных проверить сценарий').set_value('Собственный учебный пример').run(timeout=40);self.button('Рассчитать учебный сценарий').click().run(timeout=40);r=self.record()['payload']['result'];self.assertEqual(r['status'],'completed');self.assertEqual(r['scenario']['final_equity'],'10098.00');self.assertEqual(r['model_calls'],0);self.assertFalse(self.app.exception)
    def test_false_premise_is_visible_and_question_unchanged(self):
        self.sample();q='Почему выручка ФосАгро снизилась за I квартал 2024 и 2025? На сколько процентов?'
        next(t for t in self.app.text_area if t.label=='Ваш вопрос').set_value(q).run(timeout=40);self.calculate();r=self.record()['payload']['result'];self.assertEqual(r['original_question'],q);self.assertEqual(r['assumption_checks'][0]['status'],'contradicted');self.assertTrue(r['unfulfilled_requests']);self.assertTrue(any('Предпосылка не подтвердилась' in w.value for w in self.app.warning));self.assertFalse(self.app.exception)
    def test_historical_has_no_number_and_no_confirmed_assumption(self):
        self.sample();self.select('По каким данным анализировать').set_value('historical').run(timeout=40)
        from datetime import date,time
        self.app.date_input[0].set_value(date(2026,11,10));self.app.time_input[0].set_value(time(12,0));self.app.run(timeout=40);self.calculate();r=self.record()['payload']['result'];self.assertEqual(r['reason_code'],'publication_unknown');self.assertIsNone(r['financial_result']);self.assertFalse(self.app.exception)
    def test_form_absolute_does_not_become_relative(self):
        self.sample();self.app.radio[0].set_value('Заполнить поля').run(timeout=40);self.select('Что нужно сделать').set_value('absolute_change_v1').run(timeout=40);self.calculate();r=self.record()['payload']['result'];self.assertEqual(r['financial_result']['operation_id'],'absolute_change_v1');self.assertEqual(r['financial_result']['display_value'],'40118');self.assertFalse(self.app.exception)
    def test_scenario_false_signal_has_no_trade(self):
        self.button('Учебный сценарий').click().run(timeout=40);self.select('На каких данных проверить сценарий').set_value('Собственный учебный пример').run(timeout=40)
        next(x for x in self.app.text_input if x.label=='Рост выше порога, %').set_value('20').run(timeout=40);self.button('Рассчитать учебный сценарий').click().run(timeout=40);r=self.record()['payload']['result'];self.assertFalse(r['signal']);self.assertEqual(r['scenario']['final_equity'],'10000.00');self.assertFalse(self.app.exception)


if __name__=='__main__':unittest.main()
