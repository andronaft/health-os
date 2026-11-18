"""Meal nutrients: storage, reference, %norm, cascading soft-delete."""
from datetime import datetime

from sqlalchemy import text

from core.services import add_food_log


def test_nutrients_saved_and_unknown_reported(conn, user_id):
    out = add_food_log(
        conn, user_id, "омлет із овочами", eaten_at=datetime(2026, 9, 20, 8, 0),
        meal_type="breakfast",
        nutrients={"energy_kcal": 300, "protein": 20, "vitamin_c": 40, "неіснуючий_код": 5},
    )
    assert out["nutrients_saved"] == 3
    assert out["unknown_codes"] == ["неіснуючий_код"]
    n = conn.execute(
        text("SELECT count(*) FROM food_nutrients WHERE food_log_id=:f"), {"f": out["id"]}
    ).scalar()
    assert n == 3


def test_v_food_nutrients_join_has_rda_and_unit(conn, user_id):
    out = add_food_log(conn, user_id, "апельсин", eaten_at=datetime(2026, 9, 20, 10, 0),
                       nutrients={"vitamin_c": 70})
    row = conn.execute(
        text("""SELECT nutrient_code, unit, amount, rda FROM v_food_nutrients
                WHERE food_log_id=:f AND nutrient_code='vitamin_c'"""),
        {"f": out["id"]},
    ).first()
    assert row[0] == "vitamin_c"
    assert row[1] == "mg"
    assert float(row[2]) == 70
    assert float(row[3]) == 90  # RDA vitamin_c


def test_soft_delete_hides_nutrients_from_view(conn, user_id):
    out = add_food_log(conn, user_id, "чіпси", eaten_at=datetime(2026, 9, 20, 16, 0),
                       nutrients={"sodium": 500})
    conn.execute(text("UPDATE food_log SET deleted_at=now() WHERE id=:i"), {"i": out["id"]})
    seen = conn.execute(
        text("SELECT count(*) FROM v_food_nutrients WHERE food_log_id=:f"), {"f": out["id"]}
    ).scalar()
    assert seen == 0  # v_food_nutrients joins only with deleted_at IS NULL


def test_daily_sodium_excess_over_upper_limit(conn, user_id):
    day = datetime(2026, 9, 22, 8, 0)
    add_food_log(conn, user_id, "суп", eaten_at=day, nutrients={"sodium": 2000})
    add_food_log(conn, user_id, "снек", eaten_at=day.replace(hour=15),
                 nutrients={"sodium": 1000})
    row = conn.execute(
        text(
            """SELECT sum(amount) AS total, max(upper_limit) AS ul
               FROM v_food_nutrients
               WHERE user_id=:u AND nutrient_code='sodium'
                 AND date_trunc('day', eaten_at)::date = :d"""
        ),
        {"u": user_id, "d": day.date()},
    ).first()
    total, ul = float(row[0]), float(row[1])
    assert total == 3000
    assert total > ul  # sodium overage → excess flag in query_nutrition


def test_limit_only_nutrients_never_deficient(conn, user_id):
    from analytics.nutrition import is_limit_only, summarize

    assert is_limit_only(50, 50) and is_limit_only(2300, 2300)
    assert not is_limit_only(1000, 2500) and not is_limit_only(None, 2) and not is_limit_only(56, None)

    # a day with little sugar/sodium and little calcium: only calcium is a deficiency
    add_food_log(conn, user_id, "plain rice", eaten_at=datetime.now(),
                 nutrients={"added_sugar": 2, "sodium": 100, "calcium": 50})
    deficient = {d["nutrient"] for d in summarize(conn, user_id, days=7)["deficient"]}
    assert "calcium" in deficient
    assert not deficient & {"added_sugar", "sodium"}


def test_a_nutrient_is_averaged_over_every_logged_day(conn, user_id):
    # vitamin D in one meal of a seven-day week was reported as 15 a day (75% of the RDA)
    from datetime import datetime, timedelta

    from analytics.nutrition import summarize
    from core.services import add_food_log
    now = datetime.now()
    for i in range(7):
        nutrients = {"energy_kcal": 2000, **({"vitamin_d": 15} if i == 0 else {})}
        add_food_log(conn, user_id, f"day {i}", eaten_at=now - timedelta(days=i, hours=1),
                     nutrients=nutrients)
    s = summarize(conn, user_id, days=10)
    vitamin_d = next(n for n in s["nutrients"] if n["nutrient"] == "vitamin_d")
    assert s["days_logged"] == 7
    assert abs(vitamin_d["avg_per_day"] - 15 / 7) < 0.01
    assert vitamin_d["flag"] == "deficient"


def test_the_glycemic_index_is_averaged_per_meal(conn, user_id):
    # a meal with more nutrient rows used to weigh more: GI 90 and GI 30 averaged to 45
    from datetime import datetime, timedelta

    from analytics.nutrition import summarize
    from core.services import add_food_log
    now = datetime.now()
    add_food_log(conn, user_id, "white bread", eaten_at=now - timedelta(hours=3),
                 glycemic_index=90, wellbeing="tired", nutrients={"energy_kcal": 300})
    add_food_log(conn, user_id, "lentils", eaten_at=now - timedelta(hours=2),
                 glycemic_index=30, wellbeing="tired",
                 nutrients={"energy_kcal": 300, "protein": 18, "fiber": 8, "sugar": 2})
    [row] = summarize(conn, user_id, days=1)["wellbeing_association"]
    assert row["meals"] == 2 and float(row["avg_gi"]) == 60
