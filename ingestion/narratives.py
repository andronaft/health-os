"""Ingest of narrative texts into document_chunks (Phase 3, lean version without embeddings).

Narratives (consultation conclusions, immunogram interpretations, ultrasound descriptions) are
what's missing from structured observations: diagnostic reasoning, recommendations, context.
We store them as chunks with a full-text index; search via the `search` tool (tools.py).

One documents row = one physical file (unique file_sha256); chunks from different
consultations inside a single PDF attach to it. chunk_type + effective_date —
for search filters.

Every text stored here goes through the critical-narrative classifier
(safety.narrative_flags): "BI-RADS 5", "suspicion of malignancy", "5 cm aneurysm" have no
number for the critical-values rule-engine, so without this they would sit in the search index
with no alert at all. A hit is sent through the same alert channel as a critical lab value and
is returned to the caller; the system never interprets the finding further — it sends the user
to a doctor. `ingest_narrative` is the entry point that reports the hits; `upsert_document` and
`add_chunks` scan and alert on their own too, so a script calling them directly can't skip it.
"""
from __future__ import annotations

import hashlib
import os

from sqlalchemy import text

from safety import alerts
from safety.narrative_flags import scan, send_alert

ESCALATION_NOTE = ("CRITICAL narrative finding — show this document to a doctor today. "
                   "The system does not interpret it further.")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _resolve_alerter(alerter):
    """None → the production channel, looked up at call time (tests patch it).

    Unlike lab ingestion (where the MCP tool passes the alerter), narratives are written by
    import scripts with no tool in between; a silent default would mean no alert at all.
    """
    return alerter if alerter is not None else alerts.send_critical_alert


def _flags(texts: list[tuple[str, str | None]]) -> list[dict]:
    """Scans (where, text) pairs; one entry per (where, category)."""
    out = []
    for where, txt in texts:
        for f in scan(txt):
            out.append({"category": f.category, "matched_text": f.matched_text, "where": where})
    return out


def _alert(flags: list[dict], label: str, alerter) -> None:
    """One alert per stored document, naming every category found (not one per chunk)."""
    if flags:
        send_alert((f["category"] for f in flags), source_label=label,
                   alerter=_resolve_alerter(alerter))


def _label(title: str | None, doc_type: str | None, document_date) -> str:
    base = title or doc_type or "document"
    return f"{base} ({document_date})" if document_date else base


def _store_document(conn, user_id: str, file_path: str, *, doc_type: str, title: str,
                    document_date: str | None, extracted_text: str | None) -> str:
    sha = sha256_file(file_path) if os.path.exists(file_path) else hashlib.sha256(
        file_path.encode()).hexdigest()
    row = conn.execute(text("SELECT id FROM documents WHERE file_sha256=:s"),
                       {"s": sha}).first()
    if row:
        did = str(row[0])
        if extracted_text:
            conn.execute(text("UPDATE documents SET extracted_text=:t WHERE id=:id"),
                         {"t": extracted_text, "id": did})
        return did
    return str(conn.execute(
        text("""INSERT INTO documents (user_id, document_date, doc_type, title,
                    file_path, file_sha256, mime_type, extracted_text)
                VALUES (:u, :d, :dt, :ti, :fp, :sha, 'application/pdf', :txt)
                RETURNING id"""),
        {"u": user_id, "d": document_date, "dt": doc_type, "ti": title,
         "fp": file_path, "sha": sha, "txt": extracted_text},
    ).scalar())


def _store_chunks(conn, document_id: str, chunks: list[dict]) -> int:
    conn.execute(text("DELETE FROM document_chunks WHERE document_id=:d"),
                 {"d": document_id})
    for i, ch in enumerate(chunks):
        conn.execute(
            text("""INSERT INTO document_chunks
                        (document_id, chunk_index, content, chunk_type, effective_date)
                    VALUES (:d, :i, :c, :ct, :ed)"""),
            {"d": document_id, "i": i, "c": ch["content"],
             "ct": ch.get("chunk_type"), "ed": ch.get("effective_date")},
        )
    return len(chunks)


def upsert_document(conn, user_id: str, file_path: str, *, doc_type: str,
                    title: str, document_date: str | None = None,
                    extracted_text: str | None = None, alerter=None) -> str:
    """Creates/returns a documents row by file_sha256 (idempotent).

    `extracted_text` is scanned for critical narrative findings; a hit fires
    `alerter(title, message)` (default: safety.alerts.send_critical_alert). Use
    `ingest_narrative` to also get the hits back.
    """
    did = _store_document(conn, user_id, file_path, doc_type=doc_type, title=title,
                          document_date=document_date, extracted_text=extracted_text)
    _alert(_flags([("extracted_text", extracted_text)]),
           _label(title, doc_type, document_date), alerter)
    return did


def add_chunks(conn, document_id: str, chunks: list[dict], *, alerter=None) -> int:
    """Adds chunks to a document (idempotent by (document_id, chunk_index)).

    chunk: {content, chunk_type?, effective_date?}. Before inserting, clears this document's
    old chunks so a re-import doesn't duplicate. Every chunk is scanned for critical narrative
    findings; hits fire one alert for the document (see `upsert_document`).
    """
    n = _store_chunks(conn, document_id, chunks)
    flags = _flags([(f"chunk {i}", ch.get("content")) for i, ch in enumerate(chunks)])
    if flags:
        doc = conn.execute(text("SELECT title, doc_type, document_date FROM documents WHERE id=:d"),
                           {"d": document_id}).first()
        label = _label(*doc) if doc else "document"
        _alert(flags, label, alerter)
    return n


def ingest_narrative(conn, user_id: str, file_path: str, *, doc_type: str, title: str,
                     document_date: str | None = None, extracted_text: str | None = None,
                     chunks: list[dict] | None = None, alerter=None) -> dict:
    """Stores a document and its chunks, and reports critical narrative findings.

    The result carries `narrative_flags` (category, matched text, where) and, when there are
    any, `critical: true` and an escalation `note`, so a client reading the result sees the
    finding instead of a bare "stored". One alert per call, however many chunks hit.
    """
    did = _store_document(conn, user_id, file_path, doc_type=doc_type, title=title,
                          document_date=document_date, extracted_text=extracted_text)
    chunks = chunks or []
    n = _store_chunks(conn, did, chunks) if chunks else 0
    flags = _flags([("extracted_text", extracted_text)]
                   + [(f"chunk {i}", ch.get("content")) for i, ch in enumerate(chunks)])
    _alert(flags, _label(title, doc_type, document_date), alerter)
    out = {"document_id": did, "chunks": n, "narrative_flags": flags, "critical": bool(flags)}
    if flags:
        out["note"] = ESCALATION_NOTE
    return out
