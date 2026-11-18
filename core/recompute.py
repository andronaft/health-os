"""Recompute missing canonical values (#11).

Rows can hold a numeric value but no `value_canonical` — stored before a synonym/conversion
existed, approved past the unit gate, or written by an importer that bypassed normalization.
Trends and analytics read `value_canonical`, so such rows are invisible there. This re-runs
unit canonicalization + conversion for them. Dry-run unless `apply=True`.

A row without a canonical value was never checked against the critical thresholds: the check
needs the canonical unit. So every value that gets one here goes through the same rule-engine
as ingestion. Before, a pending potassium 6.9 flagged "critical check impossible" lost that
flag once its value was filled in, and became a silent 6.9.

A critical hit gets status='critical'. If the row was already approved, it goes back to
review_status='pending' with an explanation in `notes`, rather than staying approved with a
critical status: the pending queue is what the health summary and the weekly report always
force-show ("CRITICAL value"), while an approved row is only a line among the week's abnormal
values, and only in the week it was approved — years-old data would never surface. Approving it
again (approve_staged on its source) is the user's explicit acknowledgement.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import text

from core.normalize import canonicalize_unit, convert_to_canonical
from safety.critical_values import evaluate, evaluate_limit, load_thresholds

_RETURNED_NOTE = ("returned to review by recompute: its canonical value is critical, and it was "
                  "approved without a critical check")


@dataclass
class RecomputeReport:
    scanned: int = 0
    fixed: Counter = field(default_factory=Counter)          # (code, unit) -> rows
    unconvertible: Counter = field(default_factory=Counter)  # (code, unit, canonical_unit) -> rows
    applied: bool = False
    # critical hits among the filled rows: {id, code, value, unit, canonical, message,
    # was_approved} — was_approved rows go back to pending review (on apply)
    critical: list[dict] = field(default_factory=list)
    # limits (">5" potassium) a critical value may lie past: still impossible to check. Not
    # alerted again — ingestion did, and these rows stay flagged (UNVERIFIABLE_SQL)
    limit_unverified: list[dict] = field(default_factory=list)

    @property
    def n_fixed(self) -> int:
        return sum(self.fixed.values())

    @property
    def n_unconvertible(self) -> int:
        return sum(self.unconvertible.values())

    @property
    def n_returned_to_review(self) -> int:
        return sum(1 for c in self.critical if c["was_approved"])


def recompute_canonical(conn, *, apply: bool = False, user_id: str | None = None,
                        alerter=None) -> RecomputeReport:
    """Fill missing canonical values and run the critical check on them.

    `alerter(title, message)` — as in ingest_observation (in production
    safety.alerts.send_critical_alert). Alerts go out only with apply=True: a dry run changes
    nothing, and the same rows would alert again on the real run.
    """
    rows = conn.execute(
        text(
            """SELECT o.id, o.type_id, ot.code, ot.canonical_unit, o.value_numeric, o.unit,
                      o.comparator, o.review_status
               FROM observations o JOIN observation_types ot ON ot.id = o.type_id
               WHERE o.value_numeric IS NOT NULL AND o.value_canonical IS NULL
                 AND o.deleted_at IS NULL AND (CAST(:u AS uuid) IS NULL OR o.user_id = CAST(:u AS uuid))"""
        ),
        {"u": user_id},
    ).mappings().all()

    report = RecomputeReport(scanned=len(rows), applied=apply)
    thresholds = load_thresholds(conn)
    watched = {t.type_code for t in thresholds}
    factor_cache: dict[tuple, float | None] = {}
    updates: list[dict] = []
    for r in rows:
        value = float(r["value_numeric"])
        if r["canonical_unit"] is None:
            canon = value                                   # dimensionless type
        else:
            unit = canonicalize_unit(r["unit"], r["canonical_unit"])
            if unit is None:
                canon = None
            else:
                # cache the linear map (factor, offset) per type/unit: 16k rows → a few queries
                key = (r["type_id"], unit)
                if key not in factor_cache:
                    zero = convert_to_canonical(r["type_id"], 0.0, unit, r["canonical_unit"], conn)
                    one = convert_to_canonical(r["type_id"], 1.0, unit, r["canonical_unit"], conn)
                    factor_cache[key] = None if zero is None else (one - zero, zero)
                lin = factor_cache[key]
                canon = None if lin is None else value * lin[0] + lin[1]
        if canon is None:
            report.unconvertible[(r["code"], r["unit"], r["canonical_unit"])] += 1
            continue
        report.fixed[(r["code"], r["unit"])] += 1
        updates.append({"id": r["id"], "v": canon})

        if r["code"] not in watched or r["canonical_unit"] is None:
            continue
        hit, uncertain = None, False
        if r["comparator"]:
            hit, uncertain = evaluate_limit(r["code"], r["comparator"], canon,
                                            r["canonical_unit"], thresholds)
        else:
            hit = evaluate(r["code"], canon, r["canonical_unit"], thresholds)
        shown = f"{r['code']} {r['comparator'] or ''}{value:g} {r['unit'] or ''}".strip()
        if hit:
            report.critical.append({
                "id": r["id"], "code": r["code"], "value": shown, "canonical": canon,
                "canonical_unit": r["canonical_unit"], "message": hit.message,
                "was_approved": r["review_status"] == "approved"})
        elif uncertain:
            report.limit_unverified.append({"id": r["id"], "code": r["code"], "value": shown})

    if apply and updates:
        conn.execute(text("UPDATE observations SET value_canonical = :v WHERE id = :id"), updates)
    if apply and report.critical:
        # read by the observation_history trigger
        conn.execute(text("SELECT set_config('app.actor', 'system', true), "
                          "set_config('app.reason', 'recompute_critical', true)"))
        conn.execute(
            text("""UPDATE observations SET status = 'critical', review_status = 'pending',
                        notes = CASE WHEN review_status = 'approved'
                                     THEN concat_ws('; ', notes, CAST(:note AS text))
                                     ELSE notes END
                    WHERE id = :id"""),
            [{"id": c["id"], "note": _RETURNED_NOTE} for c in report.critical],
        )
        if alerter is not None:
            for c in report.critical:
                alerter("Health OS — critical value",
                        f"{c['code']} {c['canonical']:g}{c['canonical_unit']}: {c['message']}")
    return report


def count_missing_canonical(conn, user_id: str) -> dict:
    """Approved numeric rows without a canonical value, by ingestion channel (a health metric)."""
    rows = conn.execute(
        text(
            """SELECT s.channel, count(*) AS n
               FROM observations o JOIN ingestion_sources s ON s.id = o.source_id
               WHERE o.user_id=:u AND o.review_status='approved' AND o.deleted_at IS NULL
                 AND o.value_numeric IS NOT NULL AND o.value_canonical IS NULL
               GROUP BY s.channel ORDER BY n DESC"""
        ),
        {"u": user_id},
    ).all()
    return {"total": sum(n for _, n in rows), "by_channel": {c: n for c, n in rows}}
