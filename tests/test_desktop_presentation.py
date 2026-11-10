"""UI formatting and explicit-selection semantics, not new arithmetic or source truth."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from financial_assistant.desktop_presentation import number,unit_label,period_label,source_and_answers,option_label,example_fields,METHODS
from financial_assistant.contracts_v2 import ContractError
from financial_assistant.russian_input import parse_text
from financial_assistant.input_contracts import clarification
from financial_assistant.input_binding import resolve_input


class DesktopPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((ROOT/'data/catalogs/kp3_corpus_v1/runtime_catalog.json').read_text(encoding='utf8'));cls.dictionary=json.loads((ROOT/'data/dictionaries/kp3_finance_v1/definitions.json').read_text(encoding='utf8'))
    def test_decimal_precision_is_unchanged(self):self.assertEqual(number('12345678901234567890.00100'),'12\u00a0345\u00a0678\u00a0901\u00a0234\u00a0567\u00a0890,00100')
    def test_signed_value(self):self.assertEqual(number('-1000.20'),'-1\u00a0000,20')
    def test_zero_is_not_negative(self):self.assertEqual(number('0.00'),'0,00')
    def test_non_decimal_not_guessed(self):self.assertEqual(number('1/3'),'1/3')
    def test_monetary_and_percentage_units_separate(self):self.assertEqual(unit_label(dict(kind='percent')),'%');self.assertEqual(unit_label(dict(kind='percentage_point')),'п. п.');self.assertEqual(unit_label(dict(currency='RUB',scale=1000000)),'млн ₽')
    def test_period_contains_full_window(self):
        text=period_label(dict(kind='duration',duration_type='quarter',start='2025-01-01',end='2025-03-31'));self.assertIn('I квартал 2025',text);self.assertIn('01.01.2025–31.03.2025',text)
    def test_full_year_and_ytd_are_distinct(self):
        p=dict(kind='duration',duration_type='full_year',start='2024-01-01',end='2024-12-31');q=dict(kind='duration',duration_type='year_to_date',start='2024-01-01',end='2024-06-30');self.assertNotEqual(period_label(p),period_label(q))
    def test_empty_choices_no_hidden_default(self):
        source,answers=source_and_answers('question','Вопрос',dict(organization=None,mode=None));self.assertEqual(answers,[]);self.assertEqual(source['question'],'Вопрос')
    def test_text_selection_is_explicit_history_patch(self):
        source,answers=source_and_answers('question','Мой исходный вопрос',dict(organization='phosagro_group',mode='snapshot'));self.assertEqual(source['kind'],'text');self.assertEqual(source['question'],'Мой исходный вопрос');self.assertEqual(answers,[dict(organization='phosagro_group',mode='snapshot')])
    def test_form_keeps_missing_fields(self):
        source,answers=source_and_answers('form','',dict(organization=None,operation_id=None));self.assertIsNone(source['form']['fields']['organization']);self.assertIsNone(source['form']['fields']['operation_id']);self.assertEqual(answers,[])
    def test_mutation_does_not_change_source(self):
        fields=dict(organization='phosagro_group',metric_ids=['revenue']);source,_=source_and_answers('form','Запрос',fields);fields['metric_ids'][0]='wrong';self.assertEqual(source['form']['fields']['metric_ids'],['revenue'])
    def test_values_and_formula_cannot_be_form_context(self):
        for key in ['value','formula','expected','pdf_path']:
            with self.assertRaises(ContractError):source_and_answers('question','Запрос',{key:'999'})
    def test_explicit_company_conflict_is_not_silently_rewritten(self):
        t=parse_text('Выручка ФосАгро за полный 2024 год',self.catalog,'ui-conflict');b=resolve_input(t,self.catalog,self.dictionary)
        with self.assertRaises(ContractError):clarification(b['normalized_input'],dict(organization='segezha_group'))
    def test_historical_intent_is_not_replaced_with_snapshot(self):
        t=parse_text('Выручка ФосАгро за полный 2024 год на дату 2026-11-10T12:00:00+03:00',self.catalog,'ui-date');b=resolve_input(t,self.catalog,self.dictionary)
        with self.assertRaises(ContractError):clarification(b['normalized_input'],dict(mode='snapshot'))
    def test_example_contains_context_not_values(self):
        f=example_fields(self.catalog);self.assertEqual(f['periods'][0]['end'],'2024-03-31');self.assertEqual(f['periods'][1]['end'],'2025-03-31');self.assertNotIn('value',str(f));self.assertNotIn('expected',str(f));self.assertNotIn('fact_id',str(f))
    def test_human_operation_choices_keep_registered_ids(self):
        self.assertEqual(option_label('operation_id',dict(value='absolute_change_v1',label='absolute_delta'),self.catalog,self.dictionary),'Сравнить — разница в рублях')
    def test_human_company_choice(self):self.assertEqual(option_label('organization',dict(value='phosagro_group',label='phosagro_group'),self.catalog,self.dictionary),next(o['name']for o in self.catalog['organizations']if o['organization_id']=='phosagro_group'))
    def test_three_methods_explicit_no_mock(self):self.assertEqual(set(METHODS),{'B','A','C'})


if __name__=='__main__':unittest.main()
