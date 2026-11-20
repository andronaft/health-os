"""The review queue page's data (#58): every value awaiting review, by the staging it came in.

Nothing here is a fact yet. The rows are the ones get_health_summary counts as awaiting review
(review_status 'pending', not deleted), with the same "can't wait" flags: critical, or a critical
check that is impossible (an unconverted unit, a limit, an unmapped name that reads as a
critical-watch marker). Read-only: approving and mapping stay with the MCP client, on the user's
explicit instruction. Plain data, no model output.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import text

from core import queries as q
from core.health_summary import CHECK_IMPOSSIBLE_UNMAPPED_SQL, UNVERIFIABLE_SQL
from safety.critical_values import LANGUAGES


def _number(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _row(r, names: dict) -> dict:
    code = r["code"]
    return {"code": code, "name": names.get(code) or r["raw_name"] or code,
            "raw_name": r["raw_name"], "value": _number(r["value_numeric"]),
            "comparator": r["comparator"], "text": r["value_text"], "unit": r["unit"],
            "ref_min": _number(r["ref_min"]), "ref_max": _number(r["ref_max"]),
            "at": r["effective_at"], "critical": r["status"] == "critical",
            "unverifiable": bool(r["unverifiable"]), "unmapped": bool(r["unmapped"]),
            "limit": bool(r["limit_only"]), "notes": r["notes"]}


def _alarming(row: dict) -> bool:
    return row["critical"] or row["unverifiable"]


def review_queue(conn, lang: str = "en") -> dict:
    lang = lang if lang in LANGUAGES else "en"
    uid = q.user_id(conn)
    if uid is None:
        return {"total": 0, "alarming": 0, "unmapped": 0, "sources": []}
    names = q.marker_names(conn, lang)
    rows = conn.execute(text(
        f"""SELECT o.source_id, s.channel, s.created_at AS staged_at,
                   p.panel_date, p.panel_type, f.name AS facility, d.title AS document,
                   ot.code, o.raw_name, o.value_numeric, o.comparator, o.value_text, o.unit,
                   o.ref_min, o.ref_max, o.effective_at, o.status, o.notes,
                   (o.type_id IS NULL) AS unmapped,
                   ({UNVERIFIABLE_SQL} OR {CHECK_IMPOSSIBLE_UNMAPPED_SQL}) AS unverifiable,
                   (o.comparator IS NOT NULL) AS limit_only
            FROM observations o
            LEFT JOIN observation_types ot ON ot.id = o.type_id
            LEFT JOIN ingestion_sources s ON s.id = o.source_id
            LEFT JOIN panels p ON p.id = o.panel_id
            LEFT JOIN facilities f ON f.id = p.facility_id
            LEFT JOIN documents d ON d.id = COALESCE(p.document_id, s.document_id)
            WHERE o.user_id = :u AND o.review_status = 'pending' AND o.deleted_at IS NULL
            ORDER BY s.created_at DESC NULLS LAST, o.source_id, o.effective_at DESC"""),
        {"u": uid}).mappings().all()

    sources: dict[str, dict] = {}
    values: dict[str, list] = defaultdict(list)
    for r in rows:
        sid = str(r["source_id"])
        if sid not in sources:
            sources[sid] = {"source_id": sid, "channel": r["channel"], "staged_at": r["staged_at"],
                            "panel_date": r["panel_date"], "panel_type": r["panel_type"],
                            "facility": r["facility"], "document": r["document"]}
        values[sid].append(_row(r, names))

    out = []
    for sid, source in sources.items():
        # the ones that can't wait first, then the unmapped ones, then by name
        rows_ = sorted(values[sid], key=lambda v: (not _alarming(v), not v["unmapped"],
                                                   v["name"].lower()))
        out.append({**source, "total": len(rows_),
                    "alarming": sum(_alarming(v) for v in rows_),
                    "unmapped": sum(v["unmapped"] for v in rows_),
                    "rows": rows_})
    every = [v for vs in values.values() for v in vs]
    return {"total": len(every),
            "alarming": sum(_alarming(v) for v in every),
            "unmapped": sum(v["unmapped"] for v in every),
            "sources": out}
