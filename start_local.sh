#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-0.0.0.0}"
REQUESTED_PORT="${PORT:-2121}"

find_available_port() {
  python - "$1" <<'PY'
import socket
import sys

start = int(sys.argv[1])

for port in range(start, start + 50):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            continue
        print(port)
        raise SystemExit(0)

raise SystemExit(f"No open port found in range {start}-{start + 49}")
PY
}

if [[ ! -d ".venv" ]]; then
  python3.12 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  python -m pip install -r requirements.txt
fi

PORT_TO_USE="$(find_available_port "$REQUESTED_PORT")"

if [[ "$PORT_TO_USE" != "$REQUESTED_PORT" ]]; then
  echo "Port $REQUESTED_PORT is already in use; starting on $PORT_TO_USE instead."
fi

echo "Starting Tonic Ear at http://127.0.0.1:$PORT_TO_USE"
exec uvicorn app.main:app --host "$HOST" --port "$PORT_TO_USE" --reload
