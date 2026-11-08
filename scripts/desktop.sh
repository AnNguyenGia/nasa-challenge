#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
source .env
set +a
cd apps/desktop
exec npm run "${1:-desktop:dev}"
