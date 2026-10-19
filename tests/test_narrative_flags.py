import pytest

from safety.narrative_flags import is_critical, scan


def _cats(text):
    return {f.category for f in scan(text)}


def test_malignancy_suspicion_uk():
    assert is_critical("Утворення правої молочної залози, підозра на малігнізацію")
    cats = _cats("підозра на малігнізацію")
    assert "malignancy" in cats and "suspicion" in cats


def test_birads_4_5():
    assert is_critical("BI-RADS 4")
    assert is_critical("bi rads 5")
    assert not is_critical("BI-RADS 2")  # 2 — not critical


def test_aneurysm():
    assert is_critical("Аневризма черевної аорти 5 см")


def test_urgent_recommendation():
    assert is_critical("Рекомендовано терміново дообстеження")
    assert is_critical("cito!")


def test_russian_variants():
    assert is_critical("подозрение на злокачественное образование")
    assert is_critical("объемное образование печени")


def test_vascular_emergency():
    assert is_critical("ознаки тромбоемболії легеневої артерії")


def test_benign_text_is_clean():
    assert not is_critical("Печінка не збільшена, структура однорідна. Патології не виявлено.")
    assert not is_critical("Щитоподібна залоза без вогнищевих змін.")


def test_empty_and_none():
    assert scan(None) == []
    assert scan("") == []


# --- Spanish (#30): reports from Spanish hospitals; accents folded, so both spellings match ---
@pytest.mark.parametrize("text", [
    "Aneurisma de aorta abdominal",
    "Trombosis venosa profunda",
    "Infarto agudo de miocardio",
    "Ictus isquémico agudo",
    "Masa sólida en riñón",
    "Nódulo sospechoso",
    "Nodulo sospechoso",                       # typed without accents
    "Lesión ocupante de espacio en hígado",
    "Neoformación pulmonar",
    "Disección aórtica tipo A",
    "Tromboembolismo pulmonar",
    "Linfoma no Hodgkin",
    "Se recomienda acudir a urgencias",
])
def test_spanish_critical_findings(text):
    assert is_critical(text), text


@pytest.mark.parametrize("text", [
    "Índice de masa corporal 24,1",
    "Densitometría: masa ósea dentro de la normalidad",
    "Masa ventricular izquierda normal",
    "Hígado de tamaño y ecoestructura normales. Sin hallazgos patológicos.",
])
def test_spanish_benign_text_is_clean(text):
    assert not is_critical(text), text


def test_negation_is_not_handled_by_design():
    # "can't be ruled out" reads like a negation and is exactly what must fire
    assert is_critical("No se puede descartar malignidad")
    assert is_critical("Sin signos de trombosis")      # high recall: a human dismisses it


def test_lymphoma_and_leukemia_in_every_language():
    for text in ("Лімфома Ходжкіна", "лимфома", "Hodgkin lymphoma", "гострий лейкоз",
                 "acute leukaemia", "Leucemia linfoide", "меланома шкіри", "Melanoma"):
        assert "malignancy" in _cats(text), text


def test_aortic_dissection_in_every_language():
    for text in ("Розшарування аорти", "расслоение аорты", "Aortic dissection",
                 "Disección de la aorta"):
        assert "acute_vascular" in _cats(text), text


def test_folding_keeps_ukrainian_letters():
    # Latin accents are folded; й/ї must survive or "негайне" stops matching
    assert "urgent" in _cats("Рекомендовано негайне звернення до лікаря")
