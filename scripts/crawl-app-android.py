#!/usr/bin/env python3
"""Auto-crawl an Android app: snapshot home, every bottom-tab, and
top-bar-opened sub-screen on each tab. Aggregate everything into
snapshots/android/ so `--merge` and `--gen-pom` can consume the result.

Strategy:
  1. Snapshot the current screen as 'home' reference. Read target package.
  2. Detect bottom-nav tab elements (y > height - bottom_band).
  3. For each tab:
       a. Tap it, wait, verify still in target package
       b. Snapshot → save as snapshots/android/<tab_name>.xml
       c. Detect top-bar elements (y < top_band)
       d. For each top-bar element (after dedup + danger-skip):
            - Tap, wait, verify package
            - If new screen → save as snapshots/android/<tab_name>__<elem>.xml
            - BACK, fall back to relaunch if needed
       e. Relaunch app for clean state before next tab
  4. Print a summary index.

Safety scope:
  - Default = guest mode. We never log in. We never type into forms.
  - We never tap elements whose name matches danger keywords
    (Create/Upload/Camera/Record/Pay/Delete/SignOut/Subscribe/Buy).
  - If a tap navigates outside the app (different package), we BACK and skip.
  - We never recurse below the top-bar level.
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

# --- Tunables ---------------------------------------------------------------
TAP_WAIT_S = 1.5
RECOVERY_WAIT_S = 0.8
MAX_BACK = 4
RELAUNCH_WAIT_S = 3.0
TOP_FRACTION = 0.15
BOTTOM_FRACTION = 0.15
ANCHOR_RECOVERY_THRESHOLD = 0.7

# Don't tap things that likely create user-visible side effects, log out, or
# launch external apps. Substring match (case-insensitive) on element name/id.
DANGER_KEYWORDS = (
    "create", "upload", "publish", "record", "camera", "photo", "video record",
    "pay", "payment", "checkout", "subscribe", "donate", "purchase", "buy ",
    "delete", "remove", "clear", "reset", "wipe",
    "sign out", "signout", "logout", "log out",
    "share to", "open with", "external",
)

# System chrome to ignore at the parsing step.
SYSTEM_ID_SUBSTRINGS = (
    "statusBarBackground", "navigationBarBackground",
    "action_bar_root", "android:id/content",
)

BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


# --- ADB helpers ------------------------------------------------------------
def adb(*args, capture=True) -> str:
    r = subprocess.run(["adb", *args], capture_output=capture, text=True)
    return r.stdout if capture else ""


def adb_dump_xml() -> str:
    adb("shell", "uiautomator", "dump", "/sdcard/mobile-inspect.xml")
    out = subprocess.run(
        ["adb", "shell", "cat", "/sdcard/mobile-inspect.xml"],
        capture_output=True, text=True, check=True,
    ).stdout
    adb("shell", "rm", "/sdcard/mobile-inspect.xml")
    return out


def adb_tap(x: int, y: int):
    adb("shell", "input", "tap", str(x), str(y))


def adb_back():
    adb("shell", "input", "keyevent", "KEYCODE_BACK")


def adb_current_package() -> str:
    pat = re.compile(r"([a-zA-Z][a-zA-Z0-9_.]+\.[a-zA-Z][a-zA-Z0-9_.]+)/[\w$.]+")
    for cmd in (["shell", "dumpsys", "window"],
                ["shell", "dumpsys", "activity", "activities"]):
        out = subprocess.run(["adb", *cmd], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if any(k in line for k in ("mCurrentFocus", "mFocusedApp",
                                       "mResumedActivity", "topResumedActivity")):
                m = pat.search(line)
                if m:
                    return m.group(1)
    return ""


def adb_relaunch(pkg: str):
    if not pkg:
        return
    adb("shell", "am", "force-stop", pkg)
    time.sleep(0.5)
    adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(RELAUNCH_WAIT_S)


# --- XML helpers ------------------------------------------------------------
def parse_bounds(s: str):
    m = BOUNDS_RE.match(s or "")
    return tuple(int(x) for x in m.groups()) if m else None


def screen_size_from_root(root: ET.Element):
    best = None
    for n in root.iter():
        b = parse_bounds(n.attrib.get("bounds", ""))
        if not b:
            continue
        area = (b[2] - b[0]) * (b[3] - b[1])
        if best is None or area > best[1]:
            best = (b, area)
    return best[0] if best else (0, 0, 1080, 1920)


def identity(node: ET.Element) -> str:
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


def is_danger(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in DANGER_KEYWORDS)


def anchor_set(xml_text: str):
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


def matches_anchors(home_anchors: set, current_xml: str, threshold: float) -> bool:
    if not home_anchors:
        return False
    cur = anchor_set(current_xml)
    return len(home_anchors & cur) / len(home_anchors) >= threshold


def collect_zone_targets(root: ET.Element, zone: str, screen):
    """Pick named, non-system, non-label, deduped elements in a zone."""
    sx1, sy1, sx2, sy2 = screen
    h = sy2 - sy1
    parent_map = {c: p for p in root.iter() for c in p}

    candidates = []
    for n in root.iter():
        b = parse_bounds(n.attrib.get("bounds", ""))
        if not b:
            continue
        y_mid = (b[1] + b[3]) / 2
        if zone == "top" and y_mid >= sy1 + h * TOP_FRACTION:
            continue
        if zone == "bottom" and y_mid <= sy2 - h * BOTTOM_FRACTION:
            continue
        if is_system_chrome(n):
            continue
        name = identity(n)
        if not name:
            continue
        if is_pure_label(n):
            continue
        if (b[2] - b[0]) < 4 or (b[3] - b[1]) < 4:
            continue
        candidates.append((n, name, b))

    cand_set = {id(n) for n, _, _ in candidates}
    cand_by_id = {id(n): (name, b) for n, name, b in candidates}

    def contained(inner, outer):
        return (outer[0] <= inner[0] and outer[1] <= inner[1]
                and outer[2] >= inner[2] and outer[3] >= inner[3])

    keep = []
    seen = set()
    for n, name, b in candidates:
        is_dup = False
        anc = parent_map.get(n)
        while anc is not None:
            if id(anc) in cand_set:
                _, ab = cand_by_id[id(anc)]
                if contained(b, ab):
                    is_dup = True
                    break
            anc = parent_map.get(anc)
        if is_dup:
            continue
        key = (name, b)
        if key in seen:
            continue
        seen.add(key)
        keep.append({"name": name, "bounds": b,
                     "center": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)})
    return keep


# --- Sanitize ---------------------------------------------------------------
SAFE = re.compile(r"[^a-z0-9_.-]+")


def slug(s: str) -> str:
    s = s.lower().replace(" ", "_")
    return SAFE.sub("_", s).strip("_") or "elem"


# --- Main -------------------------------------------------------------------
def main():
    skill_dir = Path(__file__).resolve().parent.parent
    snap_dir = skill_dir / "snapshots" / "android"
    snap_dir.mkdir(parents=True, exist_ok=True)

    print("[1/4] Snapshot home + detect package...", file=sys.stderr)
    home_xml = adb_dump_xml()
    if not home_xml:
        print("Empty dump — is the app on screen?", file=sys.stderr)
        sys.exit(2)

    pkg = adb_current_package()
    if not pkg:
        print("Could not detect target package. Is the app foreground?", file=sys.stderr)
        sys.exit(2)
    print(f"  package: {pkg}", file=sys.stderr)

    home_root = ET.fromstring(home_xml)
    screen = screen_size_from_root(home_root)
    home_anchors = anchor_set(home_xml)
    (snap_dir / "home.xml").write_text(home_xml)
    print(f"  saved snapshots/android/home.xml ({len(home_xml)//1024}KB)", file=sys.stderr)

    # Detect bottom tabs
    tabs = collect_zone_targets(home_root, "bottom", screen)
    if not tabs:
        print("No bottom-nav tabs detected. App may not have a tab bar.",
              file=sys.stderr)
    print(f"\n[2/4] Found {len(tabs)} bottom tabs:", file=sys.stderr)
    for t in tabs:
        print(f"  - {t['name']}", file=sys.stderr)

    summary = {"tabs": [], "subscreens": []}

    print(f"\n[3/4] Crawling tabs (top-bar exploration per tab)...\n", file=sys.stderr)
    for ti, tab in enumerate(tabs, 1):
        tname = tab["name"]
        if is_danger(tname):
            print(f"  [tab {ti}] SKIP {tname} (danger keyword)", file=sys.stderr)
            continue

        adb_relaunch(pkg)  # clean state between tabs
        cx, cy = tab["center"]
        print(f"  [tab {ti}/{len(tabs)}] tap {tname} ({cx},{cy})", file=sys.stderr)
        adb_tap(cx, cy)
        time.sleep(TAP_WAIT_S)

        if adb_current_package() != pkg:
            print(f"    ! navigated outside app, BACK + skip", file=sys.stderr)
            adb_back(); time.sleep(0.5)
            continue

        tab_xml = adb_dump_xml()
        slug_name = slug(tname)
        tab_file = snap_dir / f"{slug_name}.xml"
        tab_file.write_text(tab_xml)
        summary["tabs"].append({"name": tname, "file": tab_file.name})
        print(f"    saved {tab_file.name}", file=sys.stderr)

        # Explore top-bar from this tab
        tab_root = ET.fromstring(tab_xml)
        tab_anchors = anchor_set(tab_xml)
        top_targets = collect_zone_targets(tab_root, "top", screen)
        # Drop the tab name itself if it appears in the top zone too
        top_targets = [t for t in top_targets if t["name"] != tname]
        if not top_targets:
            print(f"    (no top-bar elements to explore)", file=sys.stderr)
            continue
        print(f"    top-bar has {len(top_targets)} candidates", file=sys.stderr)

        for ei, elem in enumerate(top_targets, 1):
            ename = elem["name"]
            if is_danger(ename):
                print(f"      [{ei}] SKIP {ename} (danger)", file=sys.stderr)
                continue
            ex, ey = elem["center"]
            print(f"      [{ei}/{len(top_targets)}] tap {ename} ({ex},{ey})",
                  file=sys.stderr)
            adb_tap(ex, ey)
            time.sleep(TAP_WAIT_S)

            if adb_current_package() != pkg:
                print(f"        -> outside app, BACK + skip", file=sys.stderr)
                adb_back(); time.sleep(0.5)
                if adb_current_package() != pkg:
                    adb_relaunch(pkg)
                continue

            after_xml = adb_dump_xml()
            after_anchors = anchor_set(after_xml)
            new_anchors = after_anchors - tab_anchors
            still_tab = matches_anchors(tab_anchors, after_xml, threshold=0.85)

            if still_tab and not new_anchors:
                print(f"        -> no-op", file=sys.stderr)
            else:
                fname = f"{slug_name}__{slug(ename)}.xml"
                (snap_dir / fname).write_text(after_xml)
                summary["subscreens"].append({"tab": tname, "elem": ename,
                                              "file": fname,
                                              "kind": "modal" if still_tab else "screen"})
                print(f"        -> saved {fname}", file=sys.stderr)

                # Recover back to tab
                recovered = False
                for back in range(1, MAX_BACK + 1):
                    adb_back()
                    time.sleep(RECOVERY_WAIT_S)
                    if matches_anchors(tab_anchors, adb_dump_xml(), threshold=0.7):
                        recovered = True
                        break
                if not recovered:
                    print(f"        ! back failed, relaunching {pkg}", file=sys.stderr)
                    adb_relaunch(pkg)
                    # We've lost the tab context; stop top-bar loop
                    break

    # Final summary
    print(f"\n[4/4] Done.", file=sys.stderr)
    summary_md = ["# Crawl summary",
                  f"- Package: `{pkg}`",
                  f"- Snapshots dir: `{snap_dir}`",
                  f"- Tabs crawled: {len(summary['tabs'])}",
                  f"- Sub-screens captured: {len(summary['subscreens'])}",
                  ""]
    summary_md.append("## Tabs")
    for t in summary["tabs"]:
        summary_md.append(f"- `{t['file']}` — {t['name']}")
    summary_md.append("\n## Sub-screens")
    for s in summary["subscreens"]:
        summary_md.append(f"- `{s['file']}` — tab=**{s['tab']}**, opened by **{s['elem']}** ({s['kind']})")

    out = snap_dir / "_crawl_summary.md"
    out.write_text("\n".join(summary_md) + "\n")
    print(f"  summary: {out}", file=sys.stderr)
    print(f"\nNext: run `--merge` to dedupe across pages, then `--gen-pom`.",
          file=sys.stderr)
    print(str(snap_dir))


if __name__ == "__main__":
    main()
