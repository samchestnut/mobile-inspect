#!/usr/bin/env python3
"""Analyze a folder of snapshot XMLs and classify elements as shared vs page-specific.

Usage: merge-snapshots.py <platform-snapshots-dir>

Output: Markdown-style report showing which elements appear on ≥2 pages
(basePage candidates) and which are page-specific.
"""
import sys
import os
import xml.etree.ElementTree as ET
from collections import defaultdict


def short_type_ios(tag: str) -> str:
    return tag.replace("XCUIElementType", "") if tag else "?"


def short_class_android(cls: str) -> str:
    return cls.rsplit(".", 1)[-1] if cls else "?"


def extract_ios(xml: str):
    """Return list of (type, name) for each named element."""
    root = ET.fromstring(xml)
    out = []
    for el in root.iter():
        if el.attrib.get("visible", "true") == "false":
            continue
        name = el.attrib.get("name", "").strip()
        if not name:
            continue
        # Drop pure layout containers without distinct identity
        if el.tag in ("XCUIElementTypeApplication", "XCUIElementTypeWindow"):
            continue
        out.append((short_type_ios(el.tag), name))
    return out


def extract_android(xml: str):
    """Return list of (class, key) where key = resource-id last segment or content-desc."""
    root = ET.fromstring(xml)
    out = []
    for el in root.iter():
        rid = el.attrib.get("resource-id", "").strip()
        desc = el.attrib.get("content-desc", "").strip()
        cls = short_class_android(el.attrib.get("class", ""))
        if rid:
            out.append((cls, rid.split("/")[-1]))
        elif desc:
            out.append((cls, desc))
    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: merge-snapshots.py <snapshots-dir>", file=sys.stderr)
        sys.exit(2)
    snap_dir = sys.argv[1]
    if not os.path.isdir(snap_dir):
        print(f"Snapshots dir not found: {snap_dir}", file=sys.stderr)
        sys.exit(2)

    is_ios = "ios" in os.path.basename(snap_dir.rstrip("/"))
    extract = extract_ios if is_ios else extract_android

    snapshots = sorted(f for f in os.listdir(snap_dir) if f.endswith(".xml"))
    if not snapshots:
        print("No snapshots found. Take some with: inspect.sh <platform> --snapshot <name>",
              file=sys.stderr)
        sys.exit(1)

    # element_key -> set of page names
    presence = defaultdict(set)
    # page name -> count of named elements on that page
    page_counts = {}

    for fname in snapshots:
        page = fname[:-4]  # strip .xml
        with open(os.path.join(snap_dir, fname)) as f:
            xml = f.read()
        try:
            elems = extract(xml)
        except ET.ParseError as e:
            print(f"  ! could not parse {fname}: {e}", file=sys.stderr)
            continue
        # Dedup within a page
        unique = set(elems)
        page_counts[page] = len(unique)
        for key in unique:
            presence[key].add(page)

    pages = [s[:-4] for s in snapshots]
    total_pages = len(pages)

    print(f"Loaded {total_pages} snapshots: {', '.join(pages)}\n")

    # Classify
    shared = [(k, v) for k, v in presence.items() if len(v) >= 2]
    specific = defaultdict(list)
    for k, v in presence.items():
        if len(v) == 1:
            specific[next(iter(v))].append(k)

    # === Cross-page (basePage candidates) ===
    if shared:
        print(f"🌐 Cross-page elements ({len(shared)}) — basePage candidates:\n")
        # Sort by coverage desc, then by name
        shared.sort(key=lambda kv: (-len(kv[1]), kv[0][1]))
        for (typ, name), where in shared:
            coverage = f"{len(where)}/{total_pages}"
            pages_list = ", ".join(sorted(where))
            print(f"  {typ:18} {name:40} [{coverage}]  {pages_list}")
        print()
    else:
        print("🌐 No cross-page elements found (need ≥2 snapshots that share an element).\n")

    # === Page-specific ===
    print("📄 Page-specific elements:")
    for page in pages:
        items = specific.get(page, [])
        if not items:
            print(f"  {page} ({page_counts.get(page, 0)} total, 0 unique to this page)")
            continue
        items.sort(key=lambda x: (x[0], x[1]))
        print(f"  {page} ({len(items)} unique):")
        # Group by type for readability
        by_type = defaultdict(list)
        for typ, name in items:
            by_type[typ].append(name)
        for typ in sorted(by_type.keys()):
            names = by_type[typ]
            preview = ", ".join(names[:6])
            if len(names) > 6:
                preview += f", … (+{len(names)-6} more)"
            print(f"    {typ}: {preview}")
        print()

    # === Summary ===
    total_unique = len(presence)
    print(f"Summary: {total_unique} unique elements — "
          f"{len(shared)} shared, {sum(len(v) for v in specific.values())} page-specific")


if __name__ == "__main__":
    main()
