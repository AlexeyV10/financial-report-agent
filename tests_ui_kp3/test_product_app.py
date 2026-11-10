"""Separate native UI-venv tests; actual browser checks are recorded separately."""
from pathlib import Path
import json,os,sys,tempfile,unittest
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import digest

class ProductAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.tmp.cleanup);os.environ['KP3_PRODUCT_HISTORY']=self.tmp.name
    def app(self):return AppTest.from_file(str(ROOT/'app_kp3/product_app.py'),default_timeout=60).run()
    def page(self,name,a=None):
        a=a or self.app();a.sidebar.radio[0].set_value(name).run();return a
    def select(self,a,label,value):next(w for w in a.selectbox if w.label==label).set_value(value).run()
    def press(self,a,label):next(w for w in a.button if w.label==label).click().run()
    def form(self,op='direct_fact_v1'):
        a=self.page('Анализ');self.select(a,'Группа','phosagro_group');self.select(a,'Действие',op)
        if op!='operating_margin_v1':self.select(a,'Показатель','revenue')
        periods=[dict(kind='duration',duration_type='full_year',start=str(y)+'-01-01',end=str(y)+'-12-31')for y in ([2023,2024]if op in {'relative_change_v1','absolute_change_v1'}else [2024])]
        next(w for w in a.multiselect if w.label.startswith('Полные периоды')).set_value([digest(p)for p in periods]).run()
        next(w for w in a.multiselect if w.label=='Точные версии отчётов').set_value(['phosagro-2024']).run();self.select(a,'Политика версии','explicit_versions');self.select(a,'Режим','snapshot')
        if op=='scale_v1':self.select(a,'Масштаб результата',1000000000)
        return a
    def test_initial_overview(self):
        a=self.app();self.assertFalse(a.exception);self.assertTrue(any('48'in x.value for x in a.info))
    def test_no_hidden_company_or_period(self):
        a=self.page('Анализ');self.assertIsNone(next(w for w in a.selectbox if w.label=='Группа').value);self.assertIsNone(a.session_state['active_record'])
    def test_five_form_operations(self):
        for op in ['direct_fact_v1','absolute_change_v1','relative_change_v1','scale_v1','operating_margin_v1']:
            with self.subTest(op=op):
                a=self.form(op);self.press(a,'Получить ответ');self.assertFalse(a.exception);r=a.session_state['active_record']['payload']['result'];self.assertEqual(r['financial_status'],'answered',r['reason_code']);self.assertEqual(r['financial_result']['operation_id'],op)
    def test_double_click_dedup_and_change_clears(self):
        a=self.form();self.press(a,'Получить ответ');rid=a.session_state['active_record']['record_id'];self.press(a,'Получить ответ');self.assertEqual(a.session_state['active_record']['record_id'],rid);self.select(a,'Действие','relative_change_v1');self.assertIsNone(a.session_state['active_record'])
    def test_refresh_reopens_same_id(self):
        a=self.form();self.press(a,'Получить ответ');rid=a.session_state['active_record']['record_id'];b=self.form();self.press(b,'Получить ответ');self.assertEqual(b.session_state['active_record']['record_id'],rid)
    def test_text_ambiguity(self):
        a=self.page('Анализ');next(w for w in a.radio if w.label=='Ввод').set_value('Русский вопрос').run();a.text_area[0].set_value('Какая выручка за 2024 год?').run();self.press(a,'Получить ответ');self.assertEqual(a.session_state['active_record']['payload']['result']['execution_status'],'awaiting_clarification');self.assertFalse(a.exception)
    def test_own_scenario_and_threshold_reset(self):
        a=self.page('Условный сценарий');self.select(a,'Источник сценария','Собственные искусственные данные');self.press(a,'Рассчитать сценарий');self.assertEqual(a.session_state['active_record']['payload']['result']['scenario']['final_equity'],'10098.00');next(w for w in a.text_input if w.label=='Порог роста, %').set_value('20').run();self.assertIsNone(a.session_state['active_record']);self.press(a,'Рассчитать сценарий');self.assertFalse(a.session_state['active_record']['payload']['result']['signal']);self.assertFalse(a.exception)
    def test_history_snapshot_open(self):
        a=self.form();self.press(a,'Получить ответ');rid=a.session_state['active_record']['record_id'];self.page('История и экспорт',a);self.select(a,'Сохранённый запуск',rid);self.assertFalse(a.exception);self.assertTrue(any('Сохранённый снимок'in x.value for x in a.warning))
    def test_sources_preflight(self):
        a=self.page('Источники');self.assertFalse(a.exception);self.assertEqual(len(a.dataframe),1)
    def test_explicit_new_attempt_has_new_id(self):
        a=self.form();self.press(a,'Получить ответ');rid=a.session_state['active_record']['record_id'];self.press(a,'Новый запуск');self.assertIsNone(a.session_state['active_record']);self.press(a,'Получить ответ');self.assertNotEqual(a.session_state['active_record']['record_id'],rid)
    def test_false_premise_is_visible(self):
        a=self.page('Анализ');next(w for w in a.radio if w.label=='Ввод').set_value('Русский вопрос').run();a.text_area[0].set_value('Почему выручка группы ФосАгро по МСФО снизилась за 2023 и 2024 годы из отчёта за 2024 год? Снимок.').run();self.press(a,'Получить ответ');self.assertFalse(a.exception);self.assertTrue(any('Предпосылка опровергнута'in x.value for x in a.warning))
    def test_clarification_keeps_original_and_history(self):
        a=self.page('Анализ');next(w for w in a.radio if w.label=='Ввод').set_value('Русский вопрос').run();question='Какая выручка по МСФО за 2024 год из отчёта за 2024 год? Снимок.';a.text_area[0].set_value(question).run();self.press(a,'Получить ответ');self.select(a,'Уточнение: organization',0);self.press(a,'Применить уточнения');r=a.session_state['active_record']['payload']['result'];self.assertEqual(r['financial_status'],'answered');self.assertEqual(r['original_question'],question);self.assertTrue(r['normalized_input']['history']);self.assertFalse(a.exception)
    def test_historical_is_financial_block_not_number(self):
        a=self.form();self.select(a,'Режим','historical');next(w for w in a.text_input if w.label.startswith('На дату:')).set_value('2026-11-10T12:00:00+03:00').run();self.press(a,'Получить ответ');r=a.session_state['active_record']['payload']['result'];self.assertEqual(r['reason_code'],'publication_unknown');self.assertIsNone(r['financial_result']);self.assertFalse(a.exception)
    def test_real_readiness_from_history_stays_blocked(self):
        a=self.form();self.press(a,'Получить ответ');self.page('Условный сценарий',a);self.select(a,'Источник сценария','Проверка реального источника');self.select(a,'Проверенный финансовый запуск',0);next(w for w in a.text_input if w.label.startswith('Момент проверки')).set_value('2026-11-10T12:00:00+03:00').run();self.press(a,'Проверить готовность');r=a.session_state['active_record']['payload']['result'];self.assertEqual(r['status'],'blocked');self.assertEqual(r['reason_code'],'publication_unknown');self.assertIsNone(r['scenario']);self.assertFalse(a.exception)

if __name__=='__main__':unittest.main()
