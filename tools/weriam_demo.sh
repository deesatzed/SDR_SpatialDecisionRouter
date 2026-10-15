#!/bin/bash
# WERIAM Principal demo: start the WERIAM bridge (127.0.0.1:8766) and launch the app in the WERIAM demo.
#   tools/weriam_demo.sh [--ipad|--vision] [--auto] [--fresh]
#   --fresh  : new WERIAM state (runs `weriam develop --episodes 2`; requests start pending)
#   WERIAM_ROOT overrides the WERIAM checkout (default /Volumes/WS4TB/Quncen38/hive-lineage-sim/WERIAM)
set -u
cd "$(dirname "$0")/.."
PLAT=ipad; AUTO=(); FRESH=""
for a in "$@"; do case "$a" in --ipad) PLAT=ipad;; --vision) PLAT=vision;; --auto) AUTO=(-demoAuto);; --fresh) FRESH=--fresh;; esac; done
if [ -n "$FRESH" ] || ! curl -s -m 1 http://127.0.0.1:8766/health >/dev/null; then
  pkill -f "weriam_bridge.server" 2>/dev/null; sleep 0.5
  nohup ./weriam_bridge/run_bridge.sh $FRESH </dev/null > /tmp/weriam_bridge.log 2>&1 &
  for i in $(seq 1 60); do curl -s -m 1 http://127.0.0.1:8766/health >/dev/null && break; sleep 0.5; done
fi
curl -s -m 1 http://127.0.0.1:8766/health >/dev/null && echo "✓ WERIAM bridge up (cards are live; Approve/Decline go to WERIAM's journal)" \
  || echo "⚠ bridge NOT reachable — app shows seeded cards, nothing is sent (see /tmp/weriam_bridge.log)"
if [ "$PLAT" = ipad ]; then
  NAME=${SIM_NAME:-"iPad Pro 13-inch (M5)"}; BUNDLE=com.wsatz.SpatialDecisionRouter.pad
  APP=build/pad/Build/Products/Debug-iphonesimulator/SpatialDecisionRouter.app
  UDID=$(xcrun simctl list devices available | grep -F "$NAME (" | head -1 | grep -oE '[0-9A-F-]{36}'); SCHEME=SpatialDecisionRouterPad; DD=build/pad
else
  UDID=${SIM_UDID:-3FFE2D71-92D8-43D5-9418-7E3A2AF131F5}; BUNDLE=com.wsatz.SpatialDecisionRouter
  APP=build/Build/Products/Debug-xrsimulator/SpatialDecisionRouter.app; SCHEME=SpatialDecisionRouter; DD=build
fi
xcrun simctl boot "$UDID" 2>/dev/null; xcrun simctl bootstatus "$UDID" >/dev/null
xcodebuild -project SpatialDecisionRouter.xcodeproj -scheme $SCHEME -destination "id=$UDID" -derivedDataPath $DD build -quiet || exit 1
xcrun simctl install "$UDID" "$APP" && xcrun simctl launch --terminate-running-process "$UDID" "$BUNDLE" -demo -weriamDemo -freshRegistry "${AUTO[@]}" >/dev/null \
  && echo "✓ launched WERIAM Principal demo on $PLAT ($UDID)"
echo "check WERIAM:  PYTHONPATH=\$WERIAM_ROOT/src python3 -m weriam principal --state ~/.sdr/weriam_state && python3 -m weriam verify --state ~/.sdr/weriam_state"
