#!/bin/bash
# Localhost Layer 1 bridge for the visionOS / iPad home-health review pack.
# No OpenRouter key. Listens on 127.0.0.1:8767 unless HOMEHEALTH_PORT / HOMEHEALTH_BIND is set.
set -u
cd "$(dirname "$0")/../.."
exec python3 homehealth/sdr_bridge/server.py
