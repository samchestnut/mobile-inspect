#!/usr/bin/env python3
"""Produce a Markdown summary of named elements on a screen, from an XML dump.

Usage: elements-summary.py <android|ios> <xml-path>

Output schema (per row):
  | # | Name | Type | Bounds | Tappable |
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def short_type(cls: str) -> str:
    if not cls:
        return "?"
    if cls.startswith("XCUIElementType"):
        return cls.replace("XCUIElementType", "")
    return cls.rsplit(".", 1)[-1]


def parse_bounds(s: str):
    m = BOUNDS_RE.match(s or "")
    return tuple(int(x) for x in m.groups()) if m else None


def parse_ios_frame(node: ET.Element):
    """iOS WDA uses x/y/width/height attribs, not bounds=."""
    try:
        x = int(float(node.attrib.get("x", 0)))
        y = int(float(node.attrib.get("y", 0)))
        w = int(float(node.attrib.get("width", 0)))
        h = int(float(node.attrib.get("height", 0)))
        if w and h:
            return (x, y, x + w, y + h)
    except (ValueError, TypeError):
        pass
    return None


def collect_android(root: ET.Element):
    out = []
    for n in root.iter():
        rid = n.attrib.get("resource-id", "").strip()
        desc = n.attrib.get("content-desc", "").strip()
        text = n.attrib.get("text", "").strip()
        name = desc or (rid.split("/")[-1] if rid else "") or text
        if not name:
            continue
        b = parse_bounds(n.attrib.get("bounds", ""))
        if not b or (b[2] - b[0]) < 4 or (b[3] - b[1]) < 4:
            continue
        out.append({
            "name": name,
            "type": short_type(n.attrib.get("class", "")),
            "bounds": f"[{b[0]},{b[1]}][{b[2]},{b[3]}]",
            "tappable": n.attrib.get("clickable", "false") == "true",
        })
    return out


def collect_ios(root: ET.Element):
    out = []
    for n in root.iter():
        if n.attrib.get("visible", "true") == "false":
            continue
        name = n.attrib.get("name", "").strip()
        label = n.attrib.get("label", "").strip()
        display = name or label
        if not display:
            continue
        b = parse_ios_frame(n)
        if not b or (b[2] - b[0]) < 4 or (b[3] - b[1]) < 4:
            continue
        out.append({
            "name": display,
            "type": short_type(n.tag),
            "bounds": f"[{b[0]},{b[1]}][{b[2]},{b[3]}]",
            "tappable": n.attrib.get("type", "") in ("Button",) or n.tag.endswith("Button"),
        })
    return out


def dedup(items):
    """Drop exact (name, bounds) duplicates while preserving order."""
    seen = set()
    kept = []
    for it in items:
        key = (it["name"], it["bounds"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(it)
    return kept


def main():
    if len(sys.argv) < 3:
        print("Usage: elements-summary.py <android|ios> <xml-path>", file=sys.stderr)
        sys.exit(2)
    plat, xml_path = sys.argv[1], Path(sys.argv[2])
    try:
        root = ET.fromstring(xml_path.read_text())
    except (FileNotFoundError, ET.ParseError) as e:
        print(f"Failed to parse XML: {e}", file=sys.stderr)
        sys.exit(1)

    items = collect_ios(root) if plat == "ios" else collect_android(root)
    items = dedup(items)

    title = xml_path.stem
    print(f"# Elements — `{title}` ({plat})\n")
    print(f"**Total named elements:** {len(items)}\n")
    if not items:
        print("_(no named elements detected)_")
        return

    print("| # | Name | Type | Bounds | Tap |")
    print("|---|------|------|--------|-----|")
    for i, it in enumerate(items, 1):
        tap = "✅" if it["tappable"] else "—"
        # Escape pipes in name (rare)
        nm = it["name"].replace("|", "\\|")
        print(f"| {i} | `{nm}` | {it['type']} | `{it['bounds']}` | {tap} |")


if __name__ == "__main__":
    main()
