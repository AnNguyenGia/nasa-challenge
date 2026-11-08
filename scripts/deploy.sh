#!/usr/bin/env bash
# Runs ON the Ubuntu host in a checked-out, reviewed release directory.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${IMAGE_TAG:?Set IMAGE_TAG to the reviewed commit SHA}"
[[ -f .env ]] || { echo 'Run scripts/init-env.sh first'; exit 1; }
docker compose config --quiet
docker compose build edge
docker compose up -d --no-deps edge
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8000/healthz; then
    echo 'Edge release healthy'; exit 0
  fi
  sleep 2
done
echo 'Health check failed. Inspect docker compose logs edge and run documented rollback.' >&2
exit 1
