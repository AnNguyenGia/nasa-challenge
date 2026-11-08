#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'ENV'
from pathlib import Path
import secrets
p=Path('.env')
if p.exists():
    raise SystemExit('.env already exists; refusing to replace secrets')
with p.open('x') as f:
    f.write('EDGE_API_TOKEN='+secrets.token_hex(32)+'\nCLOUD_API_TOKEN='+secrets.token_hex(32)+'\nCLOUD_URL=\nQWEN_MODEL=qwen3:4b\nIMAGE_TAG=local\n')
p.chmod(0o600)
print('Created .env with separate edge/cloud credentials')
ENV
