.PHONY: install lint fmt typecheck test infra-up infra-down infra-logs check-infra check-models

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
