import pytest

from core import config
from core.config import Settings
from safety.crisis import _HOTLINES, crisis_response, is_crisis


@pytest.fixture(autouse=True)
def _default_country(monkeypatch):
    # the developer's own .env must not change what these tests see
    monkeypatch.setattr(config.settings, "crisis_country", "UA")


def test_detects_suicidal_uk_ru_en():
    assert is_crisis("я більше не хочу жити")
    assert is_crisis("думаю покінчити з собою")
    assert is_crisis("хочу умереть, нет смысла")
    assert is_crisis("I want to die")


def test_non_crisis_is_clean():
    assert not is_crisis("сьогодні болить голова і трохи втомився")
    assert not is_crisis("хочу записатись до лікаря")
    assert not is_crisis(None)


def test_response_has_hotlines_default_ua():
    r = crisis_response()
    assert "7333" in r
    assert "103" in r and "112" in r


def test_response_hotlines_by_country():
    us = crisis_response(country="US")
    assert "988" in us and "911" in us
    de = crisis_response(country="DE")
    assert "0800 111 0 111" in de and "112" in de
    pl = crisis_response(country="pl")
    assert "116 123" in pl and "800 70 2222" in pl
    assert crisis_response(country="UK") == crisis_response(country="GB")
    unknown = crisis_response(country="FR")
    assert "7333" not in unknown  # a Ukrainian short number can't be dialled from France
    assert "112" in unknown and "findahelpline.com" in unknown


def test_country_from_env_file_reaches_the_response(tmp_path, monkeypatch):
    # pydantic-settings loads .env into Settings, not os.environ — the PR first read os.getenv
    env = tmp_path / ".env"
    env.write_text("CRISIS_COUNTRY=ES\n")
    monkeypatch.delenv("CRISIS_COUNTRY", raising=False)
    s = Settings(_env_file=env)
    assert s.crisis_country == "ES"
    monkeypatch.setattr(config, "settings", s)
    r = crisis_response()
    assert "024" in r and "7333" not in r


def test_every_country_has_a_line_and_an_emergency_number():
    for code, h in _HOTLINES.items():
        assert h["label"] and h["emergency"], code
        assert any(c.isdigit() for c in h["label"]), code


def test_response_includes_trusted_contact():
    r = crisis_response(emergency_contact="Мама +380...")
    assert "Мама" in r


def test_response_has_no_analytics_language():
    r = crisis_response().lower()
    assert "trend" not in r and "metric" not in r  # no analytics during a crisis
