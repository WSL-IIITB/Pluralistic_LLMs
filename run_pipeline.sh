#!/usr/bin/env bash
set -euo pipefail

# Run the sarvam-m evaluation pipeline against your Colab/ngrok tunnel.
#
# Usage:
#   ./run_pipeline.sh [PUBLIC_URL]
#
# If PUBLIC_URL is omitted, it uses OLLAMA_BASE_URL if already exported,
# otherwise falls back to the default in src/pipeline_sarvam.py.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv-it2"

if [[ $# -ge 1 && -n "$1" ]]; then
    export OLLAMA_BASE_URL="$1"
fi

if [[ -n "${OLLAMA_BASE_URL:-}" ]]; then
    export OLLAMA_BASE_URL
fi

echo "Using OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-<pipeline default>}"
echo "Using OLLAMA_MODEL=${OLLAMA_MODEL:-<pipeline default>}"

# 1. Verify the tunnel is reachable before paying for a long run.
BASE="${OLLAMA_BASE_URL:-https://nonmutinously-oncological-meg.ngrok-free.dev}"
CODE="$(curl -s -m 15 -o /dev/null -w "%{http_code}" \
    "$BASE/api/tags" -H "ngrok-skip-browser-warning: true" || true)"
if [[ "$CODE" != "200" ]]; then
    echo "ERROR: tunnel not reachable (HTTP $CODE). Start Colab + ngrok (Cell 5) first." >&2
    echo "       Pass the new URL: ./run_pipeline.sh https://xxx.ngrok-free.dev" >&2
    exit 1
fi
echo "Tunnel reachable (HTTP 200)."

# 2. Run the pipeline.
if [[ -x "$VENV/bin/python" ]]; then
    "$VENV/bin/python" -m src.pipeline_sarvam
else
    echo "ERROR: venv not found at $VENV. Run the setup first." >&2
    exit 1
fi
