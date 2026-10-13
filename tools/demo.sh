#!/bin/bash
# One-command demo: start the Bayesian risk sidecar, (build +) install, launch the visionOS app in DEMO mode.
#   tools/demo.sh              # manual demo (click through)
#   tools/demo.sh --auto       # auto-play the 6 scripted encounters
#   tools/demo.sh --auto --record [seconds]   # also screen-record to screens/demo.mp4 (fallback if live demo fails)
set -u
cd "$(dirname "$0")/.."
UDID=${SIM_UDID:-3FFE2D71-92D8-43D5-9418-7E3A2AF131F5}; BUNDLE=com.wsatz.SpatialDecisionRouter
APP=build/Build/Products/Debug-xrsimulator/SpatialDecisionRouter.app
AUTO=""; REC=""; SECS=150
while [ $# -gt 0 ]; do case "$1" in --auto) AUTO="-demoAuto";; --record) REC=1; [[ "${2:-}" =~ ^[0-9]+$ ]] && { SECS=$2; shift; };; esac; shift; done

# 1) sidecar (localhost:8765): reuse if healthy, else start
if ! curl -s -m 1 http://127.0.0.1:8765/health >/dev/null; then
  (cd risk_engine && nohup ./run_sidecar.sh > /tmp/risk_sidecar.log 2>&1 &)
  for i in $(seq 1 40); do curl -s -m 1 http://127.0.0.1:8765/health >/dev/null && break; sleep 0.5; done
fi
if curl -s -m 1 http://127.0.0.1:8765/health; then echo; echo "✓ risk sidecar up (BN badge expected)"
else echo "⚠ risk sidecar NOT reachable — app will show 'fallback · sidecar offline' (still works)"; fi

# 2) simulator + app
xcrun simctl boot "$UDID" 2>/dev/null; open -a "$(xcode-select -p)/Applications/Simulator.app" 2>/dev/null
[ -d "$APP" ] || xcodebuild -project SpatialDecisionRouter.xcodeproj -scheme SpatialDecisionRouter -destination "id=$UDID" -derivedDataPath build build -quiet
xcrun simctl terminate "$UDID" "$BUNDLE" 2>/dev/null
xcrun simctl install "$UDID" "$APP"
(caffeinate -dimsu -t $((SECS + 60)) &)
if [ -n "$REC" ]; then
  mkdir -p screens; rm -f screens/demo.mp4
  xcrun simctl io "$UDID" recordVideo --codec=h264 --force screens/demo.mp4 & RP=$!; sleep 2
fi
xcrun simctl launch "$UDID" "$BUNDLE" -demo $AUTO -freshRegistry -speedup 1 -autoExport >/dev/null && echo "✓ launched in DEMO mode $AUTO"
if [ -n "$REC" ]; then
  sleep "$SECS"; kill -INT $RP; wait $RP 2>/dev/null
  if command -v ffmpeg >/dev/null; then   # 4K raw -> 1080p h264 (~3 MB)
    ffmpeg -y -loglevel error -i screens/demo.mp4 -vf "scale=1920:-2,fps=30" -c:v libx264 -crf 26 -preset veryfast -pix_fmt yuv420p -movflags +faststart screens/demo_1080.mp4 \
      && mv screens/demo_1080.mp4 screens/demo.mp4
  fi
  echo "✓ recorded screens/demo.mp4 (gitignored)"
fi
