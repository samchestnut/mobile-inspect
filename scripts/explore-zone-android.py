#!/usr/bin/env python3
"""Auto-explore one zone of the current screen.

Strategy:
  1. Dump current screen as the "home" reference.
  2. Auto-detect zones (top app bar / bottom nav / middle) by bounds.
  3. For the user-chosen zone, list named & deduped tap targets.
  4. For each target: tap → wait → dump → diff vs home.
       diff == 0   → log "no-op" (likely toggle/no nav)
       diff > 0    → save dump as <out_dir>/<key>.xml
     Then recover: press BACK up to MAX_BACK times until current screen
     matches home; if still off, force-stop + relaunch the package.
  5. Emit _index.md mapping element -> result + dump file.

Safety scope:
  - Only taps within the chosen zone.
  - Skips child-duplicates (same bounds as named parent).
  - Skips pure-decorative TextView (no clickable, no desc).
  - Will NOT recurse into the new screen.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# --- Config ---------------------------------------------------------------
TAP_WAIT_S = 1.5          # how long to wait after tap before re-dumping
MAX_BACK = 4              # back presses tolerated during recovery
RECOVERY_WAIT_S = 0.8

# Zone bounds (fraction of screen height). Tuned for typical mobile layouts.
TOP_FRACTION = 0.15       # top 15% = top app bar
BOTTOM_FRACTION = 0.15    # bottom 15% = bottom nav

# --- ADB helpers ----------------------------------------------------------
def adb(*args, capture=True) -> str:
    p = subprocess.run(["adb", *args], capture_output=capture, text=True)
    return p.stdout if capture else ""


def adb_dump_xml() -> str:
    """Return current UI XML."""
    adb("shell", "uiautomator", "dump", "/sdcard/mobile-inspect.xml")
    out = subprocess.run(
        ["adb", "shell", "cat", "/sdcard/mobile-inspect.xml"],
        capture_output=True, text=True, check=True,
    ).stdout
    adb("shell", "rm", "/sdcard/mobile-inspect.xml")
    return out


def adb_tap(x: int, y: int) -> None:
    adb("shell", "input", "tap", str(x), str(y))


def adb_back() -> None:
    adb("shell", "input", "keyevent", "KEYCODE_BACK")


def adb_current_package() -> str:
    """Best-effort: get the package owning the foreground window."""
    cmds = [
        ["shell", "dumpsys", "window"],
        ["shell", "dumpsys", "activity", "activities"],
    ]
    pat = re.compile(r"([a-zA-Z][a-zA-Z0-9_.]+\.[a-zA-Z][a-zA-Z0-9_.]+)/[\w$.]+")
    for c in cmds:
        out = subprocess.run(["adb", *c], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if any(k in line for k in ("mCurrentFocus", "mFocusedApp",
                                       "mResumedActivity", "topResumedActivity")):
                m = pat.search(line)
                if m:
                    return m.group(1)
    return ""


def adb_relaunch(pkg: str) -> None:
    if not pkg:
        return
    adb("shell", "am", "force-stop", pkg)
    time.sleep(0.5)
    adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(2.0)


# --- Parsing & zoning -----------------------------------------------------
BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def parse_bounds(s: str):
    m = BOUNDS_RE.match(s or "")
    return tuple(int(x) for x in m.groups()) if m else None


def screen_size_from_root(root: ET.Element):
    """Walk down looking for the largest element bounds — that's screen rect."""
    best = None
    for node in root.iter():
        b = parse_bounds(node.attrib.get("bounds", ""))
        if not b:
            continue
        area = (b[2] - b[0]) * (b[3] - b[1])
        if best is None or area > best[1]:
            best = (b, area)
    return best[0] if best else (0, 0, 1080, 1920)


def identity(node: ET.Element) -> str:
    """Return a short label for the node, or '' if it has no identity."""
    desc = node.attrib.get("content-desc", "").strip()
    rid = node.attrib.get("resource-id", "").strip()
    text = node.attrib.get("text", "").strip()
    if desc:
        return desc
    if rid:
        return rid.split("/")[-1]
    if text:
        return text
    return ""


SYSTEM_ID_SUBSTRINGS = ("statusBarBackground", "navigationBarBackground",
                        "action_bar_root", "android:id/content")


def is_pure_label(node: ET.Element) -> bool:
    cls = node.attrib.get("class", "")
    if "TextView" not in cls:
        return False
    if node.attrib.get("clickable") == "true":
        return False
    if node.attrib.get("content-desc"):
        return False
    return True


def is_system_chrome(node: ET.Element) -> bool:
    rid = node.attrib.get("resource-id", "")
    return any(s in rid for s in SYSTEM_ID_SUBSTRINGS)


def zone_for(b, screen):
    sx1, sy1, sx2, sy2 = screen
    h = sy2 - sy1
    y_mid = (b[1] + b[3]) / 2
    if y_mid < sy1 + h * TOP_FRACTION:
        return "top"
    if y_mid > sy2 - h * BOTTOM_FRACTION:
        return "bottom"
    return "middle"


def collect_targets(root: ET.Element, zone_pick: str, screen):
    """Return a deduped list of tap targets in the requested zone.

    Each entry: dict(name, bounds, center).
    Dedup rule: if a child node has bounds within 90% of an ancestor that
    already provides identity, drop the child (covers <Button-image> wrapped
    in <Button>).
    """
    candidates = []
    parent_map = {c: p for p in root.iter() for c in p}

    for node in root.iter():
        b = parse_bounds(node.attrib.get("bounds", ""))
        if not b:
            continue
        z = zone_for(b, screen)
        if z != zone_pick:
            continue
        if is_system_chrome(node):
            continue
        name = identity(node)
        if not name:
            continue
        if is_pure_label(node):
            continue
        # Filter zero-size
        if (b[2] - b[0]) < 4 or (b[3] - b[1]) < 4:
            continue
        candidates.append((node, name, b))

    cand_set = {id(n) for n, _, _ in candidates}
    cand_by_id = {id(n): (n, name, b) for n, name, b in candidates}

    def contained_in(inner, outer):
        return (outer[0] <= inner[0] and outer[1] <= inner[1]
                and outer[2] >= inner[2] and outer[3] >= inner[3])

    # Dedup: drop a node if ANY ancestor is also a candidate that contains
    # its bounds. This collapses Button + Button-image wrappers to the
    # outermost named element.
    keep = []
    seen_keys = set()
    for node, name, b in candidates:
        is_dup = False
        anc = parent_map.get(node)
        while anc is not None:
            if id(anc) in cand_set:
                _, _, ab = cand_by_id[id(anc)]
                if contained_in(b, ab):
                    is_dup = True
                    break
            anc = parent_map.get(anc)
        if is_dup:
            continue
        key = (name, b)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        keep.append({"name": name, "bounds": b,
                     "center": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)})
    return keep


# --- Diffing --------------------------------------------------------------
def screen_hash(xml_text: str) -> str:
    """Strict hash — used to detect "did anything change" after a tap."""
    if not xml_text:
        return ""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return hashlib.sha1(xml_text.encode()).hexdigest()
    sig = []
    for n in root.iter():
        sig.append("|".join([
            n.attrib.get("class", ""),
            n.attrib.get("resource-id", ""),
            n.attrib.get("content-desc", ""),
            (n.attrib.get("text", "") or "")[:40],
        ]))
    return hashlib.sha1("\n".join(sig).encode()).hexdigest()


def anchor_set(xml_text: str):
    """Stable identifiers (resource-id + content-desc) on a screen.
    Used for "are we back at home?" — robust against dynamic content
    (videos rotate, timestamps update) since we only look at named elements."""
    if not xml_text:
        return set()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return set()
    out = set()
    for n in root.iter():
        rid = n.attrib.get("resource-id", "")
        desc = n.attrib.get("content-desc", "")
        if rid:
            out.add(("id", rid))
        if desc:
            out.add(("desc", desc))
    return out


def is_back_at_home(home_anchors: set, current_xml: str, threshold: float = 0.7) -> bool:
    """True if at least <threshold> of home's named anchors are present now."""
    if not home_anchors:
        return False
    cur = anchor_set(current_xml)
    matched = len(home_anchors & cur)
    return matched / len(home_anchors) >= threshold


# --- Sanitize -------------------------------------------------------------
SAFE = re.compile(r"[^a-z0-9_.-]+")


def slug(s: str) -> str:
    s = s.lower().replace(" ", "_")
    s = SAFE.sub("_", s)
    return s.strip("_") or "elem"


# --- Main -----------------------------------------------------------------
def main(argv):
    if len(argv) < 2:
        print("Usage: explore-zone-android.py <top|bottom|middle>", file=sys.stderr)
        sys.exit(2)
    zone = argv[1]
    if zone not in ("top", "bottom", "middle"):
        print(f"Unknown zone: {zone}. Choose top|bottom|middle.", file=sys.stderr)
        sys.exit(2)

    skill_dir = Path(__file__).resolve().parent.parent
    out_root = skill_dir / "explore"
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = out_root / f"{ts}-{zone}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Capturing reference (home) screen...", file=sys.stderr)
    home_xml = adb_dump_xml()
    if not home_xml:
        print("Empty dump — is anything on screen?", file=sys.stderr)
        sys.exit(2)
    home_hash = screen_hash(home_xml)
    home_anchors = anchor_set(home_xml)
    pkg = adb_current_package()
    (out_dir / "_home.xml").write_text(home_xml)

    root = ET.fromstring(home_xml)
    screen = screen_size_from_root(root)
    print(f"Screen size: {screen}, package: {pkg or '?'}", file=sys.stderr)

    targets = collect_targets(root, zone, screen)
    if not targets:
        print(f"No tap targets found in zone '{zone}'.", file=sys.stderr)
        sys.exit(0)

    print(f"\nFound {len(targets)} target(s) in zone '{zone}':", file=sys.stderr)
    for t in targets:
        print(f"  - {t['name']}  @ {t['bounds']}", file=sys.stderr)
    print("", file=sys.stderr)

    results = []
    for i, t in enumerate(targets, 1):
        name = t["name"]
        cx, cy = t["center"]
        print(f"[{i}/{len(targets)}] tap {name}  ({cx},{cy}) ...", file=sys.stderr)
        adb_tap(cx, cy)
        time.sleep(TAP_WAIT_S)
        after_xml = adb_dump_xml()
        after_hash = screen_hash(after_xml)
        after_anchors = anchor_set(after_xml)

        # "no-op" = home anchors still all present AND no new identity surfaced
        new_anchors = after_anchors - home_anchors
        still_home = is_back_at_home(home_anchors, after_xml, threshold=0.85)

        if still_home and not new_anchors:
            print(f"    -> no-op (screen unchanged)", file=sys.stderr)
            results.append({"name": name, "result": "no-op", "file": ""})
        else:
            fname = f"{i:02d}__{slug(name)}.xml"
            (out_dir / fname).write_text(after_xml)
            tag = "modal/popup" if still_home else "new screen"
            print(f"    -> {tag} ({len(new_anchors)} new anchors), saved {fname}",
                  file=sys.stderr)
            results.append({"name": name, "result": tag, "file": fname})

            # Recover back to home.
            recovered = False
            for back in range(1, MAX_BACK + 1):
                adb_back()
                time.sleep(RECOVERY_WAIT_S)
                if is_back_at_home(home_anchors, adb_dump_xml()):
                    recovered = True
                    print(f"    -> recovered after {back} back press(es)", file=sys.stderr)
                    break
            if not recovered:
                print(f"    -> back didn't recover, force-relaunching {pkg}", file=sys.stderr)
                adb_relaunch(pkg)
                if not is_back_at_home(home_anchors, adb_dump_xml(), threshold=0.5):
                    print(f"    !! still not at home — aborting further taps",
                          file=sys.stderr)
                    results[-1]["result"] += " (recovery failed)"
                    break

    # Write index
    idx = [f"# Zone explore: `{zone}` ({ts})", "", f"Package: `{pkg}`", ""]
    idx.append(f"| # | Element | Result | Dump |")
    idx.append(f"|---|---------|--------|------|")
    for i, r in enumerate(results, 1):
        link = f"[{r['file']}]({r['file']})" if r["file"] else "—"
        idx.append(f"| {i} | `{r['name']}` | {r['result']} | {link} |")
    (out_dir / "_index.md").write_text("\n".join(idx) + "\n")
    print(f"\nDone. Index: {out_dir}/_index.md", file=sys.stderr)
    print(str(out_dir))


if __name__ == "__main__":
    main(sys.argv)
