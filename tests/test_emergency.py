"""The emergency packet (#74): approved data only, nothing dropped, an over-budget NFC text reported
with its size. A synthetic patient with made-up entries, in the test's rolled-back transaction."""
import contextlib
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import web.app
from core import emergency
from core.emergency import NFC_TAGS, build, ndef_size, nfc_budget, render_text
from core.services import (
    add_allergy,
    add_diagnosis,
    add_medication,
    stage_panel,
    stop_medication,
    upsert_profile,
)
from mcp_server import tools

TODAY = date.today()


@pytest.fixture()
def patient(conn, user_id):
    upsert_profile(conn, user_id, date_of_birth=date(1980, 1, 2), sex="female",
                   blood_type="0", rh_factor="-", emergency_contact="Marta (sister) +34 600 000 000")
    add_allergy(conn, user_id, "penicillin", reaction="anaphylaxis", severity="severe",
                verified=True)
    add_allergy(conn, user_id, "latex", verified=False)
    add_medication(conn, user_id, "Levothyroxine", start_date=TODAY - timedelta(days=400),
                   dose_amount=50, dose_unit="mcg", times_per_day=1)
    add_medication(conn, user_id, "Salbutamol", start_date=TODAY - timedelta(days=90),
                   dose_amount=100, dose_unit="mcg", dosing_pattern="as_needed")
    stopped = add_medication(conn, user_id, "Amoxicillin", start_date=TODAY - timedelta(days=60),
                             dose_amount=500, dose_unit="mg", times_per_day=3)
    stop_medication(conn, user_id, stopped, end_date=TODAY - timedelta(days=50),
                    stop_reason="course finished")
    add_diagnosis(conn, user_id, "Hypothyroidism", icd10_code="E03.9",
                  diagnosed_at=TODAY - timedelta(days=400))
    add_diagnosis(conn, user_id, "Asthma", icd10_code="J45.9",
                  diagnosed_at=TODAY - timedelta(days=90), verification_status="suspected")
    add_diagnosis(conn, user_id, "Appendicitis", icd10_code="K35.8",
                  diagnosed_at=TODAY - timedelta(days=3000), clinical_status="resolved")
    add_diagnosis(conn, user_id, "Epilepsy", icd10_code="G40.9",
                  diagnosed_at=TODAY - timedelta(days=200), verification_status="refuted")
    # a pending (staged, never approved) value: nothing of it may reach the packet
    stage_panel(conn, user_id, TODAY, [{"raw_name": "Potassium", "value": 6.87, "unit": "mmol/L",
                                       "ref_min": 3.5, "ref_max": 5.1}])
    return user_id


def _all_text(packet) -> str:
    return json.dumps(packet, default=str, ensure_ascii=False)


def test_approved_data_only_nothing_stopped_resolved_refuted_or_pending(conn, patient):
    p = build(conn, "en")
    assert not p["empty"]
    assert [m["name"] for m in p["medications"]] == ["Levothyroxine", "Salbutamol"]
    assert [d["name"] for d in p["conditions"]] == ["Hypothyroidism", "Asthma"]
    everything = _all_text(p)
    for gone in ("Amoxicillin", "Appendicitis", "Epilepsy", "6.87", "Potassium", "6,87"):
        assert gone not in everything
    assert p["blood_type"] == "0-"
    assert p["emergency_contact"] == "Marta (sister) +34 600 000 000"


def test_unverified_allergies_are_included_and_marked(conn, patient):
    p = build(conn, "en")
    fields = {f["key"]: f for f in p["lock_screen"]["fields"]}
    allergies = fields["allergies"]["text"].splitlines()
    # the most severe first; the unverified one is there, and says so
    assert allergies == ["penicillin (anaphylaxis, severe)", "latex (not verified)"]
    assert "latex (not verified)" in p["nfc"]["text"]
    uk = {f["key"]: f["text"] for f in build(conn, "uk")["lock_screen"]["fields"]}
    assert "latex (не підтверджено)" in uk["allergies"]
    es = {f["key"]: f["text"] for f in build(conn, "es")["lock_screen"]["fields"]}
    assert "penicillin (anaphylaxis, grave)" in es["allergies"]


def test_a_diagnosis_without_clinical_status_counts_as_current(conn, patient):
    did = add_diagnosis(conn, patient, "Migraine", diagnosed_at=TODAY - timedelta(days=10))
    conn.execute(text("UPDATE diagnoses SET clinical_status=NULL WHERE id=:d"), {"d": did})
    assert "Migraine" in [d["name"] for d in build(conn, "en")["conditions"]]


def test_lock_screen_has_one_block_per_medical_id_field(conn, patient):
    p = build(conn, "en")
    fields = {f["key"]: f for f in p["lock_screen"]["fields"]}
    assert list(fields) == ["conditions", "medications", "allergies", "blood_type",
                            "emergency_contact", "notes"]
    assert fields["conditions"]["text"] == "Hypothyroidism E03.9\nAsthma J45.9 (suspected)"
    assert fields["medications"]["text"] == ("Levothyroxine 50 mcg 1×/day\n"
                                             "Salbutamol 100 mcg (as needed)")
    assert fields["notes"]["text"] == (f"As of {p['as_of'].isoformat()}. From a personal health "
                                       "record kept by the patient, not a clinical system.")
    text = render_text(p, "lock_screen")
    assert "Medical conditions:\nHypothyroidism E03.9" in text
    assert p["privacy"] in text and "no address, no ID numbers" in p["privacy"]


def test_words_we_own_are_translated_entries_stay_as_entered(conn, patient):
    uk = build(conn, "uk")
    assert uk["lang"] == "uk"
    labels = [f["label"] for f in uk["lock_screen"]["fields"]]
    assert labels[0] == "Захворювання" and labels[3] == "Група крові"
    assert "Levothyroxine 50 mcg 1×/день" in uk["nfc"]["text"]
    assert "Станом на" in uk["nfc"]["text"]
    es = build(conn, "es")
    assert "Salbutamol 100 mcg (si es necesario)" in es["nfc"]["text"]
    assert es["notice"].startswith("De un registro personal")
    assert build(conn, "xx")["lang"] == "en"  # an unknown language falls back to English


def test_nfc_text_in_budget_reports_its_size(conn, patient):
    nfc = build(conn, "en")["nfc"]
    assert nfc["size"] == ndef_size(nfc["text"], "en")
    assert nfc["text_bytes"] == len(nfc["text"].encode())
    tags = {t["tag"]: t for t in nfc["tags"]}
    assert tags["NTAG215"]["fits"] and tags["NTAG215"]["capacity"] == 504
    assert nfc["message"].startswith(f"{nfc['size']} bytes on the tag: fits NTAG215")


def test_over_budget_nfc_reports_its_size_and_cuts_nothing(conn, patient):
    names = [f"Made-up medication number {i:02d} with a long name" for i in range(20)]
    for name in names:
        add_medication(conn, patient, name, start_date=TODAY, dose_amount=10, dose_unit="mg",
                       times_per_day=2)
    p = build(conn, "en")
    nfc = p["nfc"]
    assert all(name in nfc["text"] for name in names)  # nothing dropped
    assert nfc["size"] > NFC_TAGS["NTAG216"]
    assert not any(t["fits"] for t in nfc["tags"])
    over = nfc["size"] - 504
    assert {"tag": "NTAG215", "capacity": 504, "fits": False, "over": over} in nfc["tags"]
    assert f"does not fit NTAG215 (504 bytes) by {over} bytes" in nfc["message"]
    assert "Nothing was cut" in nfc["message"]
    assert nfc["message"] in render_text(p, "nfc")


def test_ndef_size_counts_utf8_and_the_record_wrapping():
    # a short Text record: TLV tag+len (2) + header, type length, payload length, "T" (4) +
    # status byte + "en" (3) + text + terminator (1)
    assert ndef_size("", "en") == 10
    assert ndef_size("abc", "en") == 13
    assert ndef_size("абв", "uk") == 16  # Cyrillic is 2 bytes a letter in UTF-8
    # payload over 255: a 4-byte payload length; record over 254: a 3-byte TLV length
    assert ndef_size("a" * 252, "en") == 1 + 3 + 3 + 1 + 255 + 1
    assert ndef_size("a" * 253, "en") == 3 + 5 + 3 + 253 + 3 + 1
    assert NFC_TAGS == {"NTAG213": 144, "NTAG215": 504, "NTAG216": 888}
    edge = "a" * (144 - 10)
    assert [t["fits"] for t in nfc_budget(edge)["tags"]] == [True, True, True]
    assert [t["fits"] for t in nfc_budget(edge + "a")["tags"]] == [False, True, True]


def test_blood_type_joins_the_rh_factor():
    assert emergency.blood_type("A", "+") == "A+"
    assert emergency.blood_type("B+", "+") == "B+"
    assert emergency.blood_type("B+", None) == "B+"
    assert emergency.blood_type("AB", "negative") == "AB-"
    assert emergency.blood_type("AB−", "neg") == "AB-"
    assert emergency.blood_type("0", None) == "0"
    assert emergency.blood_type(None, "+") is None


def test_a_blood_type_its_rh_contradicts_shows_the_conflict():
    # which one is right is not for code to pick: both are printed, with a request to check
    assert emergency.blood_type("A+", "-") == "A+, but Rh is recorded as -: check which is right"
    assert emergency.blood_type("0-", "positive", "uk") == (
        "0-, але резус записано як positive: перевірте, що правильно")
    assert emergency.blood_type("B+", "weak D") == (
        "B+, but Rh is recorded as weak D: check which is right")


def test_a_diagnosis_without_verification_status_is_not_shown_as_confirmed(conn, patient):
    did = add_diagnosis(conn, patient, "Gout", icd10_code="M10.9",
                        diagnosed_at=TODAY - timedelta(days=5))
    conn.execute(text("UPDATE diagnoses SET verification_status=NULL WHERE id=:d"), {"d": did})
    fields = {f["key"]: f["text"] for f in build(conn, "en")["lock_screen"]["fields"]}
    assert "Gout M10.9 (certainty not recorded)" in fields["conditions"].splitlines()
    es = {f["key"]: f["text"] for f in build(conn, "es")["lock_screen"]["fields"]}
    assert "Gout M10.9 (certeza no registrada)" in es["conditions"]


def test_nothing_recorded_never_reads_as_none_known(conn, user_id):
    upsert_profile(conn, user_id, date_of_birth=date(1980, 1, 2), sex="male")
    p = build(conn, "en")
    fields = {f["key"]: f for f in p["lock_screen"]["fields"]}
    assert fields["allergies"]["text"] == "None recorded. That does not mean there are none."
    assert not fields["allergies"]["recorded"] and fields["notes"]["recorded"]
    assert fields["blood_type"]["text"] == "Not recorded."


def test_no_profile_is_an_empty_packet(conn):
    p = build(conn, "es")
    assert p["empty"] and p["message"].startswith("Aún no hay perfil")
    assert p["privacy"] in render_text(p)


class _ReadOnlyProxy:
    """The test's connection for the MCP tool: its own SET TRANSACTION would come after this
    transaction's first query, so it is skipped; everything else runs as is."""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, statement, *args, **kwargs):
        if str(statement).startswith("SET TRANSACTION"):
            return None
        return self.conn.execute(statement, *args, **kwargs)


def test_mcp_tool_returns_the_chosen_layout_as_text(conn, patient, monkeypatch):
    class Engine:
        @contextlib.contextmanager
        def connect(self):
            yield _ReadOnlyProxy(conn)

    monkeypatch.setattr(tools, "rw_engine", Engine())
    lock = json.loads(tools.get_emergency_packet("lock_screen", "en"))
    assert lock["layout"] == "lock_screen" and "nfc" not in lock
    assert "latex (not verified)" in lock["text"] and lock["privacy"] in lock["text"]
    nfc = json.loads(tools.get_emergency_packet("nfc", "uk"))
    assert nfc["nfc"]["size"] == ndef_size(nfc["nfc"]["text"], "uk")
    assert "Amoxicillin" not in nfc["text"]
    assert "error" in json.loads(tools.get_emergency_packet("wallet", "en"))


def test_mcp_as_of_is_the_day_in_health_os_tz(conn, patient, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from core.config import settings

    class Engine:
        @contextlib.contextmanager
        def connect(self):
            yield _ReadOnlyProxy(conn)

    monkeypatch.setattr(tools, "rw_engine", Engine())
    # 25 hours apart: the two zones are never on the same day
    for zone in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
        monkeypatch.setattr(settings, "health_os_tz", zone)
        out = json.loads(tools.get_emergency_packet("lock_screen", "en"))
        now = conn.execute(text("SELECT now()")).scalar()
        assert out["as_of"] == now.astimezone(ZoneInfo(zone)).date().isoformat()
    assert datetime.now(ZoneInfo("Pacific/Kiritimati")).date() != datetime.now(
        ZoneInfo("Pacific/Pago_Pago")).date()
    monkeypatch.setattr(settings, "health_os_tz", "Mars/Base")
    assert "HEALTH_OS_TZ" in json.loads(tools.get_emergency_packet("nfc", "en"))["error"]


def test_api_endpoint(conn, patient, monkeypatch):
    @contextlib.contextmanager
    def on_the_test_connection():
        yield conn

    monkeypatch.setattr(web.app, "read_only_snapshot", on_the_test_connection)
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")
    headers = {"X-Health-OS-Token": "t"}
    r = client.get("/api/v1/emergency?lang=es&tz=Europe/Madrid", headers=headers)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    data = r.json()
    assert data["lang"] == "es" and data["nfc"]["size"] > 0
    assert [f["key"] for f in data["lock_screen"]["fields"]][0] == "conditions"
    assert client.get("/api/v1/emergency?tz=Mars/Base", headers=headers).status_code == 400
    assert client.get("/api/v1/emergency").status_code == 403
