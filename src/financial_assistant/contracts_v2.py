"""Strict v0.2 data contracts. Validation is consistency, not source verification."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re
from functools import wraps
from urllib.parse import urlsplit

VERSION = "0.2"
SCALES = {1, 1000, 1000000, 1000000000}
STANDARDS = {"IFRS", "RAS"}
CHECKED = {"assistant_checked", "human_reviewed"}


class ContractError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ClarificationRequired(ContractError):
    def __init__(self, code, fields):
        self.fields = tuple(fields)
        super().__init__(code)


def boundary(fn):
    @wraps(fn)
    def checked(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ContractError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            raise ContractError("malformed_record") from None
    return checked


def need(condition, code):
    if not condition:
        raise ContractError(code)


def shape(value, fields):
    need(type(value) is dict and set(value) == set(fields.split()), "fields_mismatch")


def text(value):
    need(isinstance(value, str) and 0 < len(value.strip()) <= 4000, "invalid_text")


def identifier(value):
    need(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,199}", value), "invalid_id")


def sha(value):
    need(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value), "invalid_sha256")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def day(value):
    need(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "invalid_date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ContractError("invalid_date") from None


def instant(value):
    need(isinstance(value, str) and "T" in value, "invalid_timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError("invalid_timestamp") from None
    need(stamp.utcoffset() is not None, "timezone_required")
    return stamp


def period(value):
    need(type(value) is dict, "invalid_period")
    if value.get("kind") == "instant":
        shape(value, "kind date")
        day(value["date"])
        return
    shape(value, "kind duration_type start end")
    need(value["kind"] == "duration" and value["duration_type"] in
         {"full_year", "year_to_date", "quarter", "custom"}, "invalid_period_kind")
    start, end = day(value["start"]), day(value["end"])
    need(start <= end, "reversed_period")
    if value["duration_type"] == "full_year":
        need(start.year == end.year and (start.month, start.day, end.month, end.day) == (1, 1, 12, 31), "invalid_full_year")
    elif value["duration_type"] == "year_to_date":
        need(start.year == end.year and (start.month, start.day) == (1, 1) and end.month < 12, "invalid_year_to_date")
    elif value["duration_type"] == "quarter":
        from calendar import monthrange
        need(start.year == end.year and start.month in {1, 4, 7, 10} and start.day == 1
             and end.month == start.month + 2 and end.day == monthrange(end.year, end.month)[1], "invalid_quarter")


def period_end(value):
    return day(value["date"] if value["kind"] == "instant" else value["end"])


def number(value):
    need(isinstance(value, str) and len(value) <= 60 and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value), "invalid_decimal")
    return Decimal(value)


def unit(value):
    shape(value, "currency scale")
    need(value["currency"] in {"RUB", "USD"} and type(value["scale"]) is int and value["scale"] in SCALES, "invalid_unit")


def https(value):
    need(isinstance(value, str) and len(value) <= 2000 and not any(c.isspace() for c in value), "invalid_url")
    try:
        parsed = urlsplit(value)
        need(parsed.scheme == "https" and parsed.hostname and parsed.username is None
             and parsed.password is None, "invalid_url")
    except ValueError:
        raise ContractError("invalid_url") from None


def provenance(value):
    shape(value, "status method human_reviewer")
    need(value["status"] in CHECKED | {"candidate", "structure_checked"}, "invalid_provenance")
    text(value["method"])
    if value["status"] == "human_reviewed":
        text(value["human_reviewer"])
    else:
        need(value["human_reviewer"] is None, "unestablished_human_review")


def read_json(path):
    """No executable object hooks; duplicate keys/NaN/large files are rejected."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    def invalid(_):
        raise ContractError("invalid_json_number")
    need(path.stat().st_size <= 2_000_000, "input_too_large")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique,
                          parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError):
        raise ContractError("invalid_json") from None


@boundary
def validate_outcome(value):
    shape(value, "schema_version run_id task_id execution_status financial_status reason_code clarification_fields financial_result")
    need(value["schema_version"] == VERSION, "unsupported_schema_version")
    for key in ("run_id", "task_id"):
        identifier(value[key])
    identifier(value["reason_code"])
    fields = value["clarification_fields"]
    need(type(fields) is list and len(fields) == len(set(fields)) and all(isinstance(x, str) and x for x in fields), "invalid_clarification_fields")
    execution, financial, reason = value["execution_status"], value["financial_status"], value["reason_code"]
    technical = {"source_missing", "registry_invalid", "model_unavailable", "input_invalid", "protocol_error", "save_failed"}
    if execution == "completed":
        need(financial in {"answered", "missing", "conflict", "unsupported"} and not fields, "invalid_status_combination")
        need(reason not in technical | {"call_limit", "timeout"}, "technical_reason_is_not_financial")
        if financial == "answered":
            need(reason == "ok" and type(value["financial_result"]) is dict and bool(value["financial_result"]), "answer_required")
        else:
            need(reason != "ok" and value["financial_result"] is None, "refusal_has_no_calculation")
            reasons = {
                "missing": {"publication_unknown", "not_yet_available", "document_unchecked", "value_missing",
                            "unverified_candidate", "verified_evidence_not_retrieved", "original_version_missing",
                            "prepared_original_version_missing", "retrieval_context_missing"},
                "conflict": {"duplicate_candidates", "entity_or_standard_mismatch", "incompatible_periods",
                             "incompatible_units", "input_fact_context_mismatch", "input_fact_selection_mismatch",
                             "retrieval_metadata_conflict", "retrieval_duplicate_conflict"},
                "unsupported": {"unsupported_operation", "nonpositive_base"},
            }
            need(reason in reasons[financial], "invalid_financial_reason")
    else:
        need(financial is None and value["financial_result"] is None, "technical_status_has_no_financial_result")
        if execution == "awaiting_clarification":
            need(bool(fields) and reason in {"missing_fields", "ambiguous_alias", "period_needs_clarification", "version_needs_clarification"}, "invalid_clarification")
        elif execution == "error":
            need(not fields and reason in technical, "invalid_technical_reason")
        else:
            need(execution == "limit_exceeded" and not fields and reason in {"call_limit", "timeout"}, "invalid_limit_status")
