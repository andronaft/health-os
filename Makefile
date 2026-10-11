.PHONY: start stop restart logs demo test test-unit test-integration lint

start:
	@docker compose up -d

# One-command demo database: db up, migrations, catalog seed, fictional patient.
# seed.demo refuses a non-empty DB — run `make stop` first if you need a clean slate.
demo:
	@docker compose up -d db
	@uv run alembic upgrade head
	@uv run python -m seed.load
	@uv run python -m seed.demo

stop:
	@docker compose down

restart: stop start

logs:
	@docker compose logs -f

test:
	@uv run pytest -q

test-unit:
	@uv run pytest -q -m "not integration"

test-integration:
	@uv run pytest -q -m integration

lint:
	@uv run ruff check .
