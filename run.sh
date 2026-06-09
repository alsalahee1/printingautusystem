#!/usr/bin/env bash
# Launch PrintSys locally. First run installs deps and seeds sample data.
set -e

cd "$(dirname "$0")"

if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies..."
  pip3 install -r requirements.txt
fi

# Seed sample data on first run (idempotent — skips existing records).
python3 -m app.seed

echo "Starting PrintSys at http://127.0.0.1:8000 ..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
