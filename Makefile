COMPOSE = docker compose --env-file .env -f deploy/compose.yaml

.PHONY: install infra up down stop restart status logs migrate api worker scheduler web check integration e2e storage-smoke
install:
	cd backend && uv sync --frozen
	cd frontend && pnpm install --frozen-lockfile
infra:
	$(COMPOSE) up -d --wait postgres redis onlyoffice
up:
	python3 scripts/local.py up
down:
	python3 scripts/local.py stop
	$(COMPOSE) stop onlyoffice redis postgres
stop:
	python3 scripts/local.py stop
restart:
	python3 scripts/local.py restart
status:
	python3 scripts/local.py status
logs:
	tail -n 60 .local/run/api.log .local/run/worker.log .local/run/scheduler.log .local/run/web.log
migrate:
	cd backend && uv run alembic upgrade head
api:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 18400
worker:
	cd backend && uv run celery -A app.worker:celery_app worker --loglevel=INFO --pool=solo
scheduler:
	mkdir -p .local/run
	cd backend && uv run celery -A app.worker:celery_app beat --loglevel=INFO --schedule=../.local/run/celerybeat-schedule
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
