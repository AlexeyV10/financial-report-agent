"""Three remaining declared UI operation paths; hand expectations on admitted05 cells."""
from pathlib import Path
import json,os,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
os.environ['KP3_DESKTOP_CONTEXT']=str(ROOT/'tmp/service-context.json')
from streamlit.testing.v1 import AppTest
import sys
sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.contracts_v2 import digest


class ReleaseUIOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');os.environ['KP3_DESKTOP_HISTORY']=str(Path(self.temp.name)/'history');self.app=AppTest.from_file(str(ROOT/'app_kp3/desktop_app.py')).run(timeout=40)
    def tearDown(self):
        for key in ['viewer','downloads']:
            try:self.app.session_state[key].close()
            except Exception:pass
        self.temp.cleanup()
    def select(self,label):return next(s for s in self.app.selectbox if s.label==label)
    def form(self,operation):
        self.app.radio[0].set_value('Заполнить поля').run(timeout=40)
        self.select('Компания').set_value('phosagro_group').run(timeout=40)
        self.select('Что нужно сделать').set_value(operation).run(timeout=40)
        if operation!='operating_margin_v1':self.select('Показатель').set_value('revenue').run(timeout=40)
        period=dict(kind='duration',start='2025-01-01',end='2025-03-31',duration_type='quarter')
        self.select('За какой период').set_value(digest(period)).run(timeout=40)
        next(s for s in self.app.multiselect if s.label=='Какие отчёты использовать').set_value(['phosagro-2025-q1']).run(timeout=40)
        self.select('По каким данным анализировать').set_value('snapshot').run(timeout=40)
        self.select('Правило выбора версии').set_value('explicit_versions').run(timeout=40)
        return self
    def answer(self):
        next(b for b in self.app.button if b.label=='Проверить и рассчитать').click().run(timeout=40);self.assertFalse(self.app.exception);a=self.app.session_state['active_record']['payload']['result'];self.assertEqual(a['financial_status'],'answered',a['reason_code']);self.assertEqual(a['model_calls'],0);return a['financial_result']
    def test_direct_from_explicit_form(self):
        r=self.form('direct_fact_v1').answer();self.assertEqual(r['operation_id'],'direct_fact_v1');self.assertEqual(r['display_value'],'159390');self.assertEqual(len(r['inputs']),1)
    def test_scale_from_explicit_form(self):
        self.form('scale_v1');self.select('Единицы результата').set_value(1000000000).run(timeout=40);r=self.answer();self.assertEqual(r['operation_id'],'scale_v1');self.assertEqual(r['display_value'],'159.39');self.assertEqual(r['result_unit'],dict(kind='amount',currency='RUB',scale=1000000000))
    def test_margin_from_explicit_form(self):
        r=self.form('operating_margin_v1').answer();self.assertEqual(r['operation_id'],'operating_margin_v1');self.assertEqual(r['display_value'],'24.35');self.assertEqual([x['role']for x in r['inputs']],['profit','revenue']);self.assertEqual(len({x['version_id']for x in r['inputs']}),1)


if __name__=='__main__':unittest.main()
