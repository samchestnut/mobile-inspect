#!/usr/bin/env python3
"""Format Android uiautomator XML dump as a compact indented tree."""
import sys
import xml.etree.ElementTree as ET


def short_class(cls: str) -> str:
    return cls.rsplit(".", 1)[-1] if cls else "?"


def fmt_node(node: ET.Element) -> str:
    cls = short_class(node.attrib.get("class", ""))
    parts = [cls]
    extras = []
    rid = node.attrib.get("resource-id", "")
    if rid:
        extras.append(f"id={rid.split('/')[-1]}")
    desc = node.attrib.get("content-desc", "")
    if desc:
        extras.append(f'desc="{desc}"')
    text = node.attrib.get("text", "")
    if text:
        extras.append(f'text="{text}"')
    bounds = node.attrib.get("bounds", "")
    if bounds:
        extras.append(f"bounds={bounds}")
    if node.attrib.get("clickable") == "false":
        extras.append("clickable=false")
    if node.attrib.get("enabled") == "false":
        extras.append("disabled")
    if extras:
        parts.append("[" + ", ".join(extras) + "]")
    return " ".join(parts)


def matches(node: ET.Element, needle: str) -> bool:
    needle = needle.lower()
    for k in ("text", "resource-id", "content-desc", "class"):
        v = node.attrib.get(k, "").lower()
        if needle in v:
            return True
    return False


def subtree_has_match(node: ET.Element, needle: str) -> bool:
    if matches(node, needle):
        return True
    return any(subtree_has_match(c, needle) for c in node)


def walk(node: ET.Element, depth: int, needle: str, out: list):
    if needle and not subtree_has_match(node, needle):
        return
    line = "  " * depth + fmt_node(node)
    out.append(line)
    for child in node:
        walk(child, depth + 1, needle, out)


def main():
    xml_path = sys.argv[1]
    needle = sys.argv[2] if len(sys.argv) > 2 else ""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    out = []
    # uiautomator wraps in <hierarchy>; descend into its children
    if root.tag == "hierarchy":
        for child in root:
            walk(child, 0, needle, out)
    else:
        walk(root, 0, needle, out)
    if not out:
        print("(empty tree or filter matched nothing)", file=sys.stderr)
        sys.exit(1)
    print("\n".join(out))
    print(f"\n-- {len(out)} nodes --", file=sys.stderr)


if __name__ == "__main__":
    main()
