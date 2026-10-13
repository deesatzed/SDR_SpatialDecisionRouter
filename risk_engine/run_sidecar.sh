#!/bin/bash
# Start the Bayesian risk sidecar on 127.0.0.1:${RISK_PORT:-8765}. Creates risk_engine/.venv on first run.
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python -m risk_engine.service
