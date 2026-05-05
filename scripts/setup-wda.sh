#!/usr/bin/env bash
# One-time setup: clone WebDriverAgent into the skill folder and pre-build it.
# Idempotent — re-running is safe.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WDA_DIR="$SKILL_DIR/wda"
DERIVED="$SKILL_DIR/.wda-derived"

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "xcodebuild not found. Install Xcode (full IDE, not just CLI tools) from the App Store." >&2
  exit 2
fi

if [[ ! -d "$WDA_DIR/.git" ]]; then
  echo "Cloning appium/WebDriverAgent into $WDA_DIR ..."
  git clone --depth 1 https://github.com/appium/WebDriverAgent.git "$WDA_DIR"
else
  echo "WDA already cloned at $WDA_DIR (skip)"
fi

# Pick first booted simulator for the build target. If none, fall back to a generic destination.
SIM_UDID=$(xcrun simctl list devices booted 2>/dev/null | awk -F'[()]' '/Booted/ {print $2; exit}')
if [[ -n "$SIM_UDID" ]]; then
  DEST="platform=iOS Simulator,id=$SIM_UDID"
else
  DEST="generic/platform=iOS Simulator"
fi

echo "Building WebDriverAgentRunner against: $DEST"
cd "$WDA_DIR"
xcodebuild build-for-testing \
  -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination "$DEST" \
  -derivedDataPath "$DERIVED" \
  -quiet

echo
echo "WDA setup complete."
echo "  WDA source : $WDA_DIR"
echo "  Build cache: $DERIVED"
echo "Next time you run mobile-inspect on iOS, it will launch WDA automatically (~10s)."
