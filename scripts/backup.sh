#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p data/backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T edge python -c 'import sqlite3; a=sqlite3.connect("/data/edge.db"); b=sqlite3.connect("/tmp/edge-backup.db"); a.backup(b); b.close(); a.close()'
docker compose cp edge:/tmp/edge-backup.db "data/backups/edge-$stamp.db"
echo "Saved data/backups/edge-$stamp.db; encrypt before transferring off device."
