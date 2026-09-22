#!/bin/bash
# Запуск Job Radar. Интерфейс откроется на http://127.0.0.1:8777
set -e
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."
exec uv run uvicorn app.main:app --host 127.0.0.1 --port 8777 "$@"
