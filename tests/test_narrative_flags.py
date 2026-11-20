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


def test_negation_of_findings_is_not_handled_by_design():
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


# --- radiology scales: the phrasings reports actually use -----------------------------------
@pytest.mark.parametrize(("text", "category"), [
    ("BI-RADS category 4: suspicious abnormality, biopsy should be considered", "birads"),
    ("BI-RADS IV", "birads"),
    ("BI-RADS V", "birads"),
    ("BI-RADS 4C", "birads"),
    ("BIRADS 4a", "birads"),
    ("BI-RADS® 5", "birads"),
    ("BI-RADS 6 (known biopsy-proven malignancy)", "birads"),
    ("Bi-RADS: categoría 4", "birads"),
    ("BI-RADS категорія 4", "birads"),
    ("BI-RADS 3-4", "birads"),                   # a range ending in a suspicious grade
    ("PI-RADS v2.1 score 5", "pirads"),
    ("PI-RADS 4", "pirads"),
    ("ACR TI-RADS TR5", "tirads"),
    ("TI-RADS 4b", "tirads"),
    ("EU-TIRADS 5", "tirads"),
    ("Nodule TR4, 14 mm", "tirads"),
    ("Lung-RADS 4B", "lungrads"),
    ("Lung-RADS v2022 category 4X", "lungrads"),
    ("Lung-RADS 4A", "lungrads"),
    ("Bosniak IV", "bosniak"),
    ("Bosniak category III", "bosniak"),
    ("Bosniak 3", "bosniak"),
])
def test_scale_grade_flags(text, category):
    assert category in _cats(text), text


@pytest.mark.parametrize("text", [
    "BI-RADS 0", "BI-RADS 1", "BI-RADS 2", "BI-RADS 3", "BI-RADS II", "BI-RADS III",
    "BI-RADS 3, control a 6 meses",              # a follow-up interval, not a grade
    "BI-RADS 3 a 6 meses",
    "BI-RADS 3 - 6 months follow-up",
    "ACR TI-RADS TR3", "TI-RADS TR2", "TR3",
    "PI-RADS 2", "PI-RADS v2.1 score 3", "PI-RADS v2.1: 2",
    "Lung-RADS 2", "Lung-RADS 3",
    "Bosniak II", "Bosniak IIF", "Bosniak 2F",
])
def test_benign_scale_grade_is_clean(text):
    assert not is_critical(text), text


# --- "suspicious": flags, unless plainly negated in its own clause ----------------------------
@pytest.mark.parametrize("text", [
    "Suspicious mass",
    "Suspicious microcalcifications in the upper outer quadrant",
    "Nódulo sospechoso",
    "Lesión sospechosa de malignidad",
    "Підозріле утворення",
    "Подозрительный очаг",
    # not negations, or negations of something else
    "No suspicious findings, but a suspicious nodule in the left breast",
    "No change in the suspicious lesion",
    "No se puede descartar lesión sospechosa",
    "Cannot exclude suspicious calcifications",
    "No mass. Suspicious calcifications",
    "No masses, suspicious calcifications",          # a comma ends the negation's reach
])
def test_suspicious_flags(text):
    assert "suspicion" in _cats(text), text


@pytest.mark.parametrize("text", [
    "No suspicious findings",
    "No suspicious findings. BI-RADS 1.",
    "There are no suspicious masses or calcifications",
    "No masses or suspicious calcifications",
    "No evidence of suspicious lymph nodes",
    "Without suspicious features",
    "The nodule is not suspicious",
    "Non-suspicious calcifications",
    "Sin hallazgos sospechosos",
    "No se observan lesiones sospechosas",
    "Sin adenopatías ni lesiones sospechosas",
    "Без підозрілих змін",
    "Підозрілих утворень не виявлено",
    "Без подозрительных очагов",
    "Подозрительных образований не выявлено",
])
def test_negated_suspicious_is_clean(text):
    assert not is_critical(text), text


def test_negating_suspicious_never_hides_another_finding():
    # the negation is for the bare word only: malignancy / BI-RADS still fire
    assert "malignancy" in _cats("No findings suspicious for malignancy")
    assert "birads" in _cats("No suspicious findings in the right breast. Left: BI-RADS 4")
