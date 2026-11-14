import pytest

from core import config
from core.config import Settings
from safety.crisis import _HOTLINES, _PATTERNS, _norm, crisis_response, is_crisis


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


@pytest.mark.parametrize("text", [
    # uk
    "хочу вмерти", "іноді думаю вбити себе", "вб’ю себе", "НЕ ХОЧУ ЖИТИ",
    # ru — "не хочу жить" was missed until the pattern stopped requiring "больше"
    "не хочу жить", "нет смысла жить", "хочу убить себя", "наложить на себя руки",
    "хочу свести счёты с жизнью", "Лучше бы я умер",
    # en
    "I don't want to live anymore", "I don’t want to live", "thinking about killing myself",
    "I want to take my own life", "I wish I was dead", "I want to hurt myself",
    # es — the table from issue #31 and everyday variants
    "quiero morir", "no quiero vivir más", "no quiero vivir mas", "quiero quitarme la vida",
    "me quiero matar", "no tiene sentido vivir", "autolesionarme", "pienso en suicidarme",
    "me quiero morir", "ya no quiero seguir viviendo", "voy a matarme",
    "quiero acabar con mi vida", "no vale la pena vivir", "quiero hacerme daño",
    "estaría mejor muerta",
    # de
    "ich will sterben", "Ich will nicht mehr leben", "ich bringe mich um",
    "ich denke daran, mich umzubringen", "Selbstmord", "ich will mir das Leben nehmen",
    # pl — with and without diacritics
    "chcę umrzeć", "chce umrzec", "nie chcę już żyć", "nie chce juz zyc", "zabiję się",
    "chcę się zabić", "myślę o samobójstwie", "chcę odebrać sobie życie",
])
def test_detects_crisis_phrases(text):
    assert is_crisis(text), text


@pytest.mark.parametrize("text", [
    "me duele la cabeza y quiero dormir", "quiero vivir más sano", "no quiero comer más azúcar",
    "mi abuelo murió de un infarto", "me corté el dedo cocinando",
    "ich will besser schlafen", "ich will nicht mehr rauchen", "mein Knie ist verletzt",
    "chcę żyć zdrowiej", "nie chcę już palić", "boli mnie głowa",
    "I hurt my knee running", "I don't want to take statins", "I cut my finger cooking",
    "не хочу пить таблетки", "хочу жить здоровее", "хочу краще спати",
])
def test_ordinary_messages_in_every_language_are_clean(text):
    assert not is_crisis(text), text


def test_spacing_and_line_breaks_do_not_hide_a_phrase():
    assert is_crisis("quiero   morir")
    assert is_crisis("не хочу\nжить")


def test_patterns_are_written_in_normalized_form():
    # is_crisis() matches against _norm(text), so a pattern with "ё" or a capital letter could
    # never match — "свести счёты" sat in the list that way and caught nothing
    assert _norm("Свести  счёты") == "свести счеты"
    for pattern in _PATTERNS:
        assert "ё" not in pattern and "’" not in pattern, pattern


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
