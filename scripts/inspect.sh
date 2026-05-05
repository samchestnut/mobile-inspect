#!/usr/bin/env bash
# mobile-inspect entry point.
# Usage:
#   inspect.sh [android|ios] [--raw] [--filter <substr>] [--suggest <query>]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PLATFORM=""
RAW=0
FILTER=""
SUGGEST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    android|ios) PLATFORM="$1"; shift ;;
    --raw) RAW=1; shift ;;
    --filter) FILTER="$2"; shift 2 ;;
    --suggest) SUGGEST="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

detect_platform() {
  local has_android=0 has_ios=0
  if command -v adb >/dev/null 2>&1; then
    if adb devices | awk 'NR>1 && $2=="device"' | grep -q .; then has_android=1; fi
  fi
  if xcrun simctl list devices booted 2>/dev/null | grep -q "Booted"; then has_ios=1; fi
  if [[ $has_android -eq 1 && $has_ios -eq 1 ]]; then
    echo "Both Android device and iOS simulator detected. Pass 'android' or 'ios' explicitly." >&2
    exit 2
  fi
  if [[ $has_android -eq 1 ]]; then echo "android"; return; fi
  if [[ $has_ios -eq 1 ]]; then echo "ios"; return; fi
  echo "No connected Android device or booted iOS simulator found." >&2
  exit 2
}

[[ -z "$PLATFORM" ]] && PLATFORM="$(detect_platform)"

# When --suggest is set, force --raw so we can pipe the dump into the suggester.
if [[ -n "$SUGGEST" ]]; then
  case "$PLATFORM" in
    android) bash "$SCRIPT_DIR/android-dump.sh" 1 "" | python3 "$SCRIPT_DIR/suggest-android.py" "$SUGGEST" ;;
    ios)     bash "$SCRIPT_DIR/ios-dump.sh"     1 "" | python3 "$SCRIPT_DIR/suggest-ios.py"     "$SUGGEST" ;;
  esac
  exit $?
fi

case "$PLATFORM" in
  android) bash "$SCRIPT_DIR/android-dump.sh" "$RAW" "$FILTER" ;;
  ios)     bash "$SCRIPT_DIR/ios-dump.sh"     "$RAW" "$FILTER" ;;
  *) echo "Invalid platform: $PLATFORM" >&2; exit 2 ;;
esac
