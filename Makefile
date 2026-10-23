COMPOSE = docker compose --env-file .env -f infra/compose.yaml
.PHONY: install init-env up down dev migrate check test integration openapi
install:
	uv sync --locked
init-env:
	python3 scripts/init_env.py
up:
	$(COMPOSE) up -d --build --wait api
down:
	$(COMPOSE) down
dev:
	uv run --locked uvicorn corpusflow.main:create_app --factory --host 127.0.0.1 --port 58000 --no-access-log
migrate:
	uv run --locked alembic upgrade head
check:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked mypy
	uv run --locked pytest -m "not integration" -q
test:
	uv run --locked pytest -m "not integration" -q
integration:
	uv run --locked pytest -m integration -q
openapi:
	uv run --locked python scripts/export_openapi.py
