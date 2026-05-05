#!/usr/bin/env bash
# Dump iOS Simulator UI tree via WebDriverAgent (XCTest). Args: $1=raw(0|1) $2=filter
set -euo pipefail

RAW="${1:-0}"
FILTER="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WDA_DIR="${MOBILE_INSPECT_WDA_DIR:-$SKILL_DIR/wda}"
DERIVED="${MOBILE_INSPECT_WDA_DERIVED:-$SKILL_DIR/.wda-derived}"
PORT=8100
SESSION_FILE="/tmp/mobile-inspect-wda-session.txt"
PID_FILE="/tmp/mobile-inspect-wda.pid"
LOG_FILE="/tmp/mobile-inspect-wda.log"

err() { echo "$@" >&2; }

ensure_wda_setup() {
  if [[ ! -d "$WDA_DIR/WebDriverAgent.xcodeproj" ]]; then
    err "WDA not set up. Run: $SCRIPT_DIR/setup-wda.sh"
    err "(or set MOBILE_INSPECT_WDA_DIR to point at an existing WDA checkout)"
    exit 2
  fi
}

booted_sim_udid() {
  xcrun simctl list devices booted 2>/dev/null | awk -F'[()]' '/Booted/ {print $2; exit}'
}

wda_up() { curl -sf "http://localhost:$PORT/status" >/dev/null 2>&1; }

launch_wda() {
  ensure_wda_setup
  local udid="$1"
  err "Launching WDA on simulator $udid ..."
  cd "$WDA_DIR"
  ( xcodebuild test-without-building \
      -project WebDriverAgent.xcodeproj \
      -scheme WebDriverAgentRunner \
      -destination "platform=iOS Simulator,id=$udid" \
      -derivedDataPath "$DERIVED" \
      > "$LOG_FILE" 2>&1 ) &
  echo $! > "$PID_FILE"
  local i=0
  until wda_up; do
    sleep 2
    i=$((i+1))
    if [[ $i -gt 60 ]]; then
      err "WDA failed to start within 120s. Last 20 log lines:"
      tail -20 "$LOG_FILE" >&2
      exit 2
    fi
    if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      err "WDA process died. Last 20 log lines:"
      tail -20 "$LOG_FILE" >&2
      exit 2
    fi
  done
}

session_valid() {
  local sid="$1"
  curl -sf "http://localhost:$PORT/session/$sid" >/dev/null 2>&1
}

ensure_session() {
  local sid=""
  if [[ -f "$SESSION_FILE" ]]; then
    sid="$(cat "$SESSION_FILE")"
    if session_valid "$sid"; then echo "$sid"; return; fi
  fi
  sid="$(curl -s -X POST "http://localhost:$PORT/session" \
        -H 'Content-Type: application/json' \
        -d '{"capabilities":{"alwaysMatch":{"platformName":"iOS"}}}' \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('value',{}).get('sessionId',''))")"
  if [[ -z "$sid" ]]; then err "Failed to create WDA session"; exit 2; fi
  echo "$sid" > "$SESSION_FILE"
  echo "$sid"
}

# If WDA is already serving on :8100 (e.g. Appium has launched it for a real
# device, or a previous run left it running), reuse it as-is.
# Otherwise we need a booted simulator to launch our own WDA against.
if ! wda_up; then
  UDID="$(booted_sim_udid)"
  if [[ -z "$UDID" ]]; then
    err "No WDA on :8100 and no booted iOS simulator."
    err "  Real device: start Appium (or your own WDA + iproxy 8100) first."
    err "  Simulator:   boot one with 'xcrun simctl boot <name>'."
    exit 2
  fi
  launch_wda "$UDID"
fi
SID="$(ensure_session)"

XML="$(curl -sf "http://localhost:$PORT/session/$SID/source")"
if [[ -z "$XML" ]]; then err "Empty source from WDA"; exit 2; fi

# WDA wraps XML in JSON {"value":"<XML...>"}; extract the value field.
XML="$(echo "$XML" | python3 -c "import json,sys; print(json.load(sys.stdin)['value'])")"

if [[ "$RAW" == "1" ]]; then
  echo "$XML"
  exit 0
fi

echo "$XML" | python3 "$SCRIPT_DIR/format-ios.py" "$FILTER"
