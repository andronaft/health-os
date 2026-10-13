# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/)
(pre-1.0: minor versions may break the schema or tool interfaces).

## [Unreleased]

### Fixed
- Lab rows with a name missing from the catalog were dropped by `stage_lab_panel` (only a note
  in the response). They are now stored as pending **unmapped** rows (printed name, value, unit,
  reference range), listed in `list_pending_reviews` and in the health summary's "awaiting
  review" block (#12).
- A name that matched the wrong marker (ambiguous synonym, e.g. a bare leukocyte name printed in
  10^9/L but mapped to the % type) used to take that marker's slot in the panel, so the correct
  row was rejected as a duplicate. When the unit's dimension can't belong to the matched marker
  the row is now stored unmapped, with a "likely wrong type" note instead of "no unit conversion".

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

[Unreleased]: https://github.com/andronaft/health-os/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/andronaft/health-os/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/andronaft/health-os/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/andronaft/health-os/releases/tag/v0.1.0
