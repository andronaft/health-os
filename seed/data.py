"""Starter seed of marker reference data (Phase 0).

A PROVISIONAL set of ~45 markers covering a typical golden set:
CBC + biochemistry + lipid panel + thyroid + basic vitals.
Refined against real-world lab forms (Phase 0-lite → Phase 1).

observation_types format:
(code, loinc, name_uk, name_en, category, specimen, value_kind, canonical_unit, molar_mass)

Synonyms — exact match of the normalized string (see plan 4.4); languages: uk/ru/en/la.
Conversions — analyte-specific coefficients (mg/dL↔mmol/L differs for glucose vs cholesterol!).
References — each with a mandatory source; range_kind='population' if not specified.
"""
from __future__ import annotations

# ---- observation_types --------------------------------------------------------------
# category: lab / vital / body ; specimen is mandatory for lab
OBSERVATION_TYPES = [
    # --- CBC (complete blood count), specimen=whole_blood ---
    ("hemoglobin", "718-7", "Гемоглобін", "Hemoglobin", "lab", "whole_blood", "numeric", "g/L", None),
    ("erythrocytes", "789-8", "Еритроцити", "Erythrocytes (RBC)", "lab", "whole_blood", "numeric", "10*12/L", None),
    ("leukocytes", "6690-2", "Лейкоцити", "Leukocytes (WBC)", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("platelets", "777-3", "Тромбоцити", "Platelets", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("hematocrit", "4544-3", "Гематокрит", "Hematocrit", "lab", "whole_blood", "numeric", "%", None),
    ("mcv", "787-2", "Середній об'єм еритроцита (MCV)", "MCV", "lab", "whole_blood", "numeric", "fL", None),
    ("mch", "785-6", "Середній вміст гемоглобіну (MCH)", "MCH", "lab", "whole_blood", "numeric", "pg", None),
    ("mchc", "786-4", "Середня концентрація Hb (MCHC)", "MCHC", "lab", "whole_blood", "numeric", "g/L", None),
    ("esr", "4537-7", "ШОЕ", "ESR", "lab", "whole_blood", "numeric", "mm/h", None),
    ("neutrophils_pct", "770-8", "Нейтрофіли %", "Neutrophils %", "lab", "whole_blood", "numeric", "%", None),
    ("lymphocytes_pct", "736-9", "Лімфоцити %", "Lymphocytes %", "lab", "whole_blood", "numeric", "%", None),
    ("monocytes_pct", "5905-5", "Моноцити %", "Monocytes %", "lab", "whole_blood", "numeric", "%", None),
    ("eosinophils_pct", "713-8", "Еозинофіли %", "Eosinophils %", "lab", "whole_blood", "numeric", "%", None),
    ("basophils_pct", "706-2", "Базофіли %", "Basophils %", "lab", "whole_blood", "numeric", "%", None),

    # --- Biochemistry, specimen=serum ---
    ("glucose", "2345-7", "Глюкоза", "Glucose", "lab", "serum", "numeric", "mmol/L", 180.16),
    ("creatinine", "2160-0", "Креатинін", "Creatinine", "lab", "serum", "numeric", "umol/L", 113.12),
    ("urea", "3094-0", "Сечовина", "Urea", "lab", "serum", "numeric", "mmol/L", 60.06),
    ("uric_acid", "3084-1", "Сечова кислота", "Uric acid", "lab", "serum", "numeric", "umol/L", 168.11),
    ("alt", "1742-6", "АЛТ", "ALT", "lab", "serum", "numeric", "U/L", None),
    ("ast", "1920-8", "АСТ", "AST", "lab", "serum", "numeric", "U/L", None),
    ("ggt", "2324-2", "ГГТ", "GGT", "lab", "serum", "numeric", "U/L", None),
    ("alp", "6768-6", "Лужна фосфатаза", "Alkaline phosphatase", "lab", "serum", "numeric", "U/L", None),
    ("total_bilirubin", "1975-2", "Білірубін загальний", "Total bilirubin", "lab", "serum", "numeric", "umol/L", 584.66),
    ("total_protein_serum", "2885-2", "Білок загальний (сироватка)", "Total protein", "lab", "serum", "numeric", "g/L", None),
    ("albumin", "1751-7", "Альбумін", "Albumin", "lab", "serum", "numeric", "g/L", None),
    ("potassium", "2823-3", "Калій", "Potassium", "lab", "serum", "numeric", "mmol/L", None),
    ("sodium", "2951-2", "Натрій", "Sodium", "lab", "serum", "numeric", "mmol/L", None),
    ("calcium_total", "17861-6", "Кальцій загальний", "Total calcium", "lab", "serum", "numeric", "mmol/L", 40.08),
    ("crp", "1988-5", "С-реактивний білок", "C-reactive protein", "lab", "serum", "numeric", "mg/L", None),
    ("iron_serum", "2498-4", "Залізо сироватки", "Serum iron", "lab", "serum", "numeric", "umol/L", 55.85),
    ("ferritin", "2276-4", "Феритин", "Ferritin", "lab", "serum", "numeric", "ng/mL", None),

    # --- Lipid panel, specimen=serum ---
    ("cholesterol_total", "2093-3", "Холестерол загальний", "Total cholesterol", "lab", "serum", "numeric", "mmol/L", 386.65),
    ("ldl", "2089-1", "ЛПНЩ (LDL)", "LDL cholesterol", "lab", "serum", "numeric", "mmol/L", 386.65),
    ("hdl", "2085-9", "ЛПВЩ (HDL)", "HDL cholesterol", "lab", "serum", "numeric", "mmol/L", 386.65),
    ("triglycerides", "2571-8", "Тригліцериди", "Triglycerides", "lab", "serum", "numeric", "mmol/L", 885.4),

    # --- Thyroid, specimen=serum ---
    ("tsh", "3016-3", "ТТГ", "TSH", "lab", "serum", "numeric", "mIU/L", None),
    ("ft4", "3024-7", "Вільний Т4", "Free T4", "lab", "serum", "numeric", "pmol/L", None),
    ("ft3", "3051-0", "Вільний Т3", "Free T3", "lab", "serum", "numeric", "pmol/L", None),

    # --- Vitamins / metabolism ---
    ("vitamin_d", "1989-3", "Вітамін D (25-OH)", "Vitamin D 25-OH", "lab", "serum", "numeric", "ng/mL", None),
    ("vitamin_b12", "2132-9", "Вітамін B12", "Vitamin B12", "lab", "serum", "numeric", "pg/mL", None),
    ("hba1c", "4548-4", "Глікований гемоглобін (HbA1c)", "HbA1c", "lab", "whole_blood", "numeric", "%", None),

    # --- Vitals / anthropometry ---
    ("systolic_bp", "8480-6", "Систолічний тиск", "Systolic BP", "vital", None, "numeric", "mmHg", None),
    ("diastolic_bp", "8462-4", "Діастолічний тиск", "Diastolic BP", "vital", None, "numeric", "mmHg", None),
    ("heart_rate", "8867-4", "Пульс", "Heart rate", "vital", None, "numeric", "bpm", None),
    ("body_temp", "8310-5", "Температура тіла", "Body temperature", "vital", None, "numeric", "Cel", None),
    ("spo2", "59408-5", "Сатурація кисню (SpO2)", "SpO2", "vital", None, "numeric", "%", None),
    ("body_weight", "29463-7", "Вага", "Body weight", "body", None, "numeric", "kg", None),
    ("body_height", "8302-2", "Зріст", "Body height", "body", None, "numeric", "cm", None),

    # ============================================================================
    # Extension (2026-07-16): immunology, serology,
    # extended biochemistry. canonical_unit matches the printed unit on the form →
    # the unit-gate passes without a separate conversion; indices/titers have canonical_unit=None.
    # ============================================================================

    # --- Differential white count in absolute numbers (specimen=whole_blood) ---
    ("neutrophils_abs", "751-8", "Нейтрофіли (абс.)", "Neutrophils absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("lymphocytes_abs", "731-0", "Лімфоцити (абс.)", "Lymphocytes absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("monocytes_abs", "742-7", "Моноцити (абс.)", "Monocytes absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("eosinophils_abs", "711-2", "Еозинофіли (абс.)", "Eosinophils absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("basophils_abs", "704-7", "Базофіли (абс.)", "Basophils absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("reticulocytes", "17849-1", "Ретикулоцити", "Reticulocytes", "lab", "whole_blood", "numeric", "%", None),

    # --- Lymphocyte subpopulations (immunophenotyping), specimen=whole_blood ---
    ("cd3_pct", "8122-4", "CD3+ Т-лімфоцити, %", "CD3+ T-lymphocytes %", "lab", "whole_blood", "numeric", "%", None),
    ("cd3_abs", "8124-0", "CD3+ Т-лімфоцити (абс.)", "CD3+ absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("cd4_pct", "8123-2", "CD4+ Т-хелпери, %", "CD4+ T-helpers %", "lab", "whole_blood", "numeric", "%", None),
    ("cd4_abs", "24467-3", "CD4+ Т-хелпери (абс.)", "CD4+ absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("cd8_pct", "8102-6", "CD8+ Т-цитотоксичні, %", "CD8+ T-cytotoxic %", "lab", "whole_blood", "numeric", "%", None),
    ("cd8_abs", "14135-8", "CD8+ Т-цитотоксичні (абс.)", "CD8+ absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("cd4_cd8_ratio", "54218-3", "Імунорегуляторний індекс CD4/CD8", "CD4/CD8 ratio", "lab", "whole_blood", "numeric", None, None),
    ("cd19_pct", "8117-4", "CD19+ B-лімфоцити, %", "CD19+ B-lymphocytes %", "lab", "whole_blood", "numeric", "%", None),
    ("cd19_abs", "8119-0", "CD19+ B-лімфоцити (абс.)", "CD19+ absolute", "lab", "whole_blood", "numeric", "10*9/L", None),
    ("cd16_56_pct", "10538-9", "CD16+CD56+ NK-клітини, %", "NK cells %", "lab", "whole_blood", "numeric", "%", None),
    ("cd16_56_abs", "30450-1", "CD16+CD56+ NK-клітини (абс.)", "NK cells absolute", "lab", "whole_blood", "numeric", "10*9/L", None),

    # --- Immunoglobulins and complement, specimen=serum ---
    ("igg", "2465-3", "IgG", "Immunoglobulin G", "lab", "serum", "numeric", "g/L", None),
    ("iga", "2458-8", "IgA", "Immunoglobulin A", "lab", "serum", "numeric", "g/L", None),
    ("igm", "2472-9", "IgM", "Immunoglobulin M", "lab", "serum", "numeric", "g/L", None),
    ("ige_total", "19113-0", "IgE загальний", "Immunoglobulin E total", "lab", "serum", "numeric", "IU/mL", None),
    ("complement_c3", "4485-9", "Комплемент C3", "Complement C3", "lab", "serum", "numeric", "g/L", None),
    ("complement_c4", "4498-2", "Комплемент C4", "Complement C4", "lab", "serum", "numeric", "g/L", None),
    ("cic", "45106-8", "Циркулюючі імунні комплекси (ЦІК)", "Circulating immune complexes", "lab", "serum", "numeric", None, None),

    # --- Infection serology (index/titer — canonical_unit=None), specimen=serum ---
    ("ebv_vca_igg", "30076-4", "EBV VCA IgG", "EBV VCA IgG", "lab", "serum", "numeric", None, None),
    ("ebv_vca_igm", "30075-6", "EBV VCA IgM", "EBV VCA IgM", "lab", "serum", "numeric", None, None),
    ("ebv_ebna_igg", "30083-0", "EBV EBNA IgG", "EBV EBNA IgG", "lab", "serum", "numeric", None, None),
    ("cmv_igg", "22239-8", "CMV IgG", "CMV IgG", "lab", "serum", "numeric", None, None),
    ("cmv_igm", "30325-5", "CMV IgM", "CMV IgM", "lab", "serum", "numeric", None, None),
    ("hhv6_igg", "40971-1", "HHV-6 IgG", "HHV-6 IgG", "lab", "serum", "numeric", None, None),

    # --- Rheumatic panel / inflammation, specimen=serum ---
    ("aso", "5364-5", "Антистрептолізин-О (АСЛО)", "Antistreptolysin O", "lab", "serum", "numeric", "IU/mL", None),
    ("rf", "11572-5", "Ревматоїдний фактор", "Rheumatoid factor", "lab", "serum", "numeric", "IU/mL", None),

    # --- Extended biochemistry / trace elements / hormones, specimen=serum ---
    ("folate", "2284-8", "Фолієва кислота (фолати)", "Folate", "lab", "serum", "numeric", "ng/mL", None),
    ("zinc", "5763-8", "Цинк", "Zinc", "lab", "serum", "numeric", "umol/L", None),
    ("erythropoietin", "14743-9", "Еритропоетин", "Erythropoietin", "lab", "serum", "numeric", "mIU/mL", None),
    ("phosphorus", "2777-1", "Фосфор", "Phosphorus", "lab", "serum", "numeric", "mmol/L", None),
    ("magnesium", "2601-3", "Магній", "Magnesium", "lab", "serum", "numeric", "mmol/L", None),
    ("ldh", "2532-0", "ЛДГ", "Lactate dehydrogenase", "lab", "serum", "numeric", "U/L", None),
    ("ck", "2157-6", "Креатинфосфокіназа (КФК)", "Creatine kinase", "lab", "serum", "numeric", "U/L", None),
    ("amylase", "1798-8", "Амілаза", "Amylase", "lab", "serum", "numeric", "U/L", None),

    # --- Protein fractions (electrophoresis), specimen=serum ---
    ("globulin_total", "10834-0", "Глобуліни", "Globulins", "lab", "serum", "numeric", "g/L", None),

    # === Wearable / Garmin daily metrics (2026-07-16), category='wearable', specimen=None ===
    ("resting_hr", "40443-4", "Пульс у спокої", "Resting heart rate", "wearable", None, "numeric", "bpm", None),
    ("hrv", "80404-7", "Варіабельність серцевого ритму (HRV)", "Heart rate variability", "wearable", None, "numeric", "ms", None),
    ("stress_avg", None, "Середній рівень стресу (Garmin)", "Average stress level", "wearable", None, "numeric", "score", None),
    ("body_battery_high", None, "Body Battery (макс за день)", "Body Battery high", "wearable", None, "numeric", "score", None),
    ("body_battery_low", None, "Body Battery (мін за день)", "Body Battery low", "wearable", None, "numeric", "score", None),
    ("respiration_avg", "9279-1", "Частота дихання (середня)", "Respiration rate avg", "wearable", None, "numeric", "brpm", None),
    ("vo2max", None, "VO2max", "VO2max", "wearable", None, "numeric", "mL/kg/min", None),
    ("sleep_duration", "93832-4", "Тривалість сну", "Sleep duration", "wearable", None, "numeric", "h", None),
    ("sleep_score", None, "Оцінка сну (Garmin)", "Sleep score", "wearable", None, "numeric", "score", None),
    ("sleep_deep", None, "Глибокий сон", "Deep sleep", "wearable", None, "numeric", "h", None),
    ("sleep_rem", None, "REM-сон", "REM sleep", "wearable", None, "numeric", "h", None),
    ("intensity_minutes", None, "Хвилини інтенсивності", "Intensity minutes", "wearable", None, "numeric", "min", None),
    ("active_calories", "41981-2", "Активні калорії", "Active calories", "wearable", None, "numeric", "kcal", None),
]

# ---- synonyms: code -> [(synonym, lang)] --------------------------------------------
# Half of Ukrainian forms before ~2022 were in Russian; so ru is mandatory.
SYNONYMS = {
    "hemoglobin": [("гемоглобін", "uk"), ("гемоглобин", "ru"), ("hemoglobin", "en"), ("hb", "en"), ("hgb", "en"), ("hgb", "la"), ("hemoglobina", "es"), ("hemoglobina", "pl"), ("haemoglobin", "de"), ("hb", "de") ],
    "erythrocytes": [("еритроцити", "uk"), ("эритроциты", "ru"), ("rbc", "en"), ("erythrocytes", "en")],
    "leukocytes": [("лейкоцити", "uk"), ("лейкоциты", "ru"), ("wbc", "en"), ("leukocytes", "en"), ("leucocitos", "es"), ("leukozyten", "de"), ("leukocyty", "pl") ],
    "platelets": [("тромбоцити", "uk"), ("тромбоциты", "ru"), ("plt", "en"), ("platelets", "en"), ("plaquetas", "es"), ("plaquetas", "pl"), ("thrombozyten", "de"), ("płytki krwi", "pl") ],
    "hematocrit": [("гематокрит", "uk"), ("гематокрит", "ru"), ("hct", "en"), ("hematocrit", "en")],
    "mcv": [("mcv", "en"), ("середній об'єм еритроцита", "uk")],
    "mch": [("mch", "en")],
    "mchc": [("mchc", "en")],
    "esr": [("шое", "uk"), ("соэ", "ru"), ("esr", "en")],
    "neutrophils_pct": [("нейтрофіли", "uk"), ("нейтрофилы", "ru"), ("neutrophils", "en")],
    "lymphocytes_pct": [("лімфоцити", "uk"), ("лимфоциты", "ru"), ("lymphocytes", "en")],
    "monocytes_pct": [("моноцити", "uk"), ("моноциты", "ru"), ("monocytes", "en")],
    "eosinophils_pct": [("еозинофіли", "uk"), ("эозинофилы", "ru"), ("eosinophils", "en")],
    "basophils_pct": [("базофіли", "uk"), ("базофилы", "ru"), ("basophils", "en")],
    "glucose": [("глюкоза", "uk"), ("глюкоза", "ru"), ("glucose", "en"), ("глюкоза крові", "uk"), ("glucosa", "es"), ("glu", "en"), ("glucosa", "es"), ("glukose", "de"), ("glukoza", "pl") ],
    "creatinine": [("креатинін", "uk"), ("креатинин", "ru"), ("creatinine", "en"), ("creatinina", "es"), ("kreatinin", "de"), ("kreatynina", "pl") ],
    "urea": [("сечовина", "uk"), ("мочевина", "ru"), ("urea", "en"), ("urea", "es"), ("harnstoff", "de"), ("mocznik", "pl") ],
    "uric_acid": [("сечова кислота", "uk"), ("мочевая кислота", "ru"), ("uric acid", "en")],
    "alt": [("алт", "uk"), ("алт", "ru"), ("alat", "en"), ("alt", "en"), ("аланінамінотрансфераза", "uk"), ("alt", "es"), ("got", "de"), ("alt", "pl") ],
    "ast": [("аст", "uk"), ("аст", "ru"), ("asat", "en"), ("ast", "en"), ("аспартатамінотрансфераза", "uk"), ("ast", "es"), ("gpt", "de"), ("ast", "pl") ],
    "ggt": [("ггт", "uk"), ("ггт", "ru"), ("ggt", "en"), ("гамма-гт", "uk")],
    "alp": [("лужна фосфатаза", "uk"), ("щелочная фосфатаза", "ru"), ("alp", "en"), ("alkaline phosphatase", "en")],
    "total_bilirubin": [("білірубін загальний", "uk"), ("билирубин общий", "ru"), ("total bilirubin", "en")],
    "total_protein_serum": [("білок загальний", "uk"), ("общий белок", "ru"), ("total protein", "en")],
    "albumin": [("альбумін", "uk"), ("альбумин", "ru"), ("albumin", "en")],
    "potassium": [("калій", "uk"), ("калий", "ru"), ("potassium", "en"), ("k+", "la"), ("k", "la"), ("potasio", "es")],
    "sodium": [("натрій", "uk"), ("натрий", "ru"), ("sodium", "en"), ("na+", "la"), ("sodio", "es")],
    "calcium_total": [("кальцій", "uk"), ("кальций", "ru"), ("calcium", "en"), ("ca", "la"), ("calcio", "es")],
    "crp": [("с-реактивний білок", "uk"), ("с-реактивный белок", "ru"), ("crp", "en"), ("срб", "ru")],
    "iron_serum": [("залізо", "uk"), ("железо", "ru"), ("iron", "en"), ("fe", "la")],
    "ferritin": [("феритин", "uk"), ("ферритин", "ru"), ("ferritin", "en"), ("ferritina", "es"), ("ferritin", "de"), ("ferrytyna", "pl") ],
    "cholesterol_total": [("холестерол загальний", "uk"), ("холестерин общий", "ru"), ("total cholesterol", "en"), ("chol", "en"), ("холестерин", "ru"), ("colesterol total", "es"), ("gesamtcholesterin", "de"), ("cholesterol całkowity", "pl") ],
    "ldl": [("лпнщ", "uk"), ("лпнп", "ru"), ("ldl", "en"), ("холестерин лпнп", "ru"), ("ldl colesterol", "es"), ("ldl-cholesterin", "de"), ("ldl-cholesterol", "pl") ],
    "hdl": [("лпвщ", "uk"), ("лпвп", "ru"), ("hdl", "en"), ("холестерин лпвп", "ru"), ("hdl colesterol", "es"), ("hdl-cholesterin", "de"), ("hdl-cholesterol", "pl") ],
    "triglycerides": [("тригліцериди", "uk"), ("триглицериды", "ru"), ("triglycerides", "en"), ("tg", "en"), ("trigliceridos", "es"), ("triglyceride", "de"), ("triglicerydy", "pl") ],
    "tsh": [("ттг", "uk"), ("ттг", "ru"), ("tsh", "en"), ("тиреотропний гормон", "uk"), ("tsh", "es"), ("tsh", "de"), ("tsh", "pl") ],
    "ft4": [("вільний т4", "uk"), ("свободный т4", "ru"), ("ft4", "en"), ("free t4", "en")],
    "ft3": [("вільний т3", "uk"), ("свободный т3", "ru"), ("ft3", "en"), ("free t3", "en")],
    "vitamin_d": [("вітамін d", "uk"), ("витамин d", "ru"), ("vitamin d", "en"), ("25-oh", "en"), ("25(oh)d", "en"), ("vitamina d", "es"), ("vitamin d", "de"), ("witamina d", "pl") ],
    "vitamin_b12": [("вітамін b12", "uk"), ("витамин b12", "ru"), ("vitamin b12", "en"), ("кобаламін", "uk")],
    "hba1c": [("глікований гемоглобін", "uk"), ("гликированный гемоглобин", "ru"), ("hba1c", "en"), ("a1c", "en"), ("hba1c", "es"), ("hba1c", "de"), ("hba1c", "pl") ],
    "systolic_bp": [("систолічний тиск", "uk"), ("систолическое давление", "ru"), ("systolic", "en"), ("сад", "uk")],
    "diastolic_bp": [("діастолічний тиск", "uk"), ("диастолическое давление", "ru"), ("diastolic", "en"), ("дад", "uk")],
    "heart_rate": [("пульс", "uk"), ("пульс", "ru"), ("heart rate", "en"), ("чсс", "uk"), ("hr", "en")],
    "body_temp": [("температура", "uk"), ("температура", "ru"), ("temperature", "en")],
    "spo2": [("сатурація", "uk"), ("сатурация", "ru"), ("spo2", "en"), ("сатурація кисню", "uk")],
    "body_weight": [("вага", "uk"), ("вес", "ru"), ("weight", "en"), ("маса тіла", "uk")],
    "body_height": [("зріст", "uk"), ("рост", "ru"), ("height", "en")],

    # --- extension 2026-07-16 ---
    "neutrophils_abs": [("нейтрофіли абс", "uk"), ("нейтрофіли абс.", "uk"), ("нейтрофилы абс", "ru"), ("нейтрофіли, абс", "uk"), ("neut#", "en"), ("neutrophils#", "en")],
    "lymphocytes_abs": [("лімфоцити абс", "uk"), ("лімфоцити абс.", "uk"), ("лимфоциты абс", "ru"), ("лімфоцити, абс", "uk"), ("lymph#", "en"), ("lymphocytes#", "en")],
    "monocytes_abs": [("моноцити абс", "uk"), ("моноцити абс.", "uk"), ("моноциты абс", "ru"), ("mon#", "en")],
    "eosinophils_abs": [("еозинофіли абс", "uk"), ("еозинофіли абс.", "uk"), ("эозинофилы абс", "ru"), ("eos#", "en")],
    "basophils_abs": [("базофіли абс", "uk"), ("базофіли абс.", "uk"), ("базофилы абс", "ru"), ("bas#", "en")],
    "reticulocytes": [("ретикулоцити", "uk"), ("ретикулоциты", "ru"), ("reticulocytes", "en"), ("ret", "en")],
    "cd3_pct": [("cd3+", "en"), ("cd3", "en"), ("т-лімфоцити cd3", "uk"), ("т-лимфоциты cd3", "ru"), ("cd3+ %", "en"), ("cd3, %", "en")],
    "cd3_abs": [("cd3+ абс", "en"), ("cd3 абс", "en"), ("cd3+ (абс.)", "en"), ("cd3 abs", "en")],
    "cd4_pct": [("cd4+", "en"), ("cd4", "en"), ("т-хелпери cd4", "uk"), ("т-хелперы cd4", "ru"), ("cd4+ %", "en"), ("cd4, %", "en")],
    "cd4_abs": [("cd4+ абс", "en"), ("cd4 абс", "en"), ("cd4+ (абс.)", "en"), ("cd4 abs", "en")],
    "cd8_pct": [("cd8+", "en"), ("cd8", "en"), ("т-цитотоксичні cd8", "uk"), ("cd8+ %", "en"), ("cd8, %", "en")],
    "cd8_abs": [("cd8+ абс", "en"), ("cd8 абс", "en"), ("cd8+ (абс.)", "en"), ("cd8 abs", "en")],
    "cd4_cd8_ratio": [("cd4/cd8", "en"), ("імунорегуляторний індекс", "uk"), ("иммунорегуляторный индекс", "ru"), ("ірі", "uk"), ("cd4/cd8 ratio", "en"), ("індекс cd4/cd8", "uk")],
    "cd19_pct": [("cd19+", "en"), ("cd19", "en"), ("в-лімфоцити cd19", "uk"), ("cd19+ %", "en"), ("cd19, %", "en")],
    "cd19_abs": [("cd19+ абс", "en"), ("cd19 абс", "en"), ("cd19+ (абс.)", "en"), ("cd19 abs", "en")],
    "cd16_56_pct": [("cd16+cd56+", "en"), ("cd16/56", "en"), ("nk-клітини", "uk"), ("nk клетки", "ru"), ("cd16+56+", "en"), ("cd16+cd56+ %", "en"), ("nk", "en")],
    "cd16_56_abs": [("cd16+cd56+ абс", "en"), ("nk-клітини абс", "uk"), ("cd16+56+ абс", "en")],
    "igg": [("igg", "en"), ("ig g", "en"), ("імуноглобулін g", "uk"), ("иммуноглобулин g", "ru"), ("ідg", "uk")],
    "iga": [("iga", "en"), ("ig a", "en"), ("імуноглобулін a", "uk"), ("иммуноглобулин a", "ru")],
    "igm": [("igm", "en"), ("ig m", "en"), ("імуноглобулін m", "uk"), ("иммуноглобулин m", "ru")],
    "ige_total": [("ige", "en"), ("ig e", "en"), ("ige загальний", "uk"), ("імуноглобулін e", "uk"), ("иммуноглобулин e", "ru"), ("ige total", "en")],
    "complement_c3": [("c3", "en"), ("комплемент c3", "uk"), ("комплемент c3", "ru"), ("с3", "uk"), ("компонент комплементу c3", "uk")],
    "complement_c4": [("c4", "en"), ("комплемент c4", "uk"), ("комплемент c4", "ru"), ("с4", "uk"), ("компонент комплементу c4", "uk")],
    "cic": [("цік", "uk"), ("цик", "ru"), ("циркулюючі імунні комплекси", "uk"), ("циркулирующие иммунные комплексы", "ru"), ("cic", "en")],
    "ebv_vca_igg": [("ebv vca igg", "en"), ("вeб vca igg", "uk"), ("ebv-vca igg", "en"), ("epstein-barr vca igg", "en"), ("віл-vca", "uk")],
    "ebv_vca_igm": [("ebv vca igm", "en"), ("ebv-vca igm", "en"), ("epstein-barr vca igm", "en")],
    "ebv_ebna_igg": [("ebv ebna igg", "en"), ("ebv-ebna igg", "en"), ("ebna igg", "en"), ("epstein-barr ebna igg", "en")],
    "cmv_igg": [("cmv igg", "en"), ("цмв igg", "uk"), ("цитомегаловірус igg", "uk"), ("цитомегаловирус igg", "ru")],
    "cmv_igm": [("cmv igm", "en"), ("цмв igm", "uk"), ("цитомегаловірус igm", "uk"), ("цитомегаловирус igm", "ru")],
    "hhv6_igg": [("hhv-6 igg", "en"), ("hhv6 igg", "en"), ("вгл-6 igg", "uk"), ("вгч-6 igg", "ru"), ("герпес 6 типу igg", "uk")],
    "aso": [("асло", "uk"), ("асло", "ru"), ("aso", "en"), ("antistreptolysin o", "en"), ("антистрептолізин-о", "uk"), ("антистрептолизин-о", "ru")],
    "rf": [("рф", "uk"), ("ревматоїдний фактор", "uk"), ("ревматоидный фактор", "ru"), ("rf", "en"), ("rheumatoid factor", "en"), ("ревмофактор", "uk")],
    "folate": [("фолієва кислота", "uk"), ("фолиевая кислота", "ru"), ("фолати", "uk"), ("folate", "en"), ("folic acid", "en"), ("вітамін b9", "uk")],
    "zinc": [("цинк", "uk"), ("цинк", "ru"), ("zinc", "en"), ("zn", "la")],
    "erythropoietin": [("еритропоетин", "uk"), ("эритропоэтин", "ru"), ("erythropoietin", "en"), ("epo", "en")],
    "phosphorus": [("фосфор", "uk"), ("фосфор", "ru"), ("phosphorus", "en"), ("фосфор неорганічний", "uk"), ("p", "la")],
    "magnesium": [("магній", "uk"), ("магний", "ru"), ("magnesium", "en"), ("mg", "la")],
    "ldh": [("лдг", "uk"), ("лдг", "ru"), ("ldh", "en"), ("лактатдегідрогеназа", "uk"), ("лактатдегидрогеназа", "ru")],
    "ck": [("кфк", "uk"), ("кфк", "ru"), ("креатинфосфокіназа", "uk"), ("креатинфосфокиназа", "ru"), ("ck", "en"), ("cpk", "en")],
    "amylase": [("амілаза", "uk"), ("амилаза", "ru"), ("amylase", "en"), ("альфа-амілаза", "uk")],
    "globulin_total": [("глобуліни", "uk"), ("глобулины", "ru"), ("globulins", "en"), ("глобулін загальний", "uk")],
}

# ---- unit_conversions: (type_code|None, from_unit, to_unit, factor, add_offset) ------
# type_code=None → universal conversion. Analyte-specific ones — with a type_code.
UNIT_CONVERSIONS = [
    # universal. Formula: canonical = value * factor + add_offset
    (None, "degF", "Cel", 0.555556, -17.777778),  # (F-32)*5/9 = F*5/9 - 17.78
    (None, "g", "kg", 0.001, 0.0),
    (None, "uIU/mL", "mIU/L", 1.0, 0.0),   # мкМО/мл = mIU/L (TSH on Ukrainian forms)
    (None, "ug/L", "ng/mL", 1.0, 0.0),
    # cell counts as printed on ES/US forms: 1/µL = 10^6/L; 10^3/µL = 10^9/L; 10^6/µL = 10^12/L
    (None, "/uL", "10*9/L", 0.001, 0.0),
    (None, "10*3/uL", "10*9/L", 1.0, 0.0),
    (None, "10*6/uL", "10*12/L", 1.0, 0.0),
    # analytes with critical thresholds — every common printed unit must convert, otherwise
    # the unit gate would silently skip the critical check
    ("potassium", "mEq/L", "mmol/L", 1.0, 0.0),      # monovalent: 1 mEq = 1 mmol
    ("sodium", "mEq/L", "mmol/L", 1.0, 0.0),
    ("calcium_total", "mEq/L", "mmol/L", 0.5, 0.0),  # divalent
    ("hemoglobin", "g/dL", "g/L", 10.0, 0.0),
    (None, "kg", "g", 1000.0, 0.0),
    # glucose mg/dL → mmol/L
    ("glucose", "mg/dL", "mmol/L", 0.05551, 0.0),
    # cholesterol and fractions mg/dL → mmol/L (0.02586)
    ("cholesterol_total", "mg/dL", "mmol/L", 0.02586, 0.0),
    ("ldl", "mg/dL", "mmol/L", 0.02586, 0.0),
    ("hdl", "mg/dL", "mmol/L", 0.02586, 0.0),
    # triglycerides mg/dL → mmol/L (0.01129)
    ("triglycerides", "mg/dL", "mmol/L", 0.01129, 0.0),
    # creatinine mg/dL → µmol/L (88.42)
    ("creatinine", "mg/dL", "umol/L", 88.42, 0.0),
    # uric acid mg/dL → µmol/L (59.48)
    ("uric_acid", "mg/dL", "umol/L", 59.48, 0.0),
    # calcium mg/dL → mmol/L (0.2495)
    ("calcium_total", "mg/dL", "mmol/L", 0.2495, 0.0),
    # total bilirubin mg/dL → µmol/L (17.1)
    ("total_bilirubin", "mg/dL", "umol/L", 17.1, 0.0),
]

# ---- reference_ranges: dict with a mandatory source ----------------------------------
# range_kind: population (default) / target / optimal. LDL — target (not a population norm!).
REFERENCE_RANGES = [
    {"code": "hemoglobin", "sex": "male", "unit": "g/L", "range_min": 130, "range_max": 170, "source": "WHO / лаб. консенсус"},
    {"code": "hemoglobin", "sex": "female", "unit": "g/L", "range_min": 120, "range_max": 155, "source": "WHO / лаб. консенсус"},
    {"code": "glucose", "unit": "mmol/L", "condition": "fasting", "range_min": 3.9, "range_max": 5.5, "source": "ADA 2023 (натще)"},
    {"code": "creatinine", "sex": "male", "unit": "umol/L", "range_min": 62, "range_max": 106, "source": "лаб. консенсус"},
    {"code": "creatinine", "sex": "female", "unit": "umol/L", "range_min": 44, "range_max": 80, "source": "лаб. консенсус"},
    {"code": "alt", "unit": "U/L", "range_min": 0, "range_max": 41, "source": "лаб. консенсус"},
    {"code": "ast", "unit": "U/L", "range_min": 0, "range_max": 40, "source": "лаб. консенсус"},
    {"code": "cholesterol_total", "unit": "mmol/L", "range_min": 0, "range_max": 5.2, "source": "лаб. консенсус (популяційний)"},
    {"code": "ldl", "unit": "mmol/L", "range_kind": "target", "range_max": 3.0, "source": "ESC 2021 (таргет залежить від CV-ризику)"},
    {"code": "hdl", "sex": "male", "unit": "mmol/L", "range_min": 1.0, "range_max": None, "source": "ESC 2021"},
    {"code": "triglycerides", "unit": "mmol/L", "range_min": 0, "range_max": 1.7, "source": "ESC 2021"},
    {"code": "tsh", "unit": "mIU/L", "range_min": 0.4, "range_max": 4.0, "source": "лаб. консенсус"},
    {"code": "potassium", "unit": "mmol/L", "range_min": 3.5, "range_max": 5.1, "source": "лаб. консенсус"},
    {"code": "sodium", "unit": "mmol/L", "range_min": 136, "range_max": 145, "source": "лаб. консенсус"},
    {"code": "hba1c", "unit": "%", "range_min": 0, "range_max": 5.7, "source": "ADA 2023 (норма < 5.7)"},
    {"code": "vitamin_d", "unit": "ng/mL", "range_kind": "optimal", "optimal_min": 30, "optimal_max": 50, "source": "Endocrine Society (достатність ≥30)"},
    # --- extension 2026-07-16: immunology / extended biochemistry ---
    {"code": "igg", "unit": "g/L", "range_min": 7.0, "range_max": 16.0, "source": "лаб. консенсус (дорослі)"},
    {"code": "iga", "unit": "g/L", "range_min": 0.7, "range_max": 4.0, "source": "лаб. консенсус (дорослі)"},
    {"code": "igm", "unit": "g/L", "range_min": 0.4, "range_max": 2.3, "source": "лаб. консенсус (дорослі)"},
    {"code": "ige_total", "unit": "IU/mL", "range_min": 0, "range_max": 100, "source": "лаб. консенсус (дорослі)"},
    {"code": "complement_c3", "unit": "g/L", "range_min": 0.9, "range_max": 1.8, "source": "лаб. консенсус"},
    {"code": "complement_c4", "unit": "g/L", "range_min": 0.1, "range_max": 0.4, "source": "лаб. консенсус"},
    {"code": "cd3_pct", "unit": "%", "range_min": 55, "range_max": 80, "source": "лаб. консенсус (дорослі)"},
    {"code": "cd4_pct", "unit": "%", "range_min": 31, "range_max": 49, "source": "лаб. консенсус (дорослі)"},
    {"code": "cd8_pct", "unit": "%", "range_min": 19, "range_max": 37, "source": "лаб. консенсус (дорослі)"},
    {"code": "cd4_cd8_ratio", "unit": "ratio", "range_min": 1.0, "range_max": 2.5, "source": "лаб. консенсус"},
    {"code": "cd19_pct", "unit": "%", "range_min": 5, "range_max": 19, "source": "лаб. консенсус (дорослі)"},
    {"code": "cd16_56_pct", "unit": "%", "range_min": 6, "range_max": 27, "source": "лаб. консенсус (дорослі)"},
    {"code": "folate", "unit": "ng/mL", "range_min": 3.1, "range_max": 20.5, "source": "лаб. консенсус"},
    {"code": "zinc", "unit": "umol/L", "range_min": 11, "range_max": 18, "source": "лаб. консенсус"},
    {"code": "erythropoietin", "unit": "mIU/mL", "range_min": 4.3, "range_max": 29, "source": "лаб. консенсус"},
    {"code": "phosphorus", "unit": "mmol/L", "range_min": 0.87, "range_max": 1.45, "source": "лаб. консенсус"},
    {"code": "magnesium", "unit": "mmol/L", "range_min": 0.66, "range_max": 1.07, "source": "лаб. консенсус"},
    {"code": "aso", "unit": "IU/mL", "range_min": 0, "range_max": 200, "source": "лаб. консенсус"},
    {"code": "rf", "unit": "IU/mL", "range_min": 0, "range_max": 14, "source": "лаб. консенсус"},
]

# ---- qualitative_values: canonical -> (ordinal_rank, [(synonym, lang)]) --------------
QUALITATIVE = {
    "negative": (0, [("негативний", "uk"), ("негатив", "uk"), ("негат.", "uk"),
                     ("не виявлено", "uk"), ("отрицательный", "ru"), ("отриц.", "ru"),
                     ("не обнаружено", "ru"), ("negative", "en"), ("neg", "en"), ("not detected", "en")]),
    "trace": (1, [("сліди", "uk"), ("следы", "ru"), ("trace", "en")]),
    "weakly_positive": (2, [("слабопозитивний", "uk"), ("слабоположительный", "ru"),
                            ("weakly positive", "en")]),
    "positive": (3, [("позитивний", "uk"), ("позитив", "uk"), ("виявлено", "uk"),
                     ("положительный", "ru"), ("обнаружено", "ru"), ("positive", "en"),
                     ("pos", "en"), ("detected", "en")]),
}

# ---- critical_thresholds: (code, sex, unit, low, high, message, source) --------------
# Standard critical values of lab medicine; doctor review — open question #7 of the plan.
CRITICAL_THRESHOLDS = [
    ("potassium", None, "mmol/L", 2.8, 6.0, "Критичний калій — потребує звернення до лікаря сьогодні, незалежно від можливої помилки розпізнавання.", "стандартні critical values"),
    ("glucose", None, "mmol/L", 3.0, 25.0, "Критична глюкоза — негайно звернутись по допомогу.", "стандартні critical values"),
    ("hemoglobin", None, "g/L", 70.0, None, "Критично низький гемоглобін — звернутись до лікаря сьогодні.", "стандартні critical values"),
    ("platelets", None, "10*9/L", 30.0, None, "Критично низькі тромбоцити — ризик кровотечі, звернутись до лікаря.", "стандартні critical values"),
    ("sodium", None, "mmol/L", 120.0, 160.0, "Критичний натрій — потребує медичної оцінки.", "стандартні critical values"),
    ("calcium_total", None, "mmol/L", 1.6, 3.5, "Критичний кальцій — потребує медичної оцінки.", "стандартні critical values"),
]

# ---- nutrient_types (food log) -------------------------------------------------------
# (code, name_uk, name_en, unit, category, rda, upper_limit, sort_order)
# rda/upper_limit — adult male 19-50 (DRI + FDA Daily Value). Estimate source — the model;
# the schema is source-agnostic (ready for USDA). None where there's no norm/limit.
NUTRIENT_TYPES = [
    # --- energy / macro ---
    ("energy_kcal", "Калорії", "Energy", "kcal", "energy", 2500, None, 10),
    ("protein", "Білки", "Protein", "g", "macro", 56, None, 20),
    ("carbs", "Вуглеводи", "Carbohydrates", "g", "macro", 275, None, 30),
    ("sugar", "Цукор", "Sugar", "g", "macro", 50, 50, 40),
    ("added_sugar", "Доданий цукор", "Added sugar", "g", "macro", 50, 50, 45),
    ("fiber", "Клітковина", "Fiber", "g", "macro", 30, None, 50),
    ("fat", "Жири", "Total fat", "g", "macro", 78, None, 60),
    # --- fats ---
    ("saturated_fat", "Насичені жири", "Saturated fat", "g", "fat", 20, 20, 70),
    ("mono_fat", "Мононенасичені жири", "Monounsaturated fat", "g", "fat", None, None, 80),
    ("poly_fat", "Поліненасичені жири", "Polyunsaturated fat", "g", "fat", None, None, 90),
    ("trans_fat", "Транс-жири", "Trans fat", "g", "fat", None, 2, 100),
    ("cholesterol", "Холестерин", "Cholesterol", "mg", "fat", 300, 300, 110),
    ("omega3", "Омега-3", "Omega-3", "g", "fat", 1.6, None, 120),
    ("omega6", "Омега-6", "Omega-6", "g", "fat", 17, None, 130),
    # --- minerals ---
    ("sodium", "Натрій", "Sodium", "mg", "mineral", 2300, 2300, 140),
    ("potassium", "Калій", "Potassium", "mg", "mineral", 3400, None, 150),
    ("calcium", "Кальцій", "Calcium", "mg", "mineral", 1000, 2500, 160),
    ("iron", "Залізо", "Iron", "mg", "mineral", 8, 45, 170),
    ("magnesium", "Магній", "Magnesium", "mg", "mineral", 420, None, 180),
    ("zinc", "Цинк", "Zinc", "mg", "mineral", 11, 40, 190),
    ("phosphorus", "Фосфор", "Phosphorus", "mg", "mineral", 700, 4000, 200),
    ("copper", "Мідь", "Copper", "mg", "mineral", 0.9, 10, 210),
    ("manganese", "Марганець", "Manganese", "mg", "mineral", 2.3, 11, 220),
    ("selenium", "Селен", "Selenium", "mcg", "mineral", 55, 400, 230),
    ("iodine", "Йод", "Iodine", "mcg", "mineral", 150, 1100, 240),
    # --- vitamins ---
    ("vitamin_a", "Вітамін A", "Vitamin A", "mcg", "vitamin", 900, 3000, 250),
    ("vitamin_c", "Вітамін C", "Vitamin C", "mg", "vitamin", 90, 2000, 260),
    ("vitamin_d", "Вітамін D", "Vitamin D", "mcg", "vitamin", 20, 100, 270),
    ("vitamin_e", "Вітамін E", "Vitamin E", "mg", "vitamin", 15, 1000, 280),
    ("vitamin_k", "Вітамін K", "Vitamin K", "mcg", "vitamin", 120, None, 290),
    ("thiamin_b1", "Вітамін B1 (тіамін)", "Thiamin (B1)", "mg", "vitamin", 1.2, None, 300),
    ("riboflavin_b2", "Вітамін B2 (рибофлавін)", "Riboflavin (B2)", "mg", "vitamin", 1.3, None, 310),
    ("niacin_b3", "Вітамін B3 (ніацин)", "Niacin (B3)", "mg", "vitamin", 16, 35, 320),
    ("pantothenic_b5", "Вітамін B5 (пантотенова)", "Pantothenic acid (B5)", "mg", "vitamin", 5, None, 330),
    ("vitamin_b6", "Вітамін B6", "Vitamin B6", "mg", "vitamin", 1.7, 100, 340),
    ("biotin_b7", "Вітамін B7 (біотин)", "Biotin (B7)", "mcg", "vitamin", 30, None, 350),
    ("folate_b9", "Вітамін B9 (фолат)", "Folate (B9)", "mcg", "vitamin", 400, 1000, 360),
    ("vitamin_b12", "Вітамін B12", "Vitamin B12", "mcg", "vitamin", 2.4, None, 370),
    ("choline", "Холін", "Choline", "mg", "vitamin", 550, 3500, 380),
    # --- other ---
    ("water", "Вода", "Water", "ml", "other", 3000, None, 390),
    ("caffeine", "Кофеїн", "Caffeine", "mg", "other", None, 400, 400),
    ("alcohol", "Алкоголь", "Alcohol", "g", "other", None, 28, 410),
]


# ---- extension: Spanish / Western-European lab forms (see seed/lab_catalog_es.py) --------
def _merge_catalog_extension() -> None:
    from seed import lab_catalog_es as ext

    known = {t[0] for t in OBSERVATION_TYPES}
    OBSERVATION_TYPES.extend(t for t in ext.TYPES if t[0] not in known)
    for code, syns in ext.SYNONYMS.items():
        SYNONYMS.setdefault(code, []).extend(syns)
    UNIT_CONVERSIONS.extend(ext.CONVERSIONS)


_merge_catalog_extension()
