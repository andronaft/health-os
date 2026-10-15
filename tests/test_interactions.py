import pytest

from safety.interactions import (
    biotin_interference_warning,
    check_paracetamol_load,
    refuse_interaction_query,
)


def test_refusal_is_explicit():
    r = refuse_interaction_query()
    assert "assess drug interactions" in r
    assert "pharmacist" in r or "Drugs.com" in r


def test_paracetamol_within_limit():
    load = check_paracetamol_load([{"name": "Парацетамол", "mg_per_dose": 500, "doses_per_day": 3}])
    assert load.level == "ok"
    assert load.total_mg_per_day == 1500


def test_paracetamol_exceeded_across_products():
    # three OTCs with paracetamol at once — the main real risk
    load = check_paracetamol_load([
        {"name": "Цитрамон", "mg_per_dose": 500, "doses_per_day": 3},
        {"name": "Терафлю", "mg_per_dose": 650, "doses_per_day": 3},
        {"name": "Панадол", "mg_per_dose": 500, "doses_per_day": 4},
    ])
    assert load.level == "exceeded"
    assert load.total_mg_per_day > 4000
    assert len(load.products) == 3


def test_paracetamol_caution_band():
    load = check_paracetamol_load([{"name": "Панадол", "mg_per_dose": 1000, "doses_per_day": 3}])
    assert load.level == "caution"  # 3000 mg


def test_biotin_warning_for_tsh():
    w = biotin_interference_warning(taking_biotin=True, planned_test_codes=["tsh", "glucose"])
    assert w and "tsh" in w


def test_biotin_no_warning_without_biotin():
    assert biotin_interference_warning(False, ["tsh"]) is None
    assert biotin_interference_warning(True, ["glucose"]) is None


# --- a dose that isn't known is never counted as 0 mg (that read as "within limits") ---
@pytest.mark.parametrize("product", [
    {"name": "Панадол"},                                         # nothing known
    {"name": "Панадол", "mg_per_dose": 500},                     # how often?
    {"name": "Панадол", "doses_per_day": 4},                     # how much?
    {"name": "Панадол", "mg_per_dose": -500, "doses_per_day": 4},
    {"name": "Панадол", "mg_per_dose": "a tablet", "doses_per_day": 4},
])
def test_paracetamol_unknown_dose_is_incomplete(product):
    load = check_paracetamol_load([product])
    assert load.level == "incomplete" and load.missing_dose == ["Панадол"]
    assert "within limits" not in load.message and "Панадол" in load.message


def test_paracetamol_partial_total_is_still_incomplete():
    load = check_paracetamol_load([{"name": "Панадол", "mg_per_dose": 500, "doses_per_day": 2},
                                   {"name": "Фервекс"}])
    assert load.level == "incomplete" and load.total_mg_per_day == 1000
    assert load.missing_dose == ["Фервекс"] and "~1000 mg/day" in load.message


def test_paracetamol_exceeded_wins_and_names_what_was_not_counted():
    load = check_paracetamol_load([{"name": "A", "mg_per_dose": 1000, "doses_per_day": 5},
                                   {"name": "B"}])
    assert load.level == "exceeded" and "Not counted (dose unknown): B" in load.message


def test_paracetamol_numeric_strings_still_count():
    load = check_paracetamol_load([{"name": "P", "mg_per_dose": "1000", "doses_per_day": "4"}])
    assert load.level == "caution" and load.total_mg_per_day == 4000 and not load.missing_dose
