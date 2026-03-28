#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  python3.12 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  python -m pip install -r requirements.txt
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 2121 --reload
