.PHONY: install lint fmt typecheck test infra-up infra-down infra-logs check-infra check-models ingest ingest-samples probe retrieve ask up down build logs

install:
	cd backend && uv sync

lint:
	cd backend && uv run ruff check .

fmt:
	cd backend && uv run ruff format .
	cd backend && uv run ruff check --fix .

typecheck:
	cd backend && uv run mypy app

test:
	cd backend && uv run pytest -v

infra-up:
	docker compose -f deploy/docker-compose.yml up -d

infra-down:
	docker compose -f deploy/docker-compose.yml down

infra-logs:
	docker compose -f deploy/docker-compose.yml logs -f

check-infra:
	cd backend && uv run python ../scripts/check_infra.py

check-models:
	cd backend && uv run python ../scripts/check_models.py

ingest:
	cd backend && uv run python -m app.ingestion

ingest-samples:
	cd backend && uv run python -m app.ingestion --dir ../data/samples

probe:
	cd backend && uv run python ../scripts/probe_search.py "$(q)"

retrieve:
	cd backend && uv run python -m app.rag --q "$(q)"

ask:
	cd backend && uv run python -m app.agents --q "$(q)"

# ===== 全栈（Docker，根目录 docker-compose.yml）=====
up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build api frontend

logs:
	docker compose logs -f api frontend
