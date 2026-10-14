#!/bin/bash
# Run the iPad (2D crossroads) build in an iPad simulator.
#   tools/ipad.sh            # start screen
#   tools/ipad.sh --demo     # straight into the scripted demo
#   tools/ipad.sh --auto     # demo, auto-play
# SIM_NAME overrides the simulator (default "iPad Pro 13-inch (M5)"). Needs the iOS 27 simulator runtime.
set -u
cd "$(dirname "$0")/.."
NAME=${SIM_NAME:-"iPad Pro 13-inch (M5)"}; BUNDLE=com.wsatz.SpatialDecisionRouter.pad
APP=build/pad/Build/Products/Debug-iphonesimulator/SpatialDecisionRouter.app
ARGS=()
case "${1:-}" in --demo) ARGS=(-demo);; --auto) ARGS=(-demo -demoAuto);; esac
UDID=$(xcrun simctl list devices available | grep -F "$NAME (" | head -1 | grep -oE '[0-9A-F-]{36}')
[ -n "$UDID" ] || UDID=$(xcrun simctl create "SDR-iPad" "com.apple.CoreSimulator.SimDeviceType.iPad-Pro-13-inch-M5-16GB")
if ! curl -s -m 1 http://127.0.0.1:8765/health >/dev/null; then
  (cd risk_engine && nohup ./run_sidecar.sh > /tmp/risk_sidecar.log 2>&1 &); sleep 4
fi
xcrun simctl boot "$UDID" 2>/dev/null; xcrun simctl bootstatus "$UDID" >/dev/null
open -a Simulator 2>/dev/null || true   # no Simulator.app on some Xcode 27 installs: use DeviceHub to view
xcodebuild -project SpatialDecisionRouter.xcodeproj -scheme SpatialDecisionRouterPad -destination "id=$UDID" -derivedDataPath build/pad build -quiet || exit 1
xcrun simctl terminate "$UDID" "$BUNDLE" 2>/dev/null
xcrun simctl install "$UDID" "$APP" && xcrun simctl launch "$UDID" "$BUNDLE" "${ARGS[@]}" && echo "✓ launched on $NAME ($UDID)"
