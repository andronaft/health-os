"""The Food page's data: the food diary over a window, with the same averages as nutrition_report.

The averages, %RDA and flags come from analytics.nutrition.summarize, the function behind
query_nutrition and nutrition_report, so the page and the chat can't disagree. Every nutrient in
the catalog is listed: one with no amount logged in the window says so instead of passing for a
zero. Meal times are stored as naive local times in a UTC session; they are sent as wall-clock
"YYYY-MM-DDTHH:MM" without an offset, so the browser can't shift them into another day. The time
check is services.meal_time_note, the one log_meal answers with. Plain data, no model output.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import text

from analytics.nutrition import is_limit_only, summarize
from core import queries as q
from core.services import meal_time_note
from safety.critical_values import LANGUAGES

DAY_CHOICES = (7, 30, 90)
DEFAULT_DAYS = 30
MAX_DAYS = 365
MEAL_ROWS = 1000
# the per-meal columns of the meal table
MEAL_NUTRIENTS = ("energy_kcal", "protein", "carbs", "fat", "fiber", "sugar", "sodium")
# the same window summarize() reads: N days back from now, and a day ahead for "now" in local time
WINDOW_SQL = ("eaten_at >= now() - make_interval(days => :d) "
              "AND eaten_at <= now() + interval '1 day'")


def window_days(value) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(1, min(days, MAX_DAYS))


def _number(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def nutrient_names(conn, lang: str) -> dict[str, str]:
    """code → name in `lang`; a nutrient without one falls back to English, then Ukrainian."""
    rows = conn.execute(text("SELECT nutrient_code, lang, name FROM v_nutrient_type_names "
                             "WHERE lang IN ('uk', 'en', :lang)"), {"lang": lang}).all()
    rank = {"uk": 0, "en": 1, lang: 2}
    return {code: name for code, _, name in sorted(rows, key=lambda r: rank[r[1]])}


def _nutrients(conn, summary: dict, names: dict) -> list[dict]:
    """Every catalog nutrient in catalog order, with the window's average when one was logged."""
    averages = {n["nutrient"]: n for n in summary["nutrients"]}
    catalog = conn.execute(text(
        "SELECT code, category, unit, rda, upper_limit FROM nutrient_types "
        "ORDER BY sort_order NULLS LAST, code")).mappings().all()
    out = []
    for c in catalog:
        code, found = c["code"], averages.get(c["code"])
        rda, ul = _number(c["rda"]), _number(c["upper_limit"])
        out.append({"code": code, "name": names.get(code) or code, "category": c["category"],
                    "unit": c["unit"], "rda": rda, "upper_limit": ul,
                    "limit_only": is_limit_only(rda, ul), "logged": found is not None,
                    "avg_per_day": found["avg_per_day"] if found else None,
                    "pct_rda": found["pct_rda"] if found else None,
                    "flag": found["flag"] if found else None})
    return out


def _daily(conn, uid: str, days: int) -> list[dict]:
    """One row per day with a meal, oldest first: how many meals and each nutrient's total."""
    meals = conn.execute(text(
        f"""SELECT (eaten_at AT TIME ZONE 'UTC')::date AS day, count(*) AS meals
            FROM v_food_log WHERE user_id=:u AND {WINDOW_SQL}
            GROUP BY 1 ORDER BY 1"""), {"u": uid, "d": days}).all()
    totals: dict = defaultdict(dict)
    for day, code, total in conn.execute(text(
            f"""SELECT (eaten_at AT TIME ZONE 'UTC')::date, nutrient_code, sum(amount)
                FROM v_food_nutrients WHERE user_id=:u AND {WINDOW_SQL}
                GROUP BY 1, 2"""), {"u": uid, "d": days}):
        totals[day][code] = _number(total)
    return [{"date": day, "meals": n, "totals": totals.get(day, {})} for day, n in meals]


def _time_check(at, meal_type) -> str | None:
    """"night" (before 04:00: it counts toward that date) or "unusual" (a main meal outside its
    usual hours), by the rule log_meal applies; None when the time looks right."""
    if not meal_time_note(at, meal_type):
        return None
    return "night" if at.hour < 4 else "unusual"


def _meals(conn, uid: str, days: int) -> tuple[list[dict], bool]:
    picks = ", ".join(f"sum(fn.amount) FILTER (WHERE fn.nutrient_code = '{code}') AS {code}"
                      for code in MEAL_NUTRIENTS)  # fixed names above, never a caller's string
    rows = conn.execute(text(
        f"""SELECT f.eaten_at AT TIME ZONE 'UTC' AS at, f.meal_type, f.description, f.portion,
                   f.glycemic_index, f.glycemic_load, f.symptoms, f.wellbeing, f.notes,
                   f.nutrient_source, n.*
            FROM v_food_log f
            LEFT JOIN LATERAL (SELECT {picks} FROM v_food_nutrients fn
                               WHERE fn.food_log_id = f.id) n ON true
            WHERE f.user_id=:u AND {WINDOW_SQL.replace('eaten_at', 'f.eaten_at')}
            ORDER BY f.eaten_at DESC LIMIT :lim"""),
        {"u": uid, "d": days, "lim": MEAL_ROWS + 1}).mappings().all()
    out = []
    for r in rows[:MEAL_ROWS]:
        at = r["at"]
        out.append({"at": at.strftime("%Y-%m-%dT%H:%M"), "date": at.date(),
                    "meal_type": r["meal_type"], "description": r["description"],
                    "portion": r["portion"], "glycemic_index": r["glycemic_index"],
                    "glycemic_load": _number(r["glycemic_load"]), "symptoms": r["symptoms"],
                    "wellbeing": r["wellbeing"], "notes": r["notes"],
                    "nutrient_source": r["nutrient_source"],
                    "time_check": _time_check(at, r["meal_type"]),
                    "nutrients": {code: _number(r[code]) for code in MEAL_NUTRIENTS}})
    return out, len(rows) > MEAL_ROWS


def food_page(conn, lang: str = "en", days=DEFAULT_DAYS) -> dict:
    lang = lang if lang in LANGUAGES else "en"
    days = window_days(days)
    window = {"days": days, "choices": list(DAY_CHOICES)}
    uid = q.user_id(conn)
    if uid is None:
        return {"window": window, "days_logged": 0, "meals_total": 0, "nutrients": [],
                "daily": [], "meals": [], "meals_truncated": False, "wellbeing": []}
    summary = summarize(conn, uid, days)
    meals, truncated = _meals(conn, uid, days)
    daily = _daily(conn, uid, days)
    return {"window": window,
            "days_logged": summary["days_logged"],
            "meals_total": sum(d["meals"] for d in daily),
            "nutrients": _nutrients(conn, summary, nutrient_names(conn, lang)),
            "daily": daily,
            "meals": meals,
            "meals_truncated": truncated,
            "wellbeing": [{k: _number(v) if k != "wellbeing" else v for k, v in a.items()}
                          for a in summary["wellbeing_association"]]}
