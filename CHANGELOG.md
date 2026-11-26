# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/)
(pre-1.0: minor versions may break the schema or tool interfaces).

## [Unreleased]

### Added
- Sustained deviations from the personal baseline (#75): resting heart rate up or HRV down for
  3+ days in a row against the median and spread of the 60 days before (both reported together
  when they share days; a missing day ends a run), and heart rate 30+ bpm above the resting
  median for 20+ still minutes with no steps and no workout (Apple Health raw samples). A
  workout on those days or a current beta blocker (ATC C07) is listed as context, never used to
  change the rule. The thresholds are initial defaults, to be reviewed, in one place
  (`analytics/baselines.py`). Shown as a `sustained` section of `get_anomalies` (no new tool) and
  of the weekly report (which is then not "stable"), and on the Vitals page as a short "Worth
  checking" list (English, Ukrainian, Spanish) with the days shaded on the watch's charts, in the
  browser's time zone. No push alerts. The demo watch has one such episode, 20–23 days ago.
- Browser UI: the medical-record pages (#57). **Timeline**: the whole record on one axis, in
  lanes (diagnoses; visits, procedures and hospital stays; lab panels; vaccinations; documents),
  with medications and habits drawn as bars from start to stop (to today while ongoing). A
  "life in years" strip from birth zooms to any year's months; zoom and pan by button, key
  (+ − ← → Home) or drag; each mark is focusable and opens its details, a lab panel with links to
  its markers in Labs. A panel with values under review is hollow and says how many; a refuted
  diagnosis is hollow and struck through. The same record is a sortable table under the chart.
  **Medications**: allergies first, boxed; what is taken now and before, with dose, route, dates,
  how long, what for and why it stopped, and the recorded paracetamol per day (a sum of recorded
  doses, never a safety verdict). **Diagnoses**: grouped by certainty (confirmed / provisional /
  suspected / refuted) with ICD-10 code and clinical status; an active one whose entry is unchanged
  for two years carries a neutral hint to review it with a doctor. **Habits**: each with its
  amount and how long it has run or how long ago it stopped, and a strip over the years. New
  endpoints `GET /api/v1/timeline`, `/medications`, `/diagnoses`, `/habits`.
- The demo patient has the rest of a medical record: diagnoses of every certainty, a finished
  medication course, an as-needed paracetamol, habits, doctor visits, a hospital stay with its
  procedure and discharge summary, and vaccinations — every timeline lane has something.
- Browser UI: the doctor-visit report (#60), one A4 page (two at most) to print or save as PDF
  with the browser's own print. Its language is chosen apart from the UI's (English, Ukrainian,
  Spanish: headings, marker names, units, dates and decimal commas). It has the profile, the
  allergies in a box of their own, current medications, diagnoses by status (confirmed, in
  question, past), the lab markers whose latest value is out of range (the same rows as
  `prepare_doctor_visit`'s `still_out_of_range`), up to four trend mini-charts, and "what changed
  since" a date (default: the last visit on record, else six months): new lab results against the
  one before, values that moved into or out of range, medications started or stopped, diagnoses
  recorded. A change between two results is called larger than lab noise only for LDL, total
  cholesterol and glucose, from the reference change value with the cited EFLM within-subject CV
  (`analytics/rcv.py`). "My questions for the doctor" is kept in the browser only and printed.
  Every printed page ends with how many approved values the report was made from, that it is not
  a medical document and that pending values are not included. New endpoint
  `GET /api/v1/report?lang=…&since=YYYY-MM-DD`.

### Added
- Browser UI: the Vitals page (#56). Home blood pressure is checked against the ESH home
  monitoring protocol (Parati et al., J Hypertens 2021;39:1742–1767): each run of reading days is
  a diary; the latest one says how many days had 2 morning and 2 evening readings and whether the
  protocol was followed, and only then shows the mean of its readings without the first day
  (overall, morning, evening). Earlier diaries are listed; the chart draws morning and evening
  apart, shades the diaries and marks the ESH home threshold of 135/85 mmHg with its source. The
  watch's daily values (sleep and its stages, sleep score, HRV, resting heart rate, stress, Body
  Battery, steps, training load as 7- and 28-day means of intensity minutes, VO₂max) share one
  time axis, zoom and pointer; a year of steps, sleep score and stress is drawn as calendar
  heatmaps. A 7-day to 5-year window switch; points are aggregated in the database per day, week
  (1 year) or month (5 years). New endpoint `GET /api/v1/vitals?days=&tz=`: days, "today" and
  morning/evening are read in the browser's time zone (`tz`, an IANA name; 400 for an unknown
  one). Measures without values are left out; blood pressure awaiting review is counted, not
  drawn. A reading is a systolic and a diastolic of one group, or recorded at the same moment
  (two readings logged at one minute stay two); only complete pairs count. Values entered per
  day (no time of day) are shown as such: the protocol's sessions can't be checked from them, so
  the diary says so and gives a plain mean, labelled as not a protocol check.
- Migration 0017: `v_observations` gains `time_precision` (appended; grants unchanged).
- `steps` marker (LOINC 41950-7, a daily total). Run `python -m seed.load` once to add it to an
  existing database.
- The demo patient has three home blood pressure diaries (two followed, one not) and a year of
  daily watch values.

### Added
- Browser UI: the Food page (preview), for the last 7, 30 or 90 days of the food diary. It says
  on how many of those days meals were logged, and that the amounts are estimates when they are.
  Tiles give the average per logged day of energy, protein, carbohydrates, fat, fibre, sugar and
  sodium against the catalog's norm or limit; the nutrients below 70% of the norm or over the safe
  upper limit are listed worst first. Two charts by day: energy with the norm as a dashed line, and
  sodium and potassium with sodium's limit; a day with nothing logged stays a gap. A table of
  every nutrient in the catalog, where one with no amount logged says "not logged" instead of
  passing for a zero, and a table of the meals with their main nutrients and a note when a main
  meal's time looks wrong (before 04:00, or outside its usual hours — the check `log_meal`
  answers with). Wellbeing after meals is shown when it was entered, as an association. The
  averages and flags are `nutrition_report`'s (`analytics.nutrition.summarize`); meal times are
  sent as wall-clock times, so the browser can't move a meal into another day. Read-only: meals
  are logged and fixed through the MCP client. New read-only `GET /api/v1/food?days=N`.

## [0.4.0] — 2026-11-20

### Added
- Browser UI: the Review queue page (#58) lists every value awaiting review, grouped by the
  staging it came in (panel date, lab, document, when and how it was staged, and its id for
  `approve_staged_source`). Values that can't wait (critical, or a critical check that is
  impossible) come first, then the ones whose marker wasn't recognized; each row has the value as
  printed, the range on its form, the name on the form when it was matched to a differently named
  marker, and the same notes as the Overview. Every row is drawn as pending. The page is
  read-only: approving and mapping stay with the MCP client, on your explicit instruction. New
  endpoint `GET /api/v1/review`; it lists the same rows `get_health_summary` counts as awaiting
  review.
- `get_open_results` (MCP tool): lab markers whose latest approved value is out of range and
  that nothing approved has measured since, oldest first, with since when they have been out of
  range in a row and whether a newer value waits for review (its number is not shown).
  `prepare_doctor_visit` gains the same list as `still_out_of_range`: its `recent_abnormal`
  also lists values re-measured in range since. The Overview's out-of-range table says the same
  in a Note column ("Out of range 3 times in a row, since 2025-05-27").
- Browser UI: print styles (always the light palette, no navigation or controls, tables in
  full; charts are repainted light for the print), a loading placeholder for pages that take
  more than 200 ms, and no animation under `prefers-reduced-motion`.
- Browser UI skeleton (preview): `make ui` / `python -m web` starts a read-only web server on
  127.0.0.1 only (port `UI_PORT`, default 8765) and opens the page with a per-run session token
  in the URL fragment. Requests with a foreign `Host` get 400 (DNS rebinding), `/api/*` without
  the token 403, anything but GET 405; a strict Content-Security-Policy, no external resources.
  The page shows only the connection status and version so far. New `ui` extra (Starlette,
  uvicorn) (#50).
- Browser UI frame (preview), still without data: a menu of the coming pages, a light, dark or
  system theme from CSS tokens, and a "Not a medical device" footer. Reusable pieces for the data
  pages: a sortable and filterable table (blanks sort last in both directions), a status pill
  (low / in range / high / pending, always with a word and an icon; pending is hollow and
  dashed), empty and error states. Apache ECharts 6.1.0 is vendored in `web/static/vendor/` with
  its licences and loaded only by a page that draws a chart. Its tooltips are painted on the
  canvas, because the default HTML ones break under the CSP. Checked in a browser in both themes
  at 1280 and 375 px wide: no external requests, no CSP violations (#53).
- `core/queries.py` — one read layer for the MCP tools and the coming browser UI: `observations`, `trend`, `timeline`, the per-user views, plus `markers` (latest value of every marker with its own range and counts) and `series` (chart points, each with its own reference range). The MCP tools now call it; their output is unchanged (#51).
- `check_data_quality` — checks of the stored records, not of health: reference ranges that are
  swapped, empty or far narrower than the same marker's other ranges (typical recognition
  errors), lab values that jumped ≥5× from the previous value, approved numbers without a
  canonical value, the review queue, and diagnoses still "active" after two years. Each item is
  "verify against the original document".
- `get_anomalies` — compares each marker's latest approved value with the user's own earlier
  values (mean ± SD of up to 90 previous values) and lists those beyond a z threshold. Uses the
  existing `analytics/baselines.py`, which no tool reached before. Markers with fewer than 5
  earlier values and personal records (`pr_*`, which only ever improve) are skipped. README no
  longer claims risk calculators beyond their age gate (#33).
- Browser UI Overview page (preview), the home page: profile card that says what a missing date
  of birth or sex breaks; critical values in red with their escalation text, approved or not;
  values awaiting review, marked as not yet facts; latest values out of range, overdue screenings
  and markers not checked in over 12 months; tiles with 30-day sparklines for blood pressure
  (7-day average), resting heart rate, HRV, sleep score and weight; recent events, with a panel
  still under review flagged. It says "N of M recorded markers in range" and what the rest are,
  never a global verdict. New read-only `GET /api/v1/overview`. It reads the same rows as
  `get_health_summary` (`core.health_summary.read_facts`) in one read-only snapshot (#54).
- Browser UI Labs page (preview). The marker table lists every lab marker's latest approved
  value with its status, the range on its form, a sparkline of the last 12 values, how many
  values there are since when, and how many wait for review; filters for "out of range only"
  and specimen, plus the text filter. Each marker has its own page: a chart in the marker's
  canonical unit where every value sits over the range printed on its own form (ranges differ
  between labs; a range in another unit is converted like the value, or left out if it can't
  be), pending values drawn hollow, grey and labelled "unverified", the trend (Mann-Kendall
  p, Theil–Sen slope per year, the same numbers as `get_trend`), an optional personal baseline
  (mean ± 2σ, at least 5 approved values), text results on their own axis, and a table of every
  value with the form's value, unit and range. A panel matrix shows markers × the latest 12
  days with a lab value, coloured by status. Pending values count in no table, matrix, trend
  or baseline. New read-only `GET /api/v1/labs` and `GET /api/v1/labs/{code}`; `get_trend` now
  also returns `p` (#55).
- Browser UI: on the Overview, a lab panel in Recent events says how many values it has and how
  many approved ones are out of range ("6 values, 2 out of range") instead of a blank, and links
  to the Labs page; a panel under review gives only its size. The names in "Latest values out
  of range" link to their Labs pages. Menu items for pages not built yet say "soon".

### Changed
- Critical-value messages in tool output and alerts are in English by default, with Ukrainian
  and Spanish available through `HEALTH_OS_LANG` (`en` / `uk` / `es`). They were Ukrainian
  only, so an English-speaking user got the system's most important message in a language
  they may not read (#32).
- Marker and nutrient names moved from the `name_uk` / `name_en` columns into
  `observation_type_names` and `nutrient_type_names` (one row per language), and the whole
  catalog now has Spanish names. The read-only role reads them through
  `v_observation_type_names` and `v_nutrient_type_names`. `v_observations` gains `loinc_code` and
  `facility` and, like the other views, keeps `name_uk`. After `alembic upgrade head`, run
  `python -m seed.load` to get the Spanish names. Your own scripts that read or write
  `observation_types.name_uk` need to use the new tables (#52).

### Fixed
- `approve_staged` dated an approval only once no unmapped row was left in the panel, so values
  approved today counted from the day they were staged and could miss the weekly report.
- A lab panel whose values were all deleted (a mistaken staging) stayed on the timeline, in the
  Overview's events and as the summary's "last lab panel". Migration 0015 keeps a panel on
  `health_timeline` only while one of its values is not deleted.
- Browser UI: an approved value whose critical check is impossible (a limit like ">5"
  potassium, or a unit that wasn't converted) is shown in the Critical values block at the top
  of the Overview, like the health summary shows it: approving it was not a check.
- Browser UI: "high" and "critical" were the same red; red is now for critical only and high is
  a burnt orange. Form controls' edges reach 3:1 contrast (they were about 1.4:1). The range on
  a marker's chart has a solid edge at its limits. On a phone, a wide table keeps its first
  column in view while scrolling sideways.
- **Critical findings in narrative reports were never checked.** The classifier for
  "BI-RADS 5", "suspicion of malignancy", "aneurysm", "cito" existed but nothing called it, so
  a document stored with `upsert_document` / `add_chunks` sent no alert. Both now scan the text
  they store and alert through the same channel as a critical lab value (one alert per call).
  The new `ingestion.narratives.ingest_narrative` stores a document with its chunks and returns
  the hits (`narrative_flags`, `critical`, and a note sending the user to a doctor).
- The narrative classifier missed common report phrasings: "BI-RADS category 4", "BI-RADS IV",
  "BI-RADS 4C", "PI-RADS v2.1 score 5", "ACR TI-RADS TR5", "Lung-RADS 4B", "Bosniak IV". It now
  reads the words between the scale and the grade (category / score / v2.1 / categoría /
  категорія), Roman numerals, sub-letters and ranges ("BI-RADS 3–4"); BI-RADS 6, Lung-RADS and
  Bosniak III–IV are new. Benign grades (BI-RADS 1–3, TR1–TR3, PI-RADS 1–3, Lung-RADS 1–3,
  Bosniak I–IIF) and follow-up intervals ("BI-RADS 3, control a 6 meses") stay quiet. The word
  "suspicious" (es "sospechoso", uk "підозрілий", ru "подозрительный") now flags, except in
  plain negations such as "no suspicious findings" or "sin hallazgos sospechosos"; negation is
  applied to that word only, so "no findings suspicious for malignancy" still flags.
- **Apple Health import ignored each record's unit.** A US-locale export's 180 lb was stored as
  180 kg body weight and a 103.1 °F fever as 103.1 °C. Values are now converted from the unit on
  the record (lb, st, g → kg; degF, K → °C); records with a unit the importer doesn't know, or
  none, are skipped and listed in the result's `skipped_unknown_unit` instead of being stored.
  Samples and daily values already imported are not corrected by importing the export again.
- Browser UI: the small charts stretched any change over their full height, so the demo's weight
  going from 68.35 to 68.4 kg was drawn as a steep climb. The Overview tiles and the Labs
  sparklines now span at least 5% of the values.
- Browser UI: leaving a marker's Labs page before it finished loading could replace the next
  page's heading with that marker's name.
- **Critical values printed as a limit were never checked.** A value like ">600" (a glucose
  meter's HI) or "<10" (platelets) was stored as text, so it skipped both the critical check
  and the "critical check impossible" flag, sent no alert, and the summary listed it as an
  ordinary pending value. A limit is now a number with its comparator: it is critical when
  everything past it is critical, and "only a limit on the form — critical check impossible"
  when a critical value may lie past it (">5" potassium). Its status is set only when the
  limit decides it. Limits stay out of trends and the personal baseline. Text results
  ("negative") are unchanged. Values already stored as text are not re-read.
- The weekly report said `"stable": true` while a critical or uncheckable value was waiting for
  review. It now lists them in `alarming_pending` and is never stable with one. Its window
  also counts a value from when it was approved, not when it was staged: a panel staged 12
  days ago and approved today was in no weekly report.
- One malformed row in `stage_panel` (no `raw_name`, or not an object) crashed the whole panel,
  critical rows included, in the duplicate check that runs before the row loop.
- `map_pending_observation` saved a learned synonym as typed, but lookups compare the name
  without accents, so a name like "Glucosa (método enzimático)" never mapped again even though
  the tool said it was saved. New ones are saved in the compared form; learned synonyms
  already stored with accents still need re-saving.
- Nutrition averages divided each nutrient by the days it appeared, not by the days logged: one
  meal with vitamin D in a week read as 75% of the daily RDA instead of 11%, hiding a
  deficiency. The food↔wellbeing glycemic index average also weighed meals by their number of
  nutrient rows.
- `query_observations` returned weekly min/avg/max buckets for any window over 90 days, which
  is the default (365). A year of a lab marker came back without status, unit, range or text
  results. It now returns every value, with comparator, text and the form's range. Only more
  than 200 values are bucketed, and the buckets count out-of-range and critical values.
- Crisis keyword detection missed everyday phrasing: Spanish had only the `suicid` stem
  ("quiero morir", "no quiero vivir más", "me quiero matar" went undetected), German and Polish
  had nothing, and Russian "не хочу жить" and English "I don't want to live" slipped through.
  All six languages now have their own pattern lists, Spanish, German and Polish also match
  without diacritics, and extra spaces, line breaks and typographic apostrophes no longer hide
  a phrase. "свести счёты" never matched because the text was normalized to "е" and the
  pattern was not (#31).
- With the database unreachable (e.g. Docker Desktop stopped), `crisis_resources` failed instead of returning its fixed response; it no longer depends on the database. Every other tool now answers "database unreachable" with a hint instead of a bare "Error executing tool".
- Backups were silently skipped when Docker Desktop wasn't running ("Cannot connect to the
  Docker daemon"): `backup.sh` and `restore_test.sh` now start Docker Desktop on macOS and wait
  for the database, and a failure is written to the log as `backup FAILED` and shown as a macOS
  notification. Re-run `scripts/install_launchd.sh` to update the scheduled copies.

- `get_trend`: the Mann-Kendall variance now has the standard tie correction (rounded lab values
  and integer wearable readings repeat often, so real trends were missed), and the slope is
  reported per year — a Theil–Sen median over the measurement dates, robust to outliers and
  uneven gaps — as `slope_per_year` (#34).
- The narrative critical-findings classifier missed Spanish reports: *aneurisma*, *trombosis*,
  *infarto*, *ictus*, *masa*, *nódulo sospechoso*, *lesión ocupante de espacio*, *disección
  aórtica* and more now flag, with or without accents. Also added in every language: lymphoma,
  leukaemia, melanoma and aortic dissection. Negation stays unhandled on purpose (documented);
  only "índice de masa corporal", bone/muscle/ventricular mass are excluded (#30).
- **`recompute_canonical` filled in canonical values without the critical check.** A pending
  potassium 6.9 stored before its unit could be converted was flagged "critical check
  impossible"; once recompute filled in its value, the flag was gone and the value read as
  ordinary. Recompute now runs the critical thresholds on every value it fills in: a hit gets
  status `critical`, an alert on `--apply`, and a line in the script's output. An approved row
  that turns out critical goes back to pending review, with the reason in its notes, so the
  health summary and the weekly report show it as a critical value; approving its source again
  acknowledges it.
- **"G/L" (giga per litre, 10^9/L) was read as grams per litre.** Platelets 25 G/L, as French,
  Swiss, German and Spanish forms print them, were stored unmapped with no critical flag and no
  alert. "G/L" and "T/L" (10^12/L) are now recognised by their capital letter; for a marker
  measured in g/L (haemoglobin), "G/L" still reads as grams. A critical-watch marker whose unit
  can't belong to it (potassium in %) is now flagged "critical check impossible" and alerted, and
  the flag is kept on the row, so the summary and the weekly report keep it alarming until it is
  mapped.
- **Approving a value printed as a limit removed every warning.** Approving a ">5" potassium
  (range 3.5–5.1) moved it out of the pending queue, and with it out of the summary and the
  weekly report, which then said `"stable": true`. Approved values the critical check couldn't
  settle (a limit, or no canonical value) are now returned by `approve_staged_source` in
  `unverifiable_approved` with a warning, listed in the weekly report (which is not stable with
  one) and in a short section of the health summary. Pending and approved rows use one
  definition of "uncheckable".
- `approve_staged_source` returned `approved_observations: 0` as if it had worked when the
  source was already approved or was never staged; it now returns an error. A source with only
  unmapped rows pending also returns an error, listing them.
- `list_pending_reviews` showed a value printed as ">5" as a plain 5.0: the pending view had no
  comparator. Migration 0016 adds `comparator` and `notes` to `v_observations_pending`.
- **`check_medication_safety` dropped recorded paracetamol when products were passed in.**
  Paracetamol 1 g × 4 on the medication list plus Frenadol 650 mg × 3 passed in came out as
  1950 mg/day "ok" instead of 5950 mg "exceeded". Recorded paracetamol is now always counted;
  a product passed under the same name replaces only that entry, and the result lists which
  recorded entries were added (`from_current_medications`).
- Paracetamol on the medication list was found only by a few generic spellings, so brands
  (Gelocatil, Panadol, Efferalgan, Dafalgan, Termalgin, Tylenol, Apiretal, Frenadol, Calpol,
  Xumadol, Perfalgan) and "Acetaminofén" got no daily-total check at all. Names are now matched
  anywhere in the name ("Парацетамолу таблетки", "Paracetamolratiopharm"), without accents, and
  by ATC code (N02BE01 / N02BE51 / N02BE71).
- `check_medication_safety`: `planned_tests` were case-sensitive — "TSH" gave no biotin warning.
- MCP tools no longer fail with a raw database error (and the SQL) on bad input: a non-UUID id,
  an impossible date ("2026-02-30"), a string longer than its column or a constraint violation
  now comes back as `{"error", "detail"}`. `map_pending_observation` and
  `approve_staged_source` check the id up front; `log_meal`, `log_from_template`,
  `record_medication`, `record_diagnosis` and `set_profile` check their dates up front.
- `set_profile` stored `sex` as typed, and "Male" silently dropped the male-only screenings.
  It is stored as male/female (any case; m/f, чоловіча/жіноча, hombre/mujer accepted),
  anything else is refused, and so is a date of birth in the future. The screening calendar
  also reads profiles saved before this case-insensitively.
- `record_diagnosis` refuses an empty name, a date in the future and statuses outside
  clinical_status active / recurrence / relapse / inactive / remission / resolved and
  verification_status confirmed / provisional / suspected / differential / refuted ("Confirmed"
  is stored as "confirmed"). `record_allergy` refuses a blank allergen and a severity longer
  than its 20-character column.
- Food diary: `log_meal` / `update_meal` refuse a time more than a day ahead, negative or
  non-numeric nutrient amounts, a glycemic index outside 0–100 and a negative glycemic load;
  `log_from_template` refuses a portion_factor ≤ 0. Nutrition analytics ignore meals dated more
  than a day ahead — one dated next year used to count in every window until then.
- `log_from_template` crashed on a template with a null or text nutrient amount; those are now
  left out and listed in `skipped`. `save_meal_template` refuses unknown nutrient codes ("protien"
  was saved and then dropped from every meal logged from it) and impossible amounts.
- `stage_lab_panel` with no rows created an empty panel, reported it as staged and showed it on
  the timeline; it is now refused before anything is written.
- `search` returned document chunks of every user in the database, and `crisis_resources` showed
  whichever profile's emergency contact came first; both are now limited to the current user.
- `list_pending_reviews` capped the queue at 200 rows in no particular order, so the newest
  values could be the ones left out, silently. It now returns `{"rows", "truncated"}`, newest
  first. The other lists have a fixed order too (medications and habits by start date,
  diagnoses by date, allergies by name).

## [0.3.0] — 2026-10-15

### Changed
- `sql_query` runs only on the restricted read-only login (`READONLY_DATABASE_URL`). On a login
  that can do more (a superuser or the owner of the tables — the default without
  `READONLY_DATABASE_URL`) it returns an error explaining the setup; the other read tools are
  unaffected. The Docker demo now sets up and uses the restricted login.

### Fixed
- Lab rows with a name missing from the catalog were dropped by `stage_lab_panel` (only a note
  in the response). They are now stored as pending **unmapped** rows (printed name, value, unit,
  reference range), listed in `list_pending_reviews` and in the health summary's "awaiting
  review" block (#12).
- A name that matched the wrong marker (ambiguous synonym, e.g. a bare leukocyte name printed in
  10^9/L but mapped to the % type) used to take that marker's slot in the panel, so the correct
  row was rejected as a duplicate. When the unit's dimension can't belong to the matched marker
  the row is now stored unmapped, with a "likely wrong type" note instead of "no unit conversion".
- `stage_lab_panel` crashed on a value passed as printed — `"6,4"`, `"negative"`, `"<0.5"` — and
  lost the whole panel, critical rows included. Numeric strings are now read as numbers, other
  text is stored as `value_text`, and every row is isolated: a row that still fails is reported
  and the rest is kept. A row without a value says "no value" (it was reported as a duplicate),
  and `panel_date` must be a valid date that isn't in the future (#41).
- `check_medication_safety` counted a paracetamol product with no known dose as 0 mg and answered
  "within limits"; a current paracetamol entry without a dose in mg was skipped. An unknown dose
  is now reported as `incomplete`, asking for mg per dose and doses per day (#43).
- `get_trend` / `query_observations`: a code with no values at all (`"LDL"`, a typo) looked like
  "no data for this marker". Codes are lower-cased, and an empty result says which case it is,
  with `did_you_mean` codes. Very large `days` windows no longer crash six read tools, and
  panels without a type are titled "lab panel" in the timeline (#44).
- `get_trend` used the oldest 500 values instead of the most recent (#24); `search` failed on
  tokens with leading/trailing apostrophes (#23); read tools returned empty lists instead of a
  "no user" error before a profile exists (#25); `approve_staged_source` reported success for an
  unknown `source_id` (#26).
- The test suite fired real critical alerts (alerts log, macOS notification, Telegram) on the
  maintainer's machine; tests now never reach the real channels (#40).

### Added
- `map_pending_observation(observation_id, type_code)` — assigns the type, re-normalizes the value,
  re-runs the critical-value check and saves the printed name as a learned synonym, so the next
  panel maps it automatically. Migration 0011: `observations.type_id` nullable + `raw_name`;
  unmapped rows can never be approved (`approve_staged_source` leaves them pending).
- `update_medication` and `stop_medication` — medications could only be added, so a wrong dose
  or a drug the user no longer takes could be fixed only with raw SQL, and `get_medications`
  kept listing it. Corrections change only the given fields; a stop sets status `stopped` +
  `end_date` (not in the future), drops the drug from `get_medications` and the safety checks
  and adds a `medication_stop` event to the timeline. A dose the doctor changed is recorded as
  stop + new entry, so the timeline shows when. Migration 0012: `medication_history` (trigger
  keeps every previous version of the row, like `observation_history`).
- `record_medication` takes `route` (oral / topical / …).
- `update_meal` and `delete_meal` — a logged meal couldn't be corrected: a wrong time, portion or
  nutrient estimate, or a meal logged twice, needed raw SQL. `update_meal` overwrites only the
  given fields and nutrient codes; `delete_meal` is a soft delete. `query_food` now returns each
  meal's `id` for them.
- `log_meal` / `log_from_template` return the `eaten_at` they stored and a `time_check` note when
  a main meal's time looks wrong: a lunch at 23:30, or a meal after midnight that may belong to
  the day before. Daily nutrient totals go by the date, and meals logged late at night with
  "now" as the time were landing on the wrong day (5 of 45 main meals in real use).

## [0.2.1] — 2026-10-01

### Fixed
- `sql_query` reached MCP clients with no description at all (its docstring was a concatenated
  string), so models never saw what it does or the view schema.

### Changed
- Clearer tool descriptions: when to use each tool vs. its neighbours, parameter formats and
  what is returned (17 tools).

### Added
- Docker image published to `ghcr.io/andronaft/health-os` (amd64 + arm64) on every release, with
  the MCP Registry ownership label; `server.json` manifest for the official MCP Registry.
- Releases publish to the official MCP Registry automatically (GitHub OIDC, no stored secrets);
  the release steps are in CONTRIBUTING.md.

## [0.2.0] — 2026-09-30

### Security
- `sql_query` always runs as `health_readonly` (`SET LOCAL ROLE`). Without
  `READONLY_DATABASE_URL` it used to run as the database owner — a superuser in the Docker image —
  and could read unapproved values, the audit log and files on the database server.

### Safety
- **Critical values were silently missed** when a lab printed the unit or name differently:
  `mmol/l`, `ммоль/л`, `g/dL`, `mEq/L`, `10^9/L`, `×10⁹/л`, `/µL`, `K`, `Potasio`… The unit gate
  failed and the critical check never ran. Units are now canonicalized (case, Cyrillic,
  powers of ten), conversions for every critical-watch analyte were added, and Spanish/`K`
  synonyms for them.
- Fail-safe: a critical-watch analyte whose unit still can't be converted raises an alert
  ("critical check impossible — compare with the form") instead of passing silently.
- `get_health_summary` now starts with the values awaiting review, critical ones spelled out —
  previously a pending critical value was invisible in the summary.
- A marker appearing twice on one form (e.g. fasting + 2 h glucose) no longer aborts the whole
  panel; the duplicate is reported and the other rows — including critical ones — are kept.
- Alert logging can't break ingestion (read-only FS) and also goes to stderr, which MCP clients
  keep (a `docker run --rm` container loses its log file).

### Added
- Catalog extension for Spanish / Western-European lab forms (`seed/lab_catalog_es.py`): 69 new
  marker types (bilirubin fractions, eGFR, NT-proBNP, iron panel, coagulation, thrombophilia,
  autoimmunity, coeliac, urinalysis, hepatitis/HIV serology, viral PCR, stool tests), Spanish
  synonyms for existing markers, dimension-exact conversions (mg/dL→g/L, g/dL→g/L, mU/L, µg/dL…).
- Name lookup strips Latin accents ("Fósforo" = "fosforo"); Cyrillic letters are kept intact.
- MCP server instructions: the safety rules (`prompts/system_prompt.py`) are sent to every client
  on connect and exposed as the `health_assistant` prompt.
- `check_medication_safety` tool: interaction refusal + total daily paracetamol + biotin checks.
- `crisis_resources` tool: the fixed crisis response, now reachable from any MCP client.
- MCP tool annotations: reads are read-only, writes are not, `approve_staged_source` is
  destructive — clients can auto-allow reads and ask before approving lab values.

### Changed
- Migrated to the MCP Python SDK 2.x (`FastMCP` → `MCPServer`); requires `mcp>=2.2,<3`.

### Fixed
- Scheduled backups never ran on macOS when the checkout lives in ~/Desktop or ~/Documents:
  launchd jobs can't read those folders ("Operation not permitted"). New
  `scripts/install_launchd.sh` installs the backup + restore-test jobs outside them; the scripts
  take `HEALTH_OS_ENV_FILE` / `HEALTH_OS_STATE_DIR`. The plist templates are replaced by it.
- Approved values without a canonical value silently dropped out of trends and analytics (#11):
  dimensionless markers (INR, ratios, indices) now get one; `approve_staged_source` refuses
  unconvertible numeric values unless `allow_missing_canonical=true`; new
  `scripts/recompute_canonical.py` fills in old rows (dry-run by default); the weekly report
  shows `approved_without_canonical`.
- `query_nutrition` had its own copy of the flag logic and still reported low sugar/sodium as
  deficient; it now uses the same `analytics.nutrition.summarize` as `nutrition_report`.
- The safety layer described in the README was not reachable over MCP: the system prompt was
  never sent and the crisis/medication checks had no tools.
- Demo MCP config uses `docker run -i --rm` instead of `docker compose run`, which left a
  running container behind after every client session.

### Removed
- Open WebUI service, `setup.sh` (Ollama install + model pull), `make setup`/`pull-model` and a
  machine-specific Ollama reinstall script: they were never connected to health-os, so the
  "fully local stack" did not actually work. Local-model clients remain an open topic (#9).

## [0.1.0] — 2026-09-29

First public release.

### Added
- **MCP server with 26 tools** — health summary, observations and trends (Mann-Kendall),
  timeline, medications/diagnoses/allergies, screening calendar, doctor-visit brief, weekly
  report, food log and nutrition analytics, document search, read-only SQL; write tools for the
  profile, manual entries, meals and meal templates, and lab panels (stage → explicit approve).
- **Deterministic safety layer** — critical-value rules with alerts (log, macOS notification,
  optional generic Telegram), critical findings in narrative reports, drug-interaction refusal
  with paracetamol-total and biotin checks, crisis protocol independent of any model.
- **Data model** — PostgreSQL 16 + pgvector schema (Alembic), approved views and a separate
  read-only role, normalization of marker names (uk/ru/en/Latin) and units, qualitative values,
  logical panel dedup, extraction confidence scoring.
- **Food log** — 41 nutrients with %RDA and deficiency/excess flags, meal templates,
  food ↔ wellbeing association.
- **Importers** — Apple Health export, Garmin.
- **Analytics** — baselines and anomalies, age-gated risk calculators, screening calendar.
- **One-command demo** — `demo/docker-compose.yml` with a fictional patient; Dockerfile for the
  MCP server.
- Backups with restic + launchd restore test; red-team eval scenarios.
- CI: tests on Python 3.12/3.13 against Postgres, ruff, gitleaks; Dependabot; locked dependencies.

### Fixed
- Pinned `mcp<2`: the 2.x SDK removed `FastMCP` and the server failed to start on fresh installs.
- Limit-only nutrients (sugar, added sugar, saturated fat, cholesterol, sodium) are no longer
  reported as deficient when intake is low.

### Security
- Postgres and Open WebUI ports bound to `127.0.0.1` by default.
- Private vulnerability reporting — see [SECURITY.md](SECURITY.md).

[Unreleased]: https://github.com/andronaft/health-os/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/andronaft/health-os/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/andronaft/health-os/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/andronaft/health-os/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/andronaft/health-os/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/andronaft/health-os/releases/tag/v0.1.0
