import pytest

from core.normalize import canonicalize, compute_status, find_type, normalize


# --- pure unit tests (no DB) ---
def test_canonicalize_lowercase_trim_yo_dashes():
    assert canonicalize("  Холестерол  Загальний ") == "холестерол загальний"
    assert canonicalize("Свободный Т4") == "свободный т4"
    assert canonicalize("бета—глобулін") == "бета-глобулін"   # em-dash → hyphen


def test_compute_status_from_bank_range():
    assert compute_status(5.8, 3.0, 5.2) == "high"
    assert compute_status(2.0, 3.0, 5.2) == "low"
    assert compute_status(4.0, 3.0, 5.2) == "normal"
    assert compute_status(None, 3.0, 5.2) is None
    assert compute_status(4.0, None, None) is None


# --- integration (live seeded database) ---
def test_exact_synonym_match_ru(conn):
    nr = normalize("Холестерин общий", 5.8, "mmol/L", conn)  # ru synonym
    assert nr.type_code == "cholesterol_total"
    assert nr.synonym_origin == "seed"
    assert nr.ok


def test_unknown_name_flagged(conn):
    nr = normalize("невідомий магічний показник", 1.0, "mmol/L", conn)
    assert nr.unknown_type and not nr.ok


def test_unit_gate_blocks_missing_conversion(conn):
    # glucose in mg/dL must be converted to mmol/L
    nr = normalize("глюкоза", 95.0, "mg/dL", conn)
    assert nr.type_code == "glucose"
    assert nr.value_canonical is not None
    assert abs(nr.value_canonical - 95.0 * 0.05551) < 1e-6


def test_unit_gate_unknown_unit_blocked(conn):
    nr = normalize("глюкоза", 95.0, "папуги/л", conn)  # a nonexistent unit
    assert nr.conversion_missing and not nr.ok


def test_identity_when_already_canonical(conn):
    nr = normalize("глюкоза", 5.2, "mmol/L", conn)
    assert nr.value_canonical == 5.2


@pytest.mark.parametrize("printed,code", [
    ("Leukozyten", "leukocytes"), ("Leukocyty", "leukocytes"), ("Płytki krwi", "platelets"),
    ("Thrombozyten", "platelets"), ("Glukoza", "glucose"), ("Kreatynina", "creatinine"),
    ("Harnstoff", "urea"), ("Ferrytyna", "ferritin"), ("Gesamtcholesterin", "cholesterol_total"),
    ("Cholesterol całkowity", "cholesterol_total"), ("LDL-Cholesterin", "ldl"),
    ("HDL-Cholesterol", "hdl"), ("Triglicéridos", "triglycerides"), ("Witamina D", "vitamin_d"),
    ("Haemoglobin", "hemoglobin"), ("Hämoglobin", "hemoglobin"),
    # GOT = AST, GPT = ALT (the first version of this list had them swapped)
    ("GOT", "ast"), ("GPT", "alt"),
])
def test_es_de_pl_names_find_the_right_type(conn, printed, code):
    assert find_type(printed, conn)["code"] == code
