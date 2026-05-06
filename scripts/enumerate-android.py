#!/usr/bin/env python3
"""Enumerate all named elements on the current Android screen, grouped by widget class.

Reads uiautomator XML on stdin. Output is a deduplicated, grouped list
ready to paste into a Page Object class.
"""
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict


def short_class(cls: str) -> str:
    return cls.rsplit(".", 1)[-1] if cls else "?"


def collect(root):
    """Return dict {class: {key: {kind, text, count}}} where key is the strongest
    available identifier (resource-id last segment, or content-desc, or text)."""
    by_class = defaultdict(dict)
    for el in root.iter():
        rid = el.attrib.get("resource-id", "").strip()
        desc = el.attrib.get("content-desc", "").strip()
        text = el.attrib.get("text", "").strip()
        cls = short_class(el.attrib.get("class", ""))

        # Skip elements with no usable identifier
        if not (rid or desc):
            # Keep TextView / EditText with text as content surrogate
            if cls not in ("TextView", "EditText", "Button") or not text:
                continue

        # Pick the strongest identifier
        if rid:
            key = rid.split("/")[-1]
            kind = "id"
        elif desc:
            key = desc
            kind = "desc"
        else:
            key = text
            kind = "text"

        bucket = by_class[cls]
        if key in bucket:
            bucket[key]["count"] += 1
        else:
            bucket[key] = {
                "kind": kind,
                "text": text if (text and text != key) else "",
                "desc": desc if (desc and desc != key and kind != "desc") else "",
                "count": 1,
            }
    return by_class


def fmt_entry(key, info):
    extras = [info["kind"]]
    if info["count"] > 1:
        extras.append(f"x{info['count']}")
    if info["text"]:
        extras.append(f'text="{info["text"]}"')
    if info["desc"]:
        extras.append(f'desc="{info["desc"]}"')
    return f"  {key}  ({', '.join(extras)})"


CLASS_ORDER = [
    "Button", "ImageButton", "EditText", "Switch", "CheckBox",
    "TextView", "ImageView", "RecyclerView", "ListView",
    "ViewGroup", "FrameLayout", "LinearLayout", "RelativeLayout",
]


def main():
    xml = sys.stdin.read()
    root = ET.fromstring(xml)
    by_class = collect(root)

    if not by_class:
        print("(no identifiable elements found on current screen)", file=sys.stderr)
        sys.exit(1)

    total_kinds = len(by_class)
    total_elements = sum(len(b) for b in by_class.values())
    print(f"{total_elements} unique identifiable elements across {total_kinds} widget types\n")

    ordered = [c for c in CLASS_ORDER if c in by_class] + \
              [c for c in by_class if c not in CLASS_ORDER]

    for cls in ordered:
        bucket = by_class[cls]
        print(f"{cls} ({len(bucket)}):")
        for k in sorted(bucket.keys()):
            print(fmt_entry(k, bucket[k]))
        print()

    # Suggested page-object skeleton (id-based first, desc fallback)
    print("// --- Suggested page-object getters (Appium Android) ---")
    suggestions = []
    for cls, bucket in by_class.items():
        for key, info in bucket.items():
            if info["kind"] == "id":
                suggestions.append((key, "id", cls))
            elif info["kind"] == "desc":
                suggestions.append((key, "desc", cls))
    suggestions.sort(key=lambda s: (s[1] != "id", s[0]))  # ids first
    for key, kind, cls in suggestions[:15]:
        camel = to_camel(key)
        if kind == "id":
            print(f'  get {camel}() {{ return $(\'android=new UiSelector().resourceIdMatches(".*:id/{key}")\'); }}')
        else:
            print(f'  get {camel}() {{ return $("~{key}"); }}')
    if len(suggestions) > 15:
        print(f"  // ... +{len(suggestions) - 15} more")


def to_camel(s: str) -> str:
    parts = []
    for chunk in s.replace("-", ".").replace("_", ".").split("."):
        if not chunk:
            continue
        parts.append(chunk[0].lower() + chunk[1:] if parts == [] else chunk[0].upper() + chunk[1:])
    return "".join(parts) or "elem"


if __name__ == "__main__":
    main()
