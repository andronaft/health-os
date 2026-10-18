from datetime import date

from core.health_summary import build
from core.services import add_allergy, add_diagnosis, add_medication, upsert_profile


def test_summary_reflects_entities_and_validates(conn, user_id):
    upsert_profile(conn, user_id, date_of_birth=date(1990, 1, 1), sex="male")
    add_allergy(conn, user_id, "пеніцилін", reaction="анафілаксія", verified=True)
    add_allergy(conn, user_id, "пилок", verified=False)
    add_diagnosis(conn, user_id, "ГЕРХ", diagnosed_at=date(2023, 1, 1),
                  verification_status="suspected")
    add_medication(conn, user_id, "Аторвастатин", start_date=date(2024, 1, 1),
                   dose_amount=20, dose_unit="mg", times_per_day=1)

    res = build(conn, user_id)
    assert res.valid, res.issues
    assert res.counts == {"allergies": 2, "active_diagnoses": 1, "current_medications": 1,
                          "habits": 0}
    # the unverified allergy is marked as such
    assert "unverified" in res.text
    # a suspected diagnosis is not presented as fact
    assert "suspected" in res.text
    # protection against false reassurance: something "never measured"
    assert "never" in res.text


def test_summary_empty_profile(conn, user_id):
    res = build(conn, user_id)
    assert res.valid
    assert res.counts["allergies"] == 0
    assert "not filled in" in res.text or "Profile" in res.text
