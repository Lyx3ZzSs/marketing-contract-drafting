#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export DOCKER_CONFIG="$PROJECT_ROOT/.runtime/docker-config"
export TMPDIR="$PROJECT_ROOT/.runtime/tmp"
mkdir -p "$DOCKER_CONFIG" "$TMPDIR"
exec docker --host unix:///var/run/docker.sock compose \
  --env-file "$PROJECT_ROOT/.runtime/test.env" \
  -f "$PROJECT_ROOT/deploy/test/compose.yaml" "$@"
