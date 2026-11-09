"""One-document local retrieval. Source text is untrusted; no fact extraction."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from contextlib import closing

from .contracts import available_from, instant, validate_bundle


class RetrievalError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def need(condition, code, message):
    if not condition:
        raise RetrievalError(code, message)


def normalize(text):
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold().replace("ё", "е"), re.UNICODE)
    aliases = {"выручки": "выручка", "выручку": "выручка", "отчёта": "отчет", "отчета": "отчет"}
    return " ".join(aliases.get(w, w) for w in words)


def source_hash(pdf, doc):
    pdf = Path(pdf)
    need(pdf.is_file(), "source_missing", "Local PDF is missing; this is not a financial refusal")
    need(pdf.stat().st_size <= 10_000_000, "source_too_large", "PDF exceeds 10 MB prototype limit")
    fingerprint = hashlib.sha256(pdf.read_bytes()).hexdigest()
    need(fingerprint == doc["sha256"], "source_version_mismatch", "PDF hash differs from selected document")
    return fingerprint


def checked_export(export, bundle):
    doc = bundle["document"]
    need(export["sha256"] == doc["sha256"] and export["pdf_pages"] == doc["pdf_pages"],
         "extraction_version_mismatch", "Extraction belongs to another PDF")
    need(export["mode"] in {"pdfplumber_split_spread_v1", "manual_reference_v1"}, "unsupported_mode", "Unknown extraction mode")
    unique = {}
    for f in export["fragments"]:
        need(type(f["pdf_page"]) is int and 1 <= f["pdf_page"] <= doc["pdf_pages"], "invalid_fragment", "Page out of range")
        need(f["page_region"] in {"left_half_of_spread", "right_half_of_spread"}, "invalid_fragment", "Unknown region")
        need(isinstance(f["text"], str) and bool(f["text"].strip()) and "\x00" not in f["text"], "invalid_fragment", "Empty or corrupt text")
        key = (f["pdf_page"], f["page_region"])
        need(key not in unique or unique[key]["text"] == f["text"], "duplicate_conflict", "Conflicting copies of a page region")
        unique[key] = f
    # Mechanical regression check against prior manual annotations; not an audit
    # of general PDF semantics. A broken target must not silently replace it.
    for ev in bundle["evidence"]:
        need(ev["raw_value"] is not None, "reference_value_missing", "Manual reference lacks a value needed for extraction regression")
        f = unique.get((ev["pdf_page"], ev["page_region"]))
        need(f is not None, "reference_context_missing", "Annotated source region was lost")
        text = f["text"]
        need(normalize(ev["table_title"]) in normalize(text), "table_header_missing", "Table title was lost")
        need(re.search(r"Млн\.?\s+руб", text, re.I) is not None, "unit_header_missing", "Currency/scale header was lost")
        header = re.search(r"Млн\.?\s+руб[^\n]*", text, re.I)
        need(header and re.search(r"\b2024\s+2023\b", header.group()), "column_order_changed", "Expected 2024 then 2023 year headers")
        row = next((line for line in text.splitlines() if line.strip().startswith(ev["row_label"] + " ")), "")
        need(ev["raw_value"] in row, "reference_row_missing", "Previously annotated source number/row not preserved")
    # Check ordered columns as well as membership; swapped numbers are unsafe.
    for loc in {(e["pdf_page"], e["page_region"]) for e in bundle["evidence"]}:
        evs = [e for e in bundle["evidence"] if (e["pdf_page"], e["page_region"]) == loc]
        ordered = sorted(evs, key=lambda e: e["column_label"], reverse=True)
        row = next(line for line in unique[loc]["text"].splitlines() if line.strip().startswith(ordered[0]["row_label"] + " "))
        positions = [row.find(e["raw_value"]) for e in ordered]
        need(positions == sorted(positions), "column_order_changed", "Numbers appear in reversed year columns")
    need(bool(unique), "extraction_empty", "No usable page text")
    return list(unique.values())


def manual_export(bundle):
    """Explicit fallback from prior manual facts, not an automatic PDF result."""
    doc = bundle["document"]
    rows = {}
    for ev in bundle["evidence"]:
        rows.setdefault((ev["pdf_page"], ev["page_region"]), []).append(ev)
    fragments = []
    for (page, region), evs in rows.items():
        ordered = sorted(evs, key=lambda e: e["column_label"], reverse=True)
        text = "\n".join([doc["entity_name"], ordered[0]["table_title"],
                          "Млн руб. Прим. " + " ".join(e["column_label"] for e in ordered),
                          ordered[0]["row_label"] + " " + " ".join(e["raw_value"] for e in ordered)])
        fragments.append({"pdf_page": page, "page_region": region, "bbox_pdf_points_top_origin": None, "text": text})
    return {"sha256": doc["sha256"], "pdf_pages": doc["pdf_pages"], "mode": "manual_reference_v1", "fragments": fragments}


def build_index(db_path, pdf, bundle, export):
    validate_bundle(bundle)
    source_hash(pdf, bundle["document"])
    fragments = checked_export(export, bundle)
    db_path = Path(db_path)
    need(not db_path.exists(), "index_exists", "Use a new index path; existing snapshots are immutable")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("CREATE TABLE metadata (payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE fragments (id INTEGER PRIMARY KEY, page INTEGER, region TEXT, body TEXT, bbox TEXT)")
            connection.execute("CREATE VIRTUAL TABLE search USING fts5(body, tokenize='unicode61')")
            metadata = {"retrieval_schema_version": "0.1", "document": bundle["document"],
                        "extractor": {k: v for k, v in export.items() if k != "fragments"}}
            connection.execute("INSERT INTO metadata VALUES (?)", (json.dumps(metadata, ensure_ascii=False),))
            for i, f in enumerate(fragments, 1):
                connection.execute("INSERT INTO fragments VALUES (?,?,?,?,?)", (i, f["pdf_page"], f["page_region"], f["text"], json.dumps(f.get("bbox_pdf_points_top_origin"))))
                connection.execute("INSERT INTO search(rowid,body) VALUES (?,?)", (i, normalize(f["text"])))
    except sqlite3.Error as exc:
        raise RetrievalError("index_build_failed", str(exc)) from exc
    finally:
        connection.close()
    return {"status": "indexed", "fragments": len(fragments), "mode": export["mode"], "index": str(db_path)}


def search_index(db_path, pdf, bundle, query, entity_id=None, version_id=None, period=None, top_k=5, mode="document_snapshot", as_of=None):
    validate_bundle(bundle)
    need(isinstance(query, str) and 0 < len(query) <= 500 and bool(normalize(query)), "invalid_query", "Use nonempty keywords up to 500 characters")
    need(type(top_k) is int and 1 <= top_k <= 10, "invalid_top_k", "top_k must be between 1 and 10")
    need(mode in {"document_snapshot", "historical_as_of"}, "invalid_mode", "Unknown mode")
    need(period is None or (isinstance(period, str) and re.fullmatch(r"20\d{2}", period)), "invalid_period", "Period is a year keyword, e.g. 2024")
    doc = bundle["document"]
    source_hash(pdf, doc)
    db_path = Path(db_path)
    need(db_path.is_file(), "index_missing", "Build a local index first")
    try:
        with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            meta = json.loads(con.execute("SELECT payload FROM metadata").fetchone()[0])
            need(meta["document"] == doc, "index_version_mismatch", "Index metadata differs from selected document")
            base = {"retrieval_schema_version": "0.1", "status": "found", "reason_code": "ok", "results": [],
                    "warnings": ["retrieved_text_is_not_a_verified_fact", "year_filter_is_annotated_scope_not_accounting_comparability"],
                    "extraction_mode": meta["extractor"]["mode"]}
            if mode == "historical_as_of":
                need(as_of is not None, "invalid_as_of", "Historical search requires a timestamp")
                now = instant(as_of)
                cutoff = available_from(doc)
                if cutoff is None or now < cutoff:
                    base.update(status="missing", reason_code="publication_unknown" if cutoff is None else "not_yet_available")
                    return base
            else:
                need(as_of is None, "invalid_as_of", "Snapshot search must not claim a historical cutoff")
            if (entity_id is not None and entity_id != doc["entity_id"]) or (version_id is not None and version_id != doc["version_id"]):
                base.update(status="not_found", reason_code="document_filter_mismatch")
                return base
            known_years = {f["period"]["end"][:4] for f in bundle["facts"]}
            if period is not None and period not in known_years:
                base.update(status="not_found", reason_code="period_outside_annotated_scope")
                return base
            tokens = normalize(query).split()
            if period is not None:
                tokens.append(period)
            match = " AND ".join('"' + t + '"' for t in dict.fromkeys(tokens))
            found = con.execute("SELECT f.id,f.page,f.region,f.body,f.bbox FROM search JOIN fragments f ON f.id=search.rowid WHERE search MATCH ? ORDER BY bm25(search),f.page,f.region", (match,)).fetchall()
            # Generic table-row preference, not a gold page/number lookup.
            # BM25 alone may prefer a definition mentioning the term repeatedly.
            first_word = next((t for t in tokens if not t.isdigit()), "")
            def table_row(row):
                return any(normalize(line).startswith(first_word + " ") and re.search(r"\d", line)
                           for line in row[3].splitlines()) if first_word else False
            found.sort(key=lambda row: not table_row(row))
            found = found[:top_k]
            base["ranking"] = "table_row_preference_then_fts5_bm25"
            for identifier, page, region, body, bbox in found:
                prior = [e for e in bundle["evidence"] if e["pdf_page"] == page and e["page_region"] == region]
                base["results"].append({"fragment_id": f"{doc['sha256']}:{page}:{region}",
                    "document_id": doc["document_id"], "entity_id": doc["entity_id"], "version_id": doc["version_id"],
                    "document_sha256": doc["sha256"], "pdf_page": page, "page_region": region,
                    "printed_page": prior[0]["printed_page"] if prior else None,
                    "bbox_pdf_points_top_origin": json.loads(bbox), "text": body,
                    "source_url": doc["document_url"] + f"#page={page}", "verification_status": "candidate",
                    "existing_manual_evidence_ids": [e["evidence_id"] for e in prior]})
            if not found:
                base.update(status="not_found", reason_code="no_keyword_match")
            return base
    except (sqlite3.Error, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RetrievalError("index_invalid", str(exc)) from exc
