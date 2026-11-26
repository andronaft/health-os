"""Weekly report — deterministic scaffold (plan 5.3).

Data is gathered by code (zero LLM); the LLM narrative (cautious hypotheses with an
anxiety budget) is optional on top, fully in Phase 5. Includes HEALTH METRICS OF THE
SYSTEM ITSELF: pending-queue size and corrected fraction — their growth = extractor
degradation or a new lab.

"Everything stable, no action needed" is a legitimate and desirable result.
"""
from __future__ import annotations

from sqlalchemy import text

from core.health_summary import is_alarming, read_facts, read_unverifiable_approved
from core.recompute import count_missing_canonical

# approved in the window: when the user approved it, not when it was staged. A panel staged
# twelve days ago and approved today used to miss every weekly report. Rows that never went
# through review (a device import) count from when they were stored.
_APPROVED_IN_WINDOW = """
               LEFT JOIN ingestion_sources s ON s.id = o.source_id
               WHERE o.user_id=:u AND o.review_status='approved' AND o.deleted_at IS NULL
                 AND COALESCE(s.reviewed_at, o.created_at) >= now() - make_interval(days => :d)"""


def build(conn, user_id: str, days: int = 7) -> dict:
    new_values = conn.execute(
        text(
            f"""SELECT ot.code, count(*) AS n FROM observations o
               JOIN observation_types ot ON ot.id=o.type_id
               {_APPROVED_IN_WINDOW}
               GROUP BY ot.code ORDER BY n DESC"""
        ),
        {"u": user_id, "d": days},
    ).mappings().all()

    abnormal = conn.execute(
        text(
            f"""SELECT ot.code, o.value_canonical, o.comparator, o.status, o.effective_at
               FROM observations o JOIN observation_types ot ON ot.id=o.type_id
               {_APPROVED_IN_WINDOW}
                 AND o.status IN ('high','low','critical')
               ORDER BY o.effective_at DESC LIMIT 20"""
        ),
        {"u": user_id, "d": days},
    ).mappings().all()

    # pending values that can't wait for their review: critical, or impossible to check. The
    # report used to read only approved rows and call a week with one of these "stable"
    alarming = [{"code": p["code"] or p["raw_name"], "value": p["value_numeric"], "comparator": p["comparator"],
                 "unit": p["unit"], "effective_at": p["effective_at"], "status": p["status"],
                 "critical_check_impossible": bool(p["unverifiable"])}
                for p in read_facts(conn, user_id)["pending"] if is_alarming(p)]
    # approved this week, but the critical check never settled them (">5" potassium may be 7):
    # approval used to drop them from every list and the week read "stable"
    unverifiable = [{k: u[k] for k in ("code", "value", "comparator", "unit", "effective_at",
                                       "why")}
                    for u in read_unverifiable_approved(conn, user_id, days=days)]

    # system health metrics
    pending_q = conn.execute(
        text("SELECT count(*) FROM observations WHERE user_id=:u AND review_status='pending' "
             "AND deleted_at IS NULL"),
        {"u": user_id},
    ).scalar()
    sources = conn.execute(
        text("""SELECT count(*) FILTER (WHERE corrected_fields IS NOT NULL) AS corrected,
                       count(*) FILTER (WHERE review_status='approved') AS approved
                FROM ingestion_sources WHERE user_id=:u"""),
        {"u": user_id},
    ).mappings().first()
    approved = sources["approved"] or 0
    corrected_ratio = (sources["corrected"] / approved) if approved else 0.0

    # nutrition for the week (top deficiencies/excesses) — deterministic, via the views
    from analytics.nutrition import summarize as _nutrition
    nut = _nutrition(conn, user_id, days)
    nutrition_block = {
        "days_logged": nut["days_logged"],
        "top_deficient": nut["deficient"][:3],
        "top_excess": nut["excess"][:3],
    }

    # wearable changes that lasted (#75): worth checking, so the week is not "stable"
    from datetime import timedelta

    from analytics import sustained as _sustained
    today = conn.execute(text("SELECT now()")).scalar().astimezone(_sustained.db_zone(conn)).date()
    lasting = _sustained.find(conn, user_id, today - timedelta(days=days - 1), today)
    sustained_block = {"findings": lasting["findings"], "limits": lasting["limits"],
                       "wording": lasting["wording"]}

    return {
        "period_days": days,
        "sustained": sustained_block,
        "new_values": [dict(r) for r in new_values],
        "abnormal": [dict(r) for r in abnormal],
        "alarming_pending": alarming,
        "unverifiable_approved": unverifiable,
        "nutrition": nutrition_block,
        "system_health": {
            "pending_queue": pending_q,
            # approved numbers invisible to trends/analytics (#11) — should be 0
            "approved_without_canonical": count_missing_canonical(conn, user_id),
            "corrected_ratio": round(corrected_ratio, 3),
            "note": ("A pending value is critical or can't be checked — see alarming_pending; "
                     "compare it with the form now." if alarming else
                     "An approved value couldn't be checked against critical thresholds — see "
                     "unverifiable_approved; compare it with the form." if unverifiable else
                     "Pending queue is large — risk of 'rubber-stamp ok' (kill criterion)."
                     if (pending_q or 0) >= 10 else "Pending queue is normal."),
        },
        "stable": not abnormal and not alarming and not unverifiable and (pending_q or 0) < 10
        and not lasting["findings"],
    }
