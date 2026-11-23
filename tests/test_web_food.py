"""GET /api/v1/food: the food diary over a window, with the same averages as nutrition_report. The
endpoint runs on the test's own connection, so everything stays in its rolled-back transaction.
Made-up meals and the fictional demo patient only."""
import contextlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import web.app
from analytics.nutrition import summarize
from core.services import add_food_log
from seed.demo import MEALS, load_demo
from web.food import DEFAULT_DAYS, MAX_DAYS, window_days

HEADERS = {"X-Health-OS-Token": "t"}


@pytest.fixture()
def get(conn, monkeypatch):
    @contextlib.contextmanager
    def on_the_test_connection():
        yield conn

    monkeypatch.setattr(web.app, "read_only_snapshot", on_the_test_connection)
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")

    def fetch(query=""):
        r = client.get(f"/api/v1/food{query}", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        return r.json()

    return fetch


def _utc_today() -> datetime:
    """Midnight of today in the database's clock: meals are naive local times in a UTC session."""
    return datetime.combine(datetime.now(UTC).date(), datetime.min.time())


def test_the_api_needs_the_token(conn):
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")
    assert client.get("/api/v1/food").status_code == 403


def test_the_demo_patients_meals_and_the_same_averages_as_nutrition_report(conn, get):
    uid = load_demo(conn, today=_utc_today().date())
    data = get()
    assert data["window"] == {"days": DEFAULT_DAYS, "choices": [7, 30, 90]}
    assert data["meals_total"] == len(data["meals"]) == len(MEALS)
    assert data["meals_truncated"] is False

    report = summarize(conn, uid, DEFAULT_DAYS)
    assert data["days_logged"] == report["days_logged"]
    by_code = {n["code"]: n for n in data["nutrients"]}
    for n in report["nutrients"]:
        assert by_code[n["nutrient"]]["avg_per_day"] == n["avg_per_day"]
        assert by_code[n["nutrient"]]["pct_rda"] == n["pct_rda"]
        assert by_code[n["nutrient"]]["flag"] == n["flag"]


def test_every_catalog_nutrient_is_listed_and_an_unlogged_one_is_not_a_zero(conn, user_id, get):
    add_food_log(conn, user_id, "Toast", eaten_at=_utc_today() - timedelta(hours=12),
                 meal_type="snack", nutrients={"energy_kcal": 200, "protein": 6})
    data = get()
    catalog = conn.execute(text("SELECT count(*) FROM nutrient_types")).scalar()
    assert len(data["nutrients"]) == catalog
    by_code = {n["code"]: n for n in data["nutrients"]}
    assert by_code["energy_kcal"]["logged"] is True and by_code["energy_kcal"]["avg_per_day"] == 200
    vitamin_d = by_code["vitamin_d"]
    assert vitamin_d["logged"] is False and vitamin_d["avg_per_day"] is None
    assert vitamin_d["flag"] is None  # never logged ≠ deficient
    assert by_code["sodium"]["limit_only"] is True and by_code["protein"]["limit_only"] is False


def test_daily_totals_add_up_the_meals_of_that_day(conn, user_id, get):
    day = _utc_today() - timedelta(days=2)
    add_food_log(conn, user_id, "Porridge", eaten_at=day + timedelta(hours=8),
                 meal_type="breakfast", nutrients={"energy_kcal": 300, "sodium": 100})
    add_food_log(conn, user_id, "Soup", eaten_at=day + timedelta(hours=13),
                 meal_type="lunch", nutrients={"energy_kcal": 450, "sodium": 900})
    [row] = get()["daily"]
    assert row["date"] == day.date().isoformat() and row["meals"] == 2
    assert row["totals"]["energy_kcal"] == 750 and row["totals"]["sodium"] == 1000


def test_times_are_wall_clock_and_odd_ones_are_flagged(conn, user_id, get):
    yesterday = _utc_today() - timedelta(days=1)
    add_food_log(conn, user_id, "Late dinner", eaten_at=yesterday + timedelta(minutes=30),
                 meal_type="dinner", nutrients={"energy_kcal": 600})
    add_food_log(conn, user_id, "Coffee and cake", eaten_at=yesterday + timedelta(hours=16, minutes=30),
                 meal_type="breakfast", nutrients={"energy_kcal": 400})
    add_food_log(conn, user_id, "Lunch", eaten_at=yesterday + timedelta(hours=13),
                 meal_type="lunch", nutrients={"energy_kcal": 700})
    by_name = {m["description"]: m for m in get()["meals"]}
    late = by_name["Late dinner"]
    assert late["at"] == f"{yesterday.date().isoformat()}T00:30"  # no offset: not shifted a day
    assert late["date"] == yesterday.date().isoformat() and late["time_check"] == "night"
    assert by_name["Coffee and cake"]["time_check"] == "unusual"
    assert by_name["Lunch"]["time_check"] is None
    assert by_name["Lunch"]["nutrients"]["energy_kcal"] == 700


def test_the_window_follows_days(conn, user_id, get):
    add_food_log(conn, user_id, "Recent", eaten_at=_utc_today() - timedelta(days=3),
                 meal_type="snack", nutrients={"energy_kcal": 100})
    add_food_log(conn, user_id, "Older", eaten_at=_utc_today() - timedelta(days=40),
                 meal_type="snack", nutrients={"energy_kcal": 100})
    assert [m["description"] for m in get()["meals"]] == ["Recent"]
    assert [m["description"] for m in get("?days=90")["meals"]] == ["Recent", "Older"]
    assert get("?days=90")["window"]["days"] == 90


@pytest.mark.parametrize(("value", "days"), [
    (None, DEFAULT_DAYS), ("abc", DEFAULT_DAYS), ("0", 1), ("-5", 1), ("7", 7),
    ("100000", MAX_DAYS)])
def test_window_days_is_clamped(value, days):
    assert window_days(value) == days


def test_names_follow_the_language(conn, user_id, get):
    add_food_log(conn, user_id, "Salmon", eaten_at=_utc_today() - timedelta(hours=10),
                 meal_type="snack", nutrients={"vitamin_d": 10})
    name = lambda data: {n["code"]: n["name"] for n in data["nutrients"]}["vitamin_d"]  # noqa: E731
    assert name(get("?lang=uk")) == "Вітамін D"
    assert name(get("?lang=es")) == "Vitamina D"
    assert name(get("?lang=xx")) == "Vitamin D"


def test_deleted_meals_are_not_shown(conn, user_id, get):
    meal = add_food_log(conn, user_id, "Mistake", eaten_at=_utc_today() - timedelta(hours=10),
                        meal_type="snack", nutrients={"energy_kcal": 999})
    conn.execute(text("UPDATE food_log SET deleted_at = now() WHERE id = :id"), {"id": meal["id"]})
    data = get()
    assert data["meals"] == [] and data["daily"] == [] and data["days_logged"] == 0

