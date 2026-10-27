#!/bin/bash
# Build and launch the visionOS app on the Home health review pack.
# Starts the Layer 1 bridge when it is not already up. The app still runs if the bridge fails
# (cards show the bundled snapshot).
#
#   tools/homehealth_vision.sh
#   SIM_NAME="Apple Vision Pro" tools/homehealth_vision.sh
#   SIM_UDID=<udid> tools/homehealth_vision.sh
set -u
cd "$(dirname "$0")/.."
NAME=${SIM_NAME:-SDR-VisionPro}
UDID=${SIM_UDID:-}
BUNDLE=com.wsatz.SpatialHITM
APP=build/Build/Products/Debug-xrsimulator/SpatialHITM.app

if ! curl -s -m 1 http://127.0.0.1:8767/health >/dev/null; then
  nohup homehealth/sdr_bridge/run_bridge.sh > /tmp/homehealth_l1.log 2>&1 &
  for _ in $(seq 1 20); do curl -s -m 1 http://127.0.0.1:8767/health >/dev/null && break; sleep 0.3; done
fi
if curl -s -m 1 http://127.0.0.1:8767/health; then
  echo
  echo "Layer 1 bridge up (L1 live badge expected)"
else
  echo "Layer 1 bridge NOT reachable — app will show the bundled snapshot (L1 bundled · bridge offline)"
fi

if [ -z "$UDID" ]; then
  UDID=$(xcrun simctl list devices available | awk -v n="$NAME" '$0 ~ n && $0 ~ /visionOS/ { gsub(/[()]/, "", $(NF-1)); print $(NF-1); exit }')
fi
if [ -z "$UDID" ]; then
  echo "No visionOS simulator named '$NAME'. Set SIM_NAME or SIM_UDID." >&2
  exit 1
fi

xcrun simctl boot "$UDID" 2>/dev/null || true
open -a "$(xcode-select -p)/Applications/Simulator.app" 2>/dev/null || true
if [ ! -d "$APP" ]; then
  xcodebuild -project SpatialDecisionRouter.xcodeproj -scheme SpatialHITM \
    -destination "id=$UDID" -derivedDataPath build build
fi
xcrun simctl terminate "$UDID" "$BUNDLE" 2>/dev/null || true
xcrun simctl install "$UDID" "$APP"
xcrun simctl launch "$UDID" "$BUNDLE" -domain home_health -autoOpenImmersive -freshRegistry
echo "Launched Home health on $UDID"
