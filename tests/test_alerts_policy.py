from pathlib import Path

from core.config import settings
from core.services import ingest_observation
from safety import alerts, narrative_flags, policy


class FakeAlerter:
    def __init__(self):
        self.calls = []

    def __call__(self, title, message):
        self.calls.append((title, message))


# --- policy ---
def test_policy_text_contains_key_elements():
    txt = policy.escalation_policy_text()
    assert "103/112" in txt
    assert "testicular torsion" in txt
    assert "Bi-RADS" in txt or "malign" in txt
    assert policy.POLICY_VERSION in txt


def test_disclaimer_nonempty():
    assert "does not replace a doctor" in policy.DISCLAIMER


# --- critical value fires alerter ---
def test_critical_observation_triggers_alerter(conn, user_id):
    fake = FakeAlerter()
    res = ingest_observation(conn, user_id, "калій", 6.8, "mmol/L", alerter=fake)
    assert res.critical is not None
    assert len(fake.calls) == 1
    assert "калій" in fake.calls[0][1] or "potassium" in fake.calls[0][1]


def test_normal_observation_no_alert(conn, user_id):
    fake = FakeAlerter()
    ingest_observation(conn, user_id, "глюкоза", 5.2, "mmol/L",
                       ref_min=3.9, ref_max=5.5, alerter=fake)
    assert fake.calls == []


# --- narrative check_and_alert ---
def test_narrative_alert_on_malignancy():
    fake = FakeAlerter()
    hits = narrative_flags.check_and_alert(
        "Об'ємне утворення, підозра на малігнізацію", source_label="УЗД", alerter=fake
    )
    assert hits
    assert len(fake.calls) == 1
    assert "УЗД" in fake.calls[0][1]


def test_narrative_no_alert_on_clean_text():
    fake = FakeAlerter()
    hits = narrative_flags.check_and_alert("Патології не виявлено.", alerter=fake)
    assert hits == []
    assert fake.calls == []


def test_alert_log_failure_does_not_break_delivery(monkeypatch, tmp_path, capsys):
    from safety import alerts

    blocked = tmp_path / "ro"
    blocked.write_text("")                       # a file where a directory is expected
    monkeypatch.setattr(alerts, "_LOG", blocked / "alerts.log")
    monkeypatch.setattr(alerts, "_macos_notify", lambda *a: False)
    monkeypatch.setattr(alerts, "_telegram_send", lambda *a: False)
    assert alerts.send_critical_alert("t", "potassium 6.8") == ["log"]
    assert "potassium 6.8" in capsys.readouterr().err


def test_tests_never_reach_the_real_alert_channels(tmp_path):
    # the install's own log, notifications and Telegram are off limits for the suite
    real_log = Path(alerts.__file__).resolve().parent.parent / "data" / "alerts.log"
    assert alerts._LOG != real_log and alerts._LOG.parent == tmp_path
    assert alerts.send_critical_alert("t", "potassium 6.9") == ["log"]
    assert not settings.alert_telegram_bot_token and not settings.alert_telegram_chat_id
