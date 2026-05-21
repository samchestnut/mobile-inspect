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
ENUMERATE=0
SNAPSHOT=""
MERGE=0
LIST_SNAPSHOTS=0
CLEAR_SNAPSHOTS=0
GEN_POM=0
EXPLORE_ZONE=""
TEMPLATE=""
LIST_TEMPLATES=0
CRAWL_APP=0
TARGET=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    android|ios) PLATFORM="$1"; shift ;;
    --raw) RAW=1; shift ;;
    --filter) FILTER="$2"; shift 2 ;;
    --suggest) SUGGEST="$2"; shift 2 ;;
    --enumerate) ENUMERATE=1; shift ;;
    --snapshot) SNAPSHOT="$2"; shift 2 ;;
    --merge) MERGE=1; shift ;;
    --snapshots) LIST_SNAPSHOTS=1; shift ;;
    --clear-snapshots) CLEAR_SNAPSHOTS=1; shift ;;
    --gen-pom) GEN_POM=1; shift ;;
    --explore-zone) EXPLORE_ZONE="$2"; shift 2 ;;
    --template) TEMPLATE="$2"; shift 2 ;;
    --list-templates) LIST_TEMPLATES=1; shift ;;
    --crawl-app) CRAWL_APP=1; shift ;;
    --target) TARGET="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SNAP_BASE="$(cd "$SCRIPT_DIR/.." && pwd)/snapshots"
sanitize() { echo "$1" | tr '[:upper:] /' '[:lower:]__' | tr -cd 'a-z0-9_.-'; }

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

# Meta actions that don't need a live device (work on saved snapshots).
if [[ "$LIST_SNAPSHOTS" == "1" ]]; then
  if [[ ! -d "$SNAP_BASE" ]]; then echo "(no snapshots yet)"; exit 0; fi
  for plat_dir in "$SNAP_BASE"/*/; do
    [[ -d "$plat_dir" ]] || continue
    plat="$(basename "$plat_dir")"
    files=("$plat_dir"*.xml)
    [[ -e "${files[0]}" ]] || continue
    echo "$plat (${#files[@]}):"
    for f in "${files[@]}"; do
      sz=$(wc -c <"$f" | tr -d ' ')
      echo "  $(basename "$f" .xml)  (${sz} bytes)"
    done
  done
  exit 0
fi

if [[ "$CLEAR_SNAPSHOTS" == "1" ]]; then
  rm -rf "$SNAP_BASE"
  echo "Cleared $SNAP_BASE"
  exit 0
fi

# --list-templates is meta — no device, no snapshots needed.
if [[ "$LIST_TEMPLATES" == "1" ]]; then
  python3 "$SCRIPT_DIR/gen-pom.py" --list-templates
  exit $?
fi

# --gen-pom is platform-agnostic: reads both ios and android snapshot dirs.
if [[ "$GEN_POM" == "1" ]]; then
  args=("$SNAP_BASE")
  [[ -n "$TEMPLATE" ]] && args+=(--template "$TEMPLATE")
  [[ -n "$TARGET" ]] && args+=(--target "$TARGET")
  [[ "$FORCE" == "1" ]] && args+=(--force)
  python3 "$SCRIPT_DIR/gen-pom.py" "${args[@]}"
  exit $?
fi

[[ -z "$PLATFORM" ]] && PLATFORM="$(detect_platform)"

# --merge: analyze saved snapshots, no live device needed once dir is populated.
if [[ "$MERGE" == "1" ]]; then
  dir="$SNAP_BASE/$PLATFORM"
  python3 "$SCRIPT_DIR/merge-snapshots.py" "$dir"
  exit $?
fi

# --snapshot <name>: dump current screen and save under snapshots/<platform>/<name>.xml
if [[ -n "$SNAPSHOT" ]]; then
  name=$(sanitize "$SNAPSHOT")
  dir="$SNAP_BASE/$PLATFORM"
  mkdir -p "$dir"
  out="$dir/$name.xml"
  case "$PLATFORM" in
    android) bash "$SCRIPT_DIR/android-dump.sh" 1 "" >"$out" ;;
    ios)     bash "$SCRIPT_DIR/ios-dump.sh"     1 "" >"$out" ;;
  esac
  if [[ ! -s "$out" ]]; then
    echo "Failed: dump was empty (device idle? app foreground?)" >&2
    rm -f "$out"
    exit 2
  fi
  bytes=$(wc -c <"$out" | tr -d ' ')
  echo "Saved snapshot: $out ($bytes bytes)"
  # Side-cars: PNG + elements.md (skip with MOBILE_INSPECT_NO_EXTRAS=1)
  bash "$SCRIPT_DIR/save-extras.sh" "$PLATFORM" "$out" || true
  echo "Run '--merge' after collecting snapshots from multiple pages."
  exit 0
fi

# When --suggest is set, force --raw so we can pipe the dump into the suggester.
if [[ -n "$SUGGEST" ]]; then
  case "$PLATFORM" in
    android) bash "$SCRIPT_DIR/android-dump.sh" 1 "" | python3 "$SCRIPT_DIR/suggest-android.py" "$SUGGEST" ;;
    ios)     bash "$SCRIPT_DIR/ios-dump.sh"     1 "" | python3 "$SCRIPT_DIR/suggest-ios.py"     "$SUGGEST" ;;
  esac
  exit $?
fi

# --enumerate also needs raw, then groups & lists named elements with PO suggestions.
if [[ "$ENUMERATE" == "1" ]]; then
  case "$PLATFORM" in
    android) bash "$SCRIPT_DIR/android-dump.sh" 1 "" | python3 "$SCRIPT_DIR/enumerate-android.py" ;;
    ios)     bash "$SCRIPT_DIR/ios-dump.sh"     1 "" | python3 "$SCRIPT_DIR/enumerate-ios.py" ;;
  esac
  exit $?
fi

# --explore-zone <top|bottom|middle>: tap each named element in zone, dump,
# diff vs home, recover. Android only for now.
if [[ -n "$EXPLORE_ZONE" ]]; then
  case "$PLATFORM" in
    android) python3 "$SCRIPT_DIR/explore-zone-android.py" "$EXPLORE_ZONE" ;;
    ios)     echo "--explore-zone not yet implemented for iOS" >&2; exit 2 ;;
  esac
  exit $?
fi

# --crawl-app: auto-snapshot home + every bottom tab + top-bar sub-screens.
# Aggregates into snapshots/android/ for downstream --merge / --gen-pom.
if [[ "$CRAWL_APP" == "1" ]]; then
  case "$PLATFORM" in
    android) python3 "$SCRIPT_DIR/crawl-app-android.py" ;;
    ios)     echo "--crawl-app not yet implemented for iOS" >&2; exit 2 ;;
  esac
  exit $?
fi

case "$PLATFORM" in
  android) bash "$SCRIPT_DIR/android-dump.sh" "$RAW" "$FILTER" ;;
  ios)     bash "$SCRIPT_DIR/ios-dump.sh"     "$RAW" "$FILTER" ;;
  *) echo "Invalid platform: $PLATFORM" >&2; exit 2 ;;
esac
