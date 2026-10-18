.PHONY: start stop restart logs demo demo-down test test-unit test-integration lint

start:
	@docker compose up -d

# One-command demo: a throwaway database with a fictional patient (demo/docker-compose.yml).
# Its own compose project and volume — never the database of `make start`. `run` waits for the
# db healthcheck before migrating; re-running keeps the existing demo data.
demo:
	@cd demo && docker compose build init && docker compose run --rm init
	@echo 'Demo ready. MCP client config: README.md → "Try it in one command". Remove: make demo-down'

# Deletes the demo database only (its own volume); your own data is not touched.
demo-down:
	@cd demo && docker compose down -v

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
