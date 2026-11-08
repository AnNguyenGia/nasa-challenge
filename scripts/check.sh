#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=backend:. python -m pytest -q backend/tests ml/test_pipeline.py
(cd apps/desktop && npm test && npm run build)
docker compose --env-file .env.example --profile cloud --profile ai --profile ml config --quiet
