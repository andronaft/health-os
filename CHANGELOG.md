# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/)
(pre-1.0: minor versions may break the schema or tool interfaces).

## [Unreleased]

### Changed
- Migrated to the MCP Python SDK 2.x (`FastMCP` → `MCPServer`); requires `mcp>=2.2,<3`.

### Added
- MCP server instructions: the safety rules (`prompts/system_prompt.py`) are sent to every client
  on connect and exposed as the `health_assistant` prompt.
- `check_medication_safety` tool: interaction refusal + total daily paracetamol + biotin checks.
- `crisis_resources` tool: the fixed crisis response, now reachable from any MCP client.
- MCP tool annotations: reads are read-only, writes are not, `approve_staged_source` is
  destructive — clients can auto-allow reads and ask before approving lab values.

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

### Security
- `sql_query` always runs as `health_readonly` (`SET LOCAL ROLE`). Without
  `READONLY_DATABASE_URL` it used to run as the database owner — a superuser in the Docker image —
  and could read unapproved values, the audit log and files on the database server.

### Fixed
- `query_nutrition` had its own copy of the flag logic and still reported low sugar/sodium as
  deficient; it now uses the same `analytics.nutrition.summarize` as `nutrition_report`.
- The safety layer described in the README was not reachable over MCP: the system prompt was
  never sent and the crisis/medication checks had no tools.
- Demo MCP config uses `docker run -i --rm` instead of `docker compose run`, which left a
  running container behind after every client session.

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

[Unreleased]: https://github.com/andronaft/health-os/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/andronaft/health-os/releases/tag/v0.1.0
