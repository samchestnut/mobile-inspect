#!/usr/bin/env python3
"""Enumerate all named elements on the current iOS screen, grouped by type.

Reads WDA XML page source on stdin. Output is a deduplicated, grouped list
ready to paste into a Page Object class.
"""
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict


# Types worth surfacing even if name is empty (e.g. visible static text)
INTERESTING_NO_NAME_TYPES = {
    "XCUIElementTypeStaticText",
    "XCUIElementTypeTextField",
    "XCUIElementTypeSecureTextField",
}

# Types we always drop when they have no name — pure layout containers
LAYOUT_NOISE = {
    "XCUIElementTypeOther",
    "XCUIElementTypeWindow",
    "XCUIElementTypeApplication",
}


def short_type(tag: str) -> str:
    return tag.replace("XCUIElementType", "") if tag else "?"


def is_visible(el):
    return el.attrib.get("visible", "true") != "false"


def collect(root):
    """Return dict {type: {name: {label, value, count}}} of interesting elements."""
    by_type = defaultdict(dict)
    for el in root.iter():
        if not is_visible(el):
            continue
        name = el.attrib.get("name", "").strip()
        label = el.attrib.get("label", "").strip()
        value = el.attrib.get("value", "").strip()

        # Decide whether to keep
        if not name:
            # Keep StaticText / TextField even unnamed — useful for assertions
            if el.tag not in INTERESTING_NO_NAME_TYPES:
                continue
            # Use label or value as the surrogate identifier
            name = label or value
            if not name:
                continue

        if el.tag in LAYOUT_NOISE and not name:
            continue

        t = short_type(el.tag)
        bucket = by_type[t]
        if name in bucket:
            bucket[name]["count"] += 1
        else:
            bucket[name] = {
                "label": label if label != name else "",
                "value": value if value not in (name, label) else "",
                "count": 1,
            }
    return by_type


def fmt_entry(name, info):
    extras = []
    if info["count"] > 1:
        extras.append(f"x{info['count']}")
    if info["label"]:
        extras.append(f'label="{info["label"]}"')
    if info["value"]:
        extras.append(f'value="{info["value"]}"')
    suffix = f"  ({', '.join(extras)})" if extras else ""
    return f"  {name}{suffix}"


# Display order — interactive first, content next, structural last
TYPE_ORDER = [
    "Button", "Switch", "Slider", "TextField", "SecureTextField",
    "StaticText", "Image", "Cell", "CollectionView", "Table", "ScrollView",
    "NavigationBar", "TabBar", "Other",
]


def main():
    xml = sys.stdin.read()
    root = ET.fromstring(xml)
    by_type = collect(root)

    if not by_type:
        print("(no named elements found on current screen)", file=sys.stderr)
        sys.exit(1)

    total_kinds = len(by_type)
    total_elements = sum(len(b) for b in by_type.values())
    app = root.attrib.get("name", "?")
    print(f"App: {app} — {total_elements} unique named elements across {total_kinds} types\n")

    ordered = [t for t in TYPE_ORDER if t in by_type] + \
              [t for t in by_type if t not in TYPE_ORDER]

    for t in ordered:
        bucket = by_type[t]
        print(f"{t} ({len(bucket)}):")
        for name in sorted(bucket.keys()):
            print(fmt_entry(name, bucket[name]))
        print()

    # Suggested page-object skeleton
    print("// --- Suggested page-object getters (Appium iOS) ---")
    button_names = sorted(by_type.get("Button", {}).keys())
    for n in button_names[:15]:
        camel = to_camel(n) + "Btn"
        print(f'  get {camel}() {{ return $("~{n}"); }}')
    if len(button_names) > 15:
        print(f"  // ... +{len(button_names) - 15} more buttons")


def to_camel(s: str) -> str:
    parts = []
    for chunk in s.replace("-", ".").replace("_", ".").split("."):
        if not chunk:
            continue
        parts.append(chunk[0].lower() + chunk[1:] if parts == [] else chunk[0].upper() + chunk[1:])
    return "".join(parts) or "elem"


if __name__ == "__main__":
    main()
