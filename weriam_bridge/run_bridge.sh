#!/bin/bash
# Start the WERIAM bridge on 127.0.0.1:8766 (creates the WERIAM state via `weriam develop` if missing).
#   WERIAM_ROOT=/path/to/WERIAM WERIAM_STATE=~/.sdr/weriam_state ./weriam_bridge/run_bridge.sh [--fresh]
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
if [ "${1:-}" = "--fresh" ]; then rm -rf "${WERIAM_STATE:-$HOME/.sdr/weriam_state}" "${WERIAM_BRIDGE_DATA:-$HOME/.sdr/weriam_bridge}"; shift; fi
exec "$PY" -m weriam_bridge.server --init "$@"
