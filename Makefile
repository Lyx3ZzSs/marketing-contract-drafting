COMPOSE = docker compose -f deploy/compose.yaml

.PHONY: install infra up down migrate api worker web check integration e2e storage-smoke
install:
	cd backend && uv sync --frozen
	cd frontend && pnpm install --frozen-lockfile
infra:
	$(COMPOSE) up -d --wait postgres redis
up:
	$(COMPOSE) up -d --build
down:
	$(COMPOSE) down
migrate:
	cd backend && uv run alembic upgrade head
api:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 18400
worker:
	cd backend && uv run celery -A app.worker:celery_app worker --loglevel=INFO --pool=solo
web:
	cd frontend && pnpm dev
check:
	./scripts/check.sh
integration:
	cd backend && RUN_INTEGRATION=1 uv run pytest -m integration -v
e2e:
	cd frontend && pnpm test:e2e
storage-smoke:
	cd backend && uv run python -m scripts.storage_smoke
