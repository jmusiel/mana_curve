#!/usr/bin/env bash
# Dev server launcher -- kills any existing Flask on :5000, then starts fresh.
# Usage: ./dev.sh

set -euo pipefail

PORT=5000

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Kill existing Python processes on the port (skip ControlCenter)
pids=$(lsof -ti :"$PORT" 2>/dev/null | while read pid; do
    comm=$(ps -p "$pid" -o comm= 2>/dev/null || true)
    if [[ "$comm" == *Python* || "$comm" == *python* || "$comm" == *flask* ]]; then
        echo "$pid"
    fi
done)

if [ -n "$pids" ]; then
    echo "Killing existing server (PIDs: $pids)"
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 0.5
fi

# Build wheel so Pyodide can load the simulation engine in-browser
echo "Building wheel..."
uv build --wheel --quiet

echo "Starting Flask dev server on :$PORT"
exec .venv/bin/flask --app src.auto_goldfish.web:create_app run --debug --port "$PORT"
