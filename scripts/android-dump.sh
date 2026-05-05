#!/usr/bin/env bash
# Dump Android UI tree via adb uiautomator. Args: $1=raw(0|1) $2=filter
set -euo pipefail

RAW="${1:-0}"
FILTER="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_XML="$(mktemp -t mobile-inspect-android.XXXXXX.xml)"
trap 'rm -f "$TMP_XML"' EXIT

if ! command -v adb >/dev/null 2>&1; then
  echo "adb not found. Install Android platform-tools (brew install --cask android-platform-tools)." >&2
  exit 2
fi

DEVICE_COUNT=$(adb devices | awk 'NR>1 && $2=="device"' | wc -l | tr -d ' ')
if [[ "$DEVICE_COUNT" -eq 0 ]]; then
  echo "No Android device in 'device' state. Run 'adb devices' to check." >&2
  exit 2
fi
if [[ "$DEVICE_COUNT" -gt 1 && -z "${ANDROID_SERIAL:-}" ]]; then
  echo "Multiple Android devices connected. Set ANDROID_SERIAL env var to disambiguate." >&2
  adb devices >&2
  exit 2
fi

# uiautomator dump writes to /sdcard/window_dump.xml by default; use explicit path for clarity.
adb shell uiautomator dump /sdcard/mobile-inspect.xml >/dev/null
adb pull /sdcard/mobile-inspect.xml "$TMP_XML" >/dev/null
adb shell rm /sdcard/mobile-inspect.xml >/dev/null 2>&1 || true

if [[ "$RAW" == "1" ]]; then
  cat "$TMP_XML"
  exit 0
fi

python3 "$SCRIPT_DIR/format-android.py" "$TMP_XML" "$FILTER"
