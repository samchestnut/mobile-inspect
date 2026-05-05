#!/usr/bin/env python3
"""Format WDA (XCTest) XML page source as a compact indented tree.

Input: stdin XML, e.g.
  <XCUIElementTypeApplication ...>
    <XCUIElementTypeWindow ...>
      <XCUIElementTypeImage name="icon-subtitle-off" .../>
    </XCUIElementTypeWindow>
  </XCUIElementTypeApplication>
"""
import sys
import xml.etree.ElementTree as ET


def short_type(tag: str) -> str:
    return tag.replace("XCUIElementType", "") if tag else "?"


def fmt_node(el: ET.Element) -> str:
    parts = [short_type(el.tag)]
    extras = []
    a = el.attrib
    name = a.get("name", "")
    if name:
        extras.append(f'name="{name}"')
    label = a.get("label", "")
    if label and label != name:
        extras.append(f'label="{label}"')
    value = a.get("value", "")
    if value and value != name and value != label:
        extras.append(f'value="{value}"')
    x, y, w, h = a.get("x"), a.get("y"), a.get("width"), a.get("height")
    if x and y and w and h:
        extras.append(f"frame={x},{y},{w}x{h}")
    if a.get("visible") == "false":
        extras.append("hidden")
    if a.get("enabled") == "false":
        extras.append("disabled")
    if extras:
        parts.append("[" + ", ".join(extras) + "]")
    return " ".join(parts)


def matches(el: ET.Element, needle: str) -> bool:
    needle = needle.lower()
    if needle in el.tag.lower():
        return True
    for k in ("name", "label", "value"):
        v = (el.attrib.get(k) or "").lower()
        if needle in v:
            return True
    return False


def subtree_has_match(el: ET.Element, needle: str) -> bool:
    if matches(el, needle):
        return True
    return any(subtree_has_match(c, needle) for c in el)


def walk(el: ET.Element, depth: int, needle: str, out: list, count: list):
    if needle and not subtree_has_match(el, needle):
        return
    out.append("  " * depth + fmt_node(el))
    count[0] += 1
    for c in el:
        walk(c, depth + 1, needle, out, count)


def main():
    needle = sys.argv[1] if len(sys.argv) > 1 else ""
    xml = sys.stdin.read()
    root = ET.fromstring(xml)
    out, count = [], [0]
    walk(root, 0, needle, out, count)
    if not out:
        print("(empty tree or filter matched nothing)", file=sys.stderr)
        sys.exit(1)
    print("\n".join(out))
    print(f"\n-- {count[0]} nodes --", file=sys.stderr)


if __name__ == "__main__":
    main()
