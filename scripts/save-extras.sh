#!/usr/bin/env bash
# Save PNG screenshot + elements.md summary alongside an XML dump.
# Usage: save-extras.sh <platform> <xml_path>
#
# Outputs (sibling to xml_path):
#   <basename>.png             - screenshot of the current screen
#   <basename>.elements.md     - markdown table of named elements
#
# Skip with: MOBILE_INSPECT_NO_EXTRAS=1
set -euo pipefail

if [[ "${MOBILE_INSPECT_NO_EXTRAS:-0}" == "1" ]]; then
  exit 0
fi

PLATFORM="${1:-}"
XML_PATH="${2:-}"
[[ -z "$PLATFORM" || -z "$XML_PATH" || ! -f "$XML_PATH" ]] && exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$(dirname "$XML_PATH")"
BASE="$(basename "$XML_PATH" .xml)"
PNG="$DIR/$BASE.png"
MD="$DIR/$BASE.elements.md"

# --- Screenshot --------------------------------------------------------------
case "$PLATFORM" in
  android)
    # adb screencap writes binary PNG to stdout (need -p flag + strip CRLF on some hosts)
    adb shell screencap -p 2>/dev/null | perl -pe 's/\x0D\x0A/\x0A/g' > "$PNG" 2>/dev/null \
      || echo "  ! screenshot failed" >&2
    ;;
  ios)
    # Reuse existing iOS screenshot path if WDA session is live.
    SID_FILE="/tmp/mobile-inspect-wda-session.txt"
    PORT="${MOBILE_INSPECT_WDA_PORT:-8100}"
    if [[ -f "$SID_FILE" ]]; then
      SID="$(cat "$SID_FILE")"
      curl -sf "http://localhost:$PORT/session/$SID/screenshot" \
        | python3 -c "import base64,json,sys,pathlib; raw=json.load(sys.stdin).get('value','') or ''; pathlib.Path('$PNG').write_bytes(base64.b64decode(raw))" \
        2>/dev/null || echo "  ! screenshot failed (WDA)" >&2
    fi
    ;;
esac

# --- Elements summary --------------------------------------------------------
python3 "$SCRIPT_DIR/elements-summary.py" "$PLATFORM" "$XML_PATH" > "$MD" 2>/dev/null \
  || echo "  ! elements summary failed" >&2

# Brief log
sz_png="-"; sz_md="-"
[[ -f "$PNG" ]] && sz_png="$(wc -c <"$PNG" | tr -d ' ') bytes"
[[ -f "$MD"  ]] && sz_md="$(wc -l <"$MD"  | tr -d ' ') lines"
echo "  + extras: $BASE.png ($sz_png), $BASE.elements.md ($sz_md)" >&2
