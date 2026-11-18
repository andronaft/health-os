"""Narrative ingestion runs the critical-narrative classifier and alerts (escalation policy)."""
from sqlalchemy import text

from ingestion.narratives import ESCALATION_NOTE, add_chunks, ingest_narrative, upsert_document
from safety import alerts


class _Fake:
    def __init__(self):
        self.calls = []

    def __call__(self, title, message):
        self.calls.append((title, message))


def test_ingest_narrative_reports_and_alerts_once(conn, user_id):
    fake = _Fake()
    out = ingest_narrative(
        conn, user_id, "/nonexistent/breast-us.pdf", doc_type="ultrasound", title="Breast US",
        document_date="2026-11-10", extracted_text="Conclusion: BI-RADS 5.",
        chunks=[{"content": "Left breast: irregular mass, highly suggestive of malignancy"},
                {"content": "Right breast: no suspicious findings"}],
        alerter=fake)
    assert out["critical"] is True and out["note"] == ESCALATION_NOTE
    assert out["chunks"] == 2
    found = {(f["where"], f["category"]) for f in out["narrative_flags"]}
    assert {("extracted_text", "birads"), ("chunk 0", "malignancy")} <= found
    assert not any(f["where"] == "chunk 1" for f in out["narrative_flags"])  # negated "suspicious"
    assert len(fake.calls) == 1                          # one alert per document, not per chunk
    title, message = fake.calls[0]
    assert title == "Health OS — critical narrative finding"
    assert "Breast US (2026-11-10)" in message and "birads" in message and "malignancy" in message
    n = conn.execute(text("SELECT count(*) FROM document_chunks WHERE document_id=:d"),
                     {"d": out["document_id"]}).scalar()
    assert n == 2


def test_ingest_narrative_clean_text_no_alert(conn, user_id):
    fake = _Fake()
    out = ingest_narrative(
        conn, user_id, "/nonexistent/liver-us.pdf", doc_type="ultrasound", title="Liver US",
        extracted_text="Liver not enlarged, homogeneous. BI-RADS 2.",
        chunks=[{"content": "No suspicious findings."}], alerter=fake)
    assert out["critical"] is False and out["narrative_flags"] == [] and "note" not in out
    assert fake.calls == []


def test_direct_calls_alert_through_the_production_channel(conn, user_id, monkeypatch):
    """upsert_document / add_chunks without an alerter use send_critical_alert — a script
    calling them directly must not store "BI-RADS 5" silently."""
    sent = []
    monkeypatch.setattr(alerts, "send_critical_alert", lambda t, m: sent.append(m))
    did = upsert_document(conn, user_id, "/nonexistent/us.pdf", doc_type="ultrasound",
                          title="Breast US", extracted_text="BI-RADS 5, malignancy")
    assert len(sent) == 1
    assert add_chunks(conn, did, [{"content": "Conclusion: BI-RADS 4C"}]) == 1
    assert len(sent) == 2 and "Breast US" in sent[1] and "birads" in sent[1]


def test_direct_calls_with_clean_text_send_nothing(conn, user_id, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_critical_alert", lambda t, m: sent.append(m))
    did = upsert_document(conn, user_id, "/nonexistent/thyroid.pdf", doc_type="ultrasound",
                          title="Thyroid US", extracted_text="ACR TI-RADS TR2")
    add_chunks(conn, did, [{"content": "Nodule 6 mm, TR3, follow-up"}])
    assert sent == []
