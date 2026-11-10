"""Hand-specified expectations, committed separately from observed outcomes."""
from collections import Counter


def build_plan():
    rows=[]
    def add(family,kind,names,expected,registry=()):
        for name in names.split():
            rows.append(dict(probe_id=kind+'-'+name,family=family,kind=kind,variant=name,expected=expected,registry_ids=list(registry),known_to_developer=True))
    add('positive','positive','direct delta relative scale margin negative_profit signed_cfo','answered',())
    add('artifacts','artifact','source_missing source_changed index_missing index_changed manifest_missing manifest_changed config_changed catalog_changed dictionary_changed admission_changed guarded_file guarded_setup code_signature','error',('changed_artifact',))
    add('search','search','empty partial','missing',('changed_artifact',))
    add('evidence','cell','unknown_evidence duplicate_evidence wrong_cell wrong_page wrong_sha lost_unit_header wrong_value candidate structure_checked','error',('unknown_id','duplicate_id','other_cell','wrong_sha_page','lost_header','automatic_candidate'))
    add('references','reference','unknown_fact duplicate_fact duplicate_role reversed_periods wrong_org legal_entity ras wrong_definition wrong_version wrong_currency wrong_scale wrong_period extra_value extra_formula extra_path','no_answer',('unknown_id','duplicate_id','swapped_roles','other_cell'))
    add('input','input','unknown_org missing_org unknown_document duplicate_document ytd quarter missing_period ebitda net_income bank ras legal_entity fx percentage_points form_extra huge_question instruction code url path','no_answer',('untrusted_instruction',))
    add('financial','finance','zero_base negative_base zero_revenue negative_revenue','unsupported',())
    add('publication','publication','unknown before_publication missing_as_of no_zone invalid_precision','no_answer',())
    add('versions','versions','cross_original original_only','no_answer',())
    add('premises','premise','increase decrease failure clarification preserve_history','invariant',('lost_claim',))
    add('A_controller_fixture','a_fixture','valid unknown duplicate_id duplicate_role wrong_roles wrong_operation value malformed large bad_reply timeout','fixture',('unknown_id','duplicate_id','swapped_roles','extra_claim','unknown_usage'))
    add('C_controller_fixture','c_fixture','valid loop timeout bad_reply wrong_finish never_finish forbidden_tool extra_value partial','fixture',('untrusted_instruction','extra_claim','unknown_usage'))
    add('history','history','repeat refresh archive export context_change units_change new_nonce duplicate_run pending_claim interrupted atomic_existing unsafe_id duplicate_keys nan oversize checksum method_swap','invariant',('changed_artifact','untrusted_instruction','unknown_usage'))
    add('scenario','scenario','default false_signal strict_nextopen costs lot price_gap exit_fee before_publication no_zone wrong_run value_tamper real_mixing negative_cash nan_threshold extra_prices source_missing source_changed','scenario',('own_price_gap','extra_claim'))
    add('real_source','real','all_publications automatic export_missing export_changed source_copy_missing source_copy_changed conflict_versions','invariant',('automatic_candidate','changed_artifact'))
    return dict(schema_version='kp3-probe-plan-0.1',stage='KP3-15',scope='developer_known_runtime_fault_campaign_not_comparison16',trusted_setup='Isolated own07 hash fixtures (NOT issuer PDF); own12 source/ledger; immutable real catalog and private resource copies. SQLite payload faults are injected by trusted evaluator and rehashed, never by source/question/model.',model_policy=dict(start_server=False,real_chat_budget=0,controller_fixtures='explicit_mock_not_actual_model',actual_model_quality='not_measured'),registry_basis='evaluation/protocols/kp3_eval_v1/protocol.json:fault_registry',rows=rows,denominators=dict(Counter(x['family']for x in rows)),final_comparison_attempts=0,reserved_unseen_real=0)
