#!/bin/bash
# Symbiosis demo (M1 slice): seeded three-column cards (ED triage + personal finance), dual labels, manifesto.
#   tools/symbiosis_demo.sh [--ipad|--vision] [--auto] [--fresh-ledger] [--export]
#   M3: pass-through spot-check knobs via SDR_SHARP="-sharpRate 0.5" (or -sharpEvery N, -sharpDetail 85)
#   --import=DIR : also load personal-finance items from tools/import_cases.py output (-importItems DIR)
#   --export : after the run, pull the app's signed ledger and run tools/unified_export.py into build/symbiosis_export
# No bridge or LLM needed. All content is SYNTHETIC.
set -u
cd "$(dirname "$0")/.."
PLAT=ipad; AUTO=(); FRESH=(); EXPORT=""; IMPORT=()
for a in "$@"; do case "$a" in --ipad) PLAT=ipad;; --vision) PLAT=vision;; --auto) AUTO=(-demoAuto -speedup 3);; --fresh-ledger) FRESH=(-freshLedger);; --export) EXPORT=1;; --import=*) IMPORT=(-importItems "$(cd "${a#--import=}" && pwd)");; esac; done
if [ "$PLAT" = ipad ]; then
  NAME=${SIM_NAME:-"iPad Pro 13-inch (M5)"}; BUNDLE=com.wsatz.SpatialHITM.pad
  APP=build/pad/Build/Products/Debug-iphonesimulator/SpatialHITM.app
  UDID=$(xcrun simctl list devices available | grep -F "$NAME (" | head -1 | grep -oE '[0-9A-F-]{36}'); SCHEME=SpatialDecisionRouterPad; DD=build/pad
else
  UDID=${SIM_UDID:-3FFE2D71-92D8-43D5-9418-7E3A2AF131F5}; BUNDLE=com.wsatz.SpatialHITM
  APP=build/Build/Products/Debug-xrsimulator/SpatialHITM.app; SCHEME=SpatialHITM; DD=build
fi
xcrun simctl boot "$UDID" 2>/dev/null; xcrun simctl bootstatus "$UDID" >/dev/null
xcodebuild -project SpatialDecisionRouter.xcodeproj -scheme $SCHEME -destination "id=$UDID" -derivedDataPath $DD build -quiet || exit 1
EXTRA=(-hideSidebar); [ "$PLAT" = vision ] && EXTRA=(-autoOpenImmersive)
xcrun simctl install "$UDID" "$APP" && xcrun simctl launch --terminate-running-process "$UDID" "$BUNDLE" -demo -symbiosisDemo -freshRegistry -noBridge \
  "${EXTRA[@]}" ${AUTO[@]+"${AUTO[@]}"} ${FRESH[@]+"${FRESH[@]}"} ${IMPORT[@]+"${IMPORT[@]}"} ${SDR_SHARP:-} >/dev/null && echo "✓ launched Symbiosis demo on $PLAT ($UDID)"
if [ -n "$EXPORT" ]; then
  echo "waiting 100 s for the auto-play to finish…"; sleep 100
  D=$(xcrun simctl get_app_container "$UDID" "$BUNDLE" data)
  python3 tools/unified_export.py "$D/Documents/decisions/decision_ledger.jsonl" -o build/symbiosis_export --replay-name symbiosis-demo --strict
fi
