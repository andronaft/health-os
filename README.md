# health-os

[![tests](https://github.com/andronaft/health-os/actions/workflows/tests.yml/badge.svg)](https://github.com/andronaft/health-os/actions/workflows/tests.yml)
[![Listed on mcpservers.org](https://mcpservers.org/badge.svg)](https://mcpservers.org/servers/andronaft/health-os)

**Local-first personal health record, exposed over [MCP](https://modelcontextprotocol.io).**
Your labs, diagnoses, medications, wearable data and food log live in your own Postgres; any
MCP client — one running a local model or a cloud assistant — can read and update them through
guarded tools. Critical values, drug-safety rules and screening
schedules are deterministic code, not LLM judgement.

<p align="center"><img src="docs/demo.svg" alt="An MCP session with the demo patient: LDL trend and the pending-review queue" width="820"></p>

> **Medical disclaimer.** This is not a medical device and does not give medical advice.
> Critical-value alerts and screening reminders are only a signal to contact a doctor —
> never a diagnosis and never a reason to delay care. Use at your own risk.

## What it does

- **Lab results** — drop a PDF or photo into your MCP client; the model extracts the values,
  health-os normalizes names (uk/ru/en/Latin synonyms) and units, and stages the panel as
  *pending*. Nothing counts as fact until you approve it.
- **Safety net in code** — critical values alert immediately (log, macOS notification,
  optional Telegram); critical findings in narrative reports are flagged; drug-interaction
  questions are refused and redirected to a doctor/pharmacist (only deterministic checks run:
  total daily paracetamol across products, biotin before lab tests); a crisis tool returns a
  fixed response with hotlines, independent of the model.
- **Trends and analytics** — Mann-Kendall trends, personal baselines and anomalies,
  age-gated risk calculators, a screening calendar, a weekly report, a doctor-visit brief.
- **Food log** — meals with a 41-nutrient profile, %RDA, deficiency/excess flags, meal templates.
- **Devices** — Apple Health export and Garmin import.
- **29 MCP tools + server instructions** — the safety rules are sent to every client on connect;
  see [mcp_server/README.md](mcp_server/README.md).

## Try it in one command

Only Docker needed. Starts a throwaway database with a fictional patient — two years of labs
(LDL creeping up), blood pressure, medications, a food log and a lab panel awaiting approval:

```bash
git clone https://github.com/andronaft/health-os && cd health-os/demo
docker compose up -d --build
```

Point your MCP client at it:

```json
{
  "mcpServers": {
    "health-os-demo": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--network", "health-os-demo",
               "-e", "DATABASE_URL=postgresql+psycopg://health:demo@db:5432/health_os",
               "health-os:local"]
    }
  }
}
```

Ask *"show my health summary"*, *"is my LDL trending up?"*, *"what's pending review?"*,
*"what am I short on nutritionally?"*. Remove it all with `docker compose down -v`.

## Install for your own data

Requires Docker and Python 3.12+.

```bash
git clone https://github.com/andronaft/health-os && cd health-os
cp .env.example .env                  # set the passwords
docker compose up -d db               # Postgres 16 + pgvector
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head        # schema
.venv/bin/python -m seed.load         # marker catalog, synonyms, units, nutrients
.venv/bin/python -m seed.demo         # optional: a fictional demo patient to play with

# or, one command after docker is available:
make demo                              # db up + migrations + catalog + demo patient
```

Then connect an MCP client — config for LM Studio, Open WebUI, Ollama CLI and Claude is in
[mcp_server/README.md](mcp_server/README.md). Try: *"show my health summary"*,
*"LDL trend"*, *"what am I short on nutritionally this week?"*.

**Local models:** the server speaks standard MCP over stdio, so any MCP client that runs a
local model can use it. Verified so far: the server itself with the official MCP Python client
(CI + the Docker demo). Not yet verified end-to-end with a local model — see
[#9](https://github.com/andronaft/health-os/issues/9); reports welcome.

## How it works

<p align="center">
  <img src="docs/architecture.drawio.svg" alt="Architecture: MCP client over stdio to mcp_server; read tools query approved views, write tools go through core/services into pending; safety, analytics, PostgreSQL with pgvector, ingestion" width="820">
</p>

### A lab result, from report to fact

Every row of a staged panel ends up **pending** — nothing becomes a fact without an explicit
approve. A row the catalog can't place is kept, not dropped:

<p align="center">
  <img src="docs/lab-result-flow.drawio.svg" alt="How a lab result row moves from stage_lab_panel through pending states to approved" width="820">
</p>

Unmapped and pending rows show up in `list_pending_reviews` and in the health summary's
"awaiting review" block; a learned name maps automatically on the next panel.

| Directory | What's inside |
|---|---|
| `core/` | config, DB, normalization, services, dedup, health summary |
| `mcp_server/` | MCP server, read and write tools |
| `safety/` | deterministic safety rules and alert delivery |
| `analytics/` | trends, baselines, calculators, screening, nutrition, reports |
| `ingestion/` | extraction schema, confidence scoring, device importers, embeddings |
| `migrations/` | Alembic schema |
| `seed/` | reference catalog + the demo patient |
| `evals/` | red-team scenarios (injections, hidden critical values, unit tricks) |
| `scripts/` | backup/restore (restic; `install_launchd.sh` schedules them on macOS), read-only role setup, importers |

## Privacy / local-first

- **Your data stays in your own database.** Postgres runs locally in Docker; `data/` and `.env`
  are outside git. Nothing is sent anywhere by health-os itself.
- **What leaves the machine depends on the MCP client you connect.** With a local model
  (LM Studio, Open WebUI + Ollama, …) nothing does. With a cloud assistant, whatever the tools
  return is sent to that provider — use one whose terms fit medical data (no training on your
  data, zero/short retention).
- **The goal is fully local:** local models for chat and extraction, local embeddings for search
  (already supported via fastembed). Cloud clients remain optional.
- Optional alert channel (Telegram) sends only a generic "check your health system" text, never values.
- Encrypt the disk (FileVault / LUKS / BitLocker) — the database files are plaintext at rest.
- Never put real medical data in issues, PRs or tests — synthetic data only.

## Tests

```bash
make test              # everything (needs Postgres for the integration part)
make test-unit         # pure unit tests — no database needed
make test-integration  # only tests marked `integration`
```

Integration tests never touch the working database: `tests/conftest.py` drops and recreates
`<POSTGRES_DB>_test` on the same server (migrations + seed) on every run. Override with
`TEST_DATABASE_URL` (the name must end in `_test`). Without Postgres, integration tests are
skipped locally; CI sets `REQUIRE_DB=1` so they fail instead.

Development history: [PROGRESS.md](PROGRESS.md).

## License

[AGPL-3.0-or-later](LICENSE). You may use, modify and fork health-os; if you distribute it or
run a modified version as a network service, you must publish your source under the same license.

Want to use it in a closed-source or commercial product without those obligations? A separate
commercial license is available from the author — reach out via GitHub
([@andronaft](https://github.com/andronaft)).

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) (includes a short CLA).
