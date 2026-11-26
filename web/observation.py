"""Where one value comes from: the drawer behind a click on a lab value (/api/v1/observations/{id}).

One observation as it was printed on its form and as it was stored: the printed value and unit,
the canonical value it was converted to (or plainly "not converted"), the range and where that
range came from, the review state, the notes, the document and panel it was read from with the
panel's other values. Plain data, no model output.

Honest about what isn't there:
- a value still under review is sent with `pending: true`, and its status is the form's, not a
  fact; a deleted row, or a row of another user, is None (a 404);
- the range stored on a value is the one printed on its form: nothing fills it in. A form
  without one gets `source: "none"`, and the general default range of the catalog is sent apart,
  as a hint that the status was NOT computed from;
- a row the panel's page number would come from is not stored, so there is none to send.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from core import queries as q
from core.normalize import canonicalize_unit
from safety.critical_values import LANGUAGES
from web.labs import _conversions, _number, band

OTHERS_MAX = 200  # a panel is a form: a few dozen rows; the cap only keeps a bad import in check


def _uuid(value: str) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        return None


def _printed(row) -> dict:
    return {"value": _number(row["value_numeric"]), "comparator": row["comparator"],
            "text": row["value_text"], "unit": row["unit"]}


def _conversion(row, conversions: dict) -> dict:
    """What happened between the form's number and the canonical one, said as it is:
    - text: a result in words, there is no number to convert;
    - no_canonical_unit: the marker has no canonical unit, the number is kept as printed;
    - not_converted: no canonical value was stored (an unknown unit, an unmapped row);
    - same_unit: printed in the canonical unit already (spelling aside);
    - converted: with the factor (and offset) of the conversion, when it is still in the table."""
    canonical_unit = row["canonical_unit"]
    value = _number(row["value_canonical"])
    out = {"value": value, "unit": canonical_unit, "factor": None, "offset": None}
    if row["value_numeric"] is None:
        return {**out, "state": "text"}
    if row["type_id"] is not None and canonical_unit is None:
        return {**out, "state": "no_canonical_unit"}
    if value is None:
        return {**out, "state": "not_converted"}
    unit = canonicalize_unit(row["unit"], canonical_unit)
    if unit == canonical_unit:
        return {**out, "state": "same_unit"}
    factor, offset = conversions.get(unit, (None, None))
    return {**out, "state": "converted", "factor": factor, "offset": offset or None}


def _defaults(conn, type_id, sex: str | None) -> list[dict]:
    """The catalog's general ranges for the marker (seed/data.py REFERENCE_RANGES), for the
    user's sex or for anyone. Only a hint: no status is ever computed from them."""
    if type_id is None:
        return []
    rows = conn.execute(text(
        """SELECT unit, range_kind, range_min, range_max, optimal_min, optimal_max, sex,
                  condition, source
           FROM reference_ranges
           WHERE type_id = :t AND (sex IS NULL OR sex = :sex)
           ORDER BY sex NULLS LAST, condition NULLS FIRST, id"""),
        {"t": type_id, "sex": sex}).mappings().all()
    return [{"unit": r["unit"], "kind": r["range_kind"],
             "min": _number(r["range_min"] if r["range_min"] is not None else r["optimal_min"]),
             "max": _number(r["range_max"] if r["range_max"] is not None else r["optimal_max"]),
             "sex": r["sex"], "condition": r["condition"], "source": r["source"]} for r in rows]


def _others(conn, uid, panel_id, own_id, names: dict) -> list[dict]:
    rows = conn.execute(text(
        """SELECT o.id::text AS id, ot.code, o.raw_name, o.value_numeric, o.comparator,
                  o.value_text, o.unit, o.ref_min, o.ref_max, o.status, o.review_status
           FROM observations o LEFT JOIN observation_types ot ON ot.id = o.type_id
           WHERE o.panel_id = :p AND o.user_id = :u AND o.deleted_at IS NULL AND o.id <> :id
           LIMIT :lim"""),
        {"p": panel_id, "u": uid, "id": own_id, "lim": OTHERS_MAX}).mappings().all()
    out = [{"id": r["id"], "code": r["code"],
            "name": names.get(r["code"]) or r["raw_name"] or r["code"],
            **_printed(r), "ref_min": _number(r["ref_min"]), "ref_max": _number(r["ref_max"]),
            "status": r["status"], "pending": r["review_status"] != "approved"} for r in rows]
    return sorted(out, key=lambda o: str(o["name"]).lower())


def observation(conn, observation_id: str, lang: str = "en") -> dict | None:
    """One of the user's observations with where it came from; None if there is no such live row
    of theirs (a malformed id, another user's row, a deleted one)."""
    lang = lang if lang in LANGUAGES else "en"
    oid = _uuid(observation_id)
    uid = q.user_id(conn)
    if oid is None or uid is None:
        return None
    row = conn.execute(text(
        """SELECT o.id::text AS id, o.type_id, ot.code, ot.category, ot.canonical_unit,
                  o.raw_name, o.effective_at, o.time_precision, o.value_numeric, o.comparator,
                  o.value_text, o.unit, o.value_canonical, o.ref_min, o.ref_max, o.status,
                  o.result_status, o.review_status, o.notes, o.created_at,
                  o.panel_id::text AS panel_id,
                  s.channel, s.review_status AS source_review_status, s.reviewed_at,
                  s.reviewed_by, s.created_at AS staged_at,
                  p.panel_date, p.panel_type, p.row_count_in_document, p.rows_extracted,
                  f.name AS facility,
                  d.id::text AS document_id, d.title AS document_title,
                  d.document_date, d.doc_type,
                  -- the row's own approval: observation_history keeps the row as it was before
                  -- each update, so the latest entry that wasn't approved yet is the update that
                  -- approved it. The source's reviewed_at moves on every later approval of it.
                  (SELECT max(h.changed_at) FROM observation_history h
                    WHERE h.observation_id = o.id
                      AND h.old_row->>'review_status' IS DISTINCT FROM 'approved') AS approved_at
           FROM observations o
           LEFT JOIN observation_types ot ON ot.id = o.type_id
           JOIN ingestion_sources s ON s.id = o.source_id
           LEFT JOIN panels p ON p.id = o.panel_id AND p.user_id = o.user_id
           LEFT JOIN facilities f ON f.id = p.facility_id
           LEFT JOIN documents d ON d.id = COALESCE(p.document_id, s.document_id)
                                AND d.user_id = o.user_id AND d.deleted_at IS NULL
           WHERE o.id = :id AND o.user_id = :u AND o.deleted_at IS NULL"""),
        {"id": oid, "u": uid}).mappings().first()
    if row is None:
        return None

    names = q.marker_names(conn, lang)
    sex = conn.execute(text("SELECT sex FROM user_profile WHERE user_id = :u"),
                       {"u": uid}).scalar()
    conversions = (_conversions(conn, row["type_id"], row["canonical_unit"])
                   if row["type_id"] is not None else {})
    pending = row["review_status"] != "approved"
    on_form = row["ref_min"] is not None or row["ref_max"] is not None
    approved = not pending

    return {
        "id": row["id"],
        "code": row["code"],
        "name": names.get(row["code"]) or row["raw_name"] or row["code"],
        "category": row["category"],
        "unmapped": row["type_id"] is None,
        "raw_name": row["raw_name"],
        "at": row["effective_at"],
        "time_precision": row["time_precision"],
        "printed": _printed(row),
        "canonical": _conversion(row, conversions),
        "range": {
            "min": _number(row["ref_min"]), "max": _number(row["ref_max"]),
            "unit": row["unit"],
            "source": "form" if on_form else "none",
            # the same range in the canonical unit, as the chart draws it; None if it can't be
            "canonical": band(row, row["canonical_unit"], conversions) if on_form else None,
            "defaults": [] if on_form else _defaults(conn, row["type_id"], sex),
        },
        "status": row["status"],
        "result_status": row["result_status"],
        "pending": pending,
        "review": {
            "status": row["review_status"],
            "channel": row["channel"],
            "staged_at": row["staged_at"],
            # when this row was approved (from its history); None for a row stored approved
            "approved_at": row["approved_at"] if approved else None,
            # when its source was last approved: a later approval of the same source (a row
            # mapped afterwards) moves it, so it is said as the source's, never as this row's.
            # Nothing for a pending row: a source keeps the date while some of its rows wait
            "source_reviewed_at": row["reviewed_at"] if approved else None,
            "reviewed_by": row["reviewed_by"] if approved else None,
        },
        "notes": row["notes"],
        "document": row["document_id"] and {
            "title": row["document_title"], "date": row["document_date"],
            "type": row["doc_type"]},
        "panel": row["panel_id"] and {
            "date": row["panel_date"], "type": row["panel_type"], "facility": row["facility"],
            "rows_in_document": row["row_count_in_document"],
            "rows_extracted": row["rows_extracted"],
            "others": _others(conn, uid, row["panel_id"], row["id"], names),
        },
    }
