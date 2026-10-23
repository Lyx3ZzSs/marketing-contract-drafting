#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
(
  cd backend
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy app
  uv run pytest -m 'not integration'
)
(
  cd frontend
  pnpm lint
  pnpm typecheck
  pnpm test
  pnpm build
)
docker compose -f deploy/compose.yaml config --quiet
