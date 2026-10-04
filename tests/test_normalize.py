from core.normalize import canonicalize, compute_status, normalize


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

def test_es_de_pl_lab_synonyms_canonicalize():
    from core.normalize import canonicalize
    # Spanish / German / Polish printed names for common markers
    assert canonicalize("Colesterol total") is not None
    assert canonicalize("Glucosa") is not None
    assert canonicalize("Hemoglobina") is not None
