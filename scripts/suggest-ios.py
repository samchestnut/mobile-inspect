#!/usr/bin/env python3
"""Suggest the best Appium/XCUITest selector for an element on iOS.

Usage: cat wda-source.xml | suggest-ios.py "<query>"
The query is a case-insensitive substring matched against
name, label, value, and type. The script picks the single
best-scoring match and prints ranked selector candidates
with reasoning.
"""
import sys
import xml.etree.ElementTree as ET


PRIORITY_NOTES = {
    "name-unique": "stable, runtime-fast, locale-independent",
    "class-chain": "fast filter using XCUIElementType + name",
    "predicate": "flexible (CONTAINS, AND, OR), slower than class chain",
    "label-unique": "label is i18n; flag if app supports multiple locales",
    "xpath": "fragile + slowest, last resort",
}


def short_type(tag):
    return tag.replace("XCUIElementType", "") if tag else "?"


def matches_query(el, q):
    q = q.lower()
    if q in el.tag.lower():
        return True
    for k in ("name", "label", "value"):
        if q in (el.attrib.get(k, "") or "").lower():
            return True
    return False


def score_match(el, q):
    q = q.lower()
    s = 0
    if q == (el.attrib.get("name") or "").lower(): s += 100
    if q == (el.attrib.get("label") or "").lower(): s += 80
    if q in (el.attrib.get("name") or "").lower(): s += 60
    if q in (el.attrib.get("label") or "").lower(): s += 40
    if q in (el.attrib.get("value") or "").lower(): s += 20
    return s


def attr_count(nodes, key, value):
    if not value:
        return 0
    return sum(1 for n in nodes if n.attrib.get(key) == value)


def build_selectors(el, all_nodes):
    out = []
    name = el.attrib.get("name", "")
    label = el.attrib.get("label", "")
    typ = el.tag

    name_dups = attr_count(all_nodes, "name", name) if name else 0
    label_dups = attr_count(all_nodes, "label", label) if label else 0

    # 1. accessibility id (~name) — best if unique
    if name and name_dups == 1:
        out.append(("accessibility id", f'$("~{name}")', "",
                    PRIORITY_NOTES["name-unique"]))

    # 1b. label-as-id when name is duplicated but label is unique
    # (common when dev sets a11y id on parent container, not the leaf button)
    if name and name_dups > 1 and label and label_dups == 1:
        out.append(("label predicate (name was duplicated)",
                    f"$('-ios predicate string:label == \"{label}\"')",
                    f"// name=\"{name}\" matches {name_dups} elements; label is unique",
                    PRIORITY_NOTES["label-unique"]))
        cc = f'**/{typ}[`label == "{label}"`]'
        out.append(("label class chain", f"$('-ios class chain:{cc}')", "",
                    PRIORITY_NOTES["class-chain"]))

    # 1c. combined name + label (if both duplicate individually but pair is unique)
    if name and label and name_dups > 1 and label_dups > 1:
        pair_count = sum(1 for n in all_nodes
                         if n.attrib.get("name") == name
                         and n.attrib.get("label") == label)
        if pair_count == 1:
            out.append(("name + label combined",
                        f"$('-ios predicate string:name == \"{name}\" AND label == \"{label}\"')",
                        f"// neither name nor label unique alone; pair matches 1 element",
                        PRIORITY_NOTES["predicate"]))

    # 2. accessibility id non-unique warning (only if no better option above)
    if name and name_dups > 1:
        out.append(("accessibility id (NON-UNIQUE)", f'$("~{name}")',
                    f"// WARNING: matches {name_dups} elements; first one picked",
                    "name duplicated — prefer label-based options above"))

    # 3. -ios class chain by name
    if name:
        cc = f'**/{typ}[`name == "{name}"`]'
        out.append(("class chain (by name)", f"$('-ios class chain:{cc}')", "",
                    PRIORITY_NOTES["class-chain"]))

    # 4. predicate by name
    if name:
        out.append(("predicate (by name)", f"$('-ios predicate string:name == \"{name}\"')", "",
                    PRIORITY_NOTES["predicate"]))

    # 4b. indexed xpath when both name AND label are duplicated (e.g. carousel buttons)
    if name and name_dups > 1 and (not label or label_dups > 1):
        # 1-based index among nodes sharing same tag + name (tree order)
        same = [n for n in all_nodes if n.tag == typ and n.attrib.get("name") == name]
        if target_in := next((i + 1 for i, n in enumerate(same) if n is el), None):
            xp = f'(//{typ}[@name="{name}"])[{target_in}]'
            extra_filter = f' AND label == "{label}"' if label else ""
            out.append(("indexed xpath",
                        f"$('{xp}')",
                        f"// element #{target_in} of {len(same)} matching {typ}[name=\"{name}\"]"
                        + (f"; combine with label predicate{extra_filter} for safety" if label else ""),
                        "use when neither name nor label is unique — flags fragility to layout changes"))

    # 5. label fallback when no name at all
    if not name and label:
        if label_dups == 1:
            out.append(("label", f"$('-ios predicate string:label == \"{label}\"')",
                        "", PRIORITY_NOTES["label-unique"]))

    # 5. xpath
    if name:
        xp = f'//{typ}[@name="{name}"]'
    elif label:
        xp = f'//{typ}[@label="{label}"]'
    else:
        xp = f'//{typ}'
    out.append(("xpath", f"$('{xp}')", "", PRIORITY_NOTES["xpath"]))

    return out


def fmt_element(el):
    a = el.attrib
    parts = [short_type(el.tag)]
    extras = []
    for k in ("name", "label", "value"):
        v = a.get(k, "")
        if v:
            extras.append(f'{k}="{v}"')
    if extras:
        parts.append("[" + ", ".join(extras) + "]")
    return " ".join(parts)


def main():
    if len(sys.argv) < 2:
        print("Usage: cat source.xml | suggest-ios.py <query>", file=sys.stderr)
        sys.exit(2)
    query = sys.argv[1]
    xml = sys.stdin.read()
    root = ET.fromstring(xml)
    nodes = list(root.iter())
    matches = [n for n in nodes if matches_query(n, query)]
    if not matches:
        print(f"No element matches '{query}'", file=sys.stderr)
        sys.exit(1)
    matches.sort(key=lambda n: -score_match(n, query))
    target = matches[0]

    print("Element:")
    print(f"  {fmt_element(target)}")
    a = target.attrib
    if all(k in a for k in ("x", "y", "width", "height")):
        print(f"  frame={a['x']},{a['y']},{a['width']}x{a['height']}")
    if len(matches) > 1:
        print(f"  ({len(matches)} elements matched query; picked highest-scoring)")
    print()

    sels = build_selectors(target, nodes)
    print("Selector recommendations (best first):")
    for i, (kind, sel, alt, why) in enumerate(sels, 1):
        marker = "✅" if i == 1 else ("⚠️" if "WARNING" in alt or "NON-UNIQUE" in kind else "  ")
        print(f"  {marker} [{i}] {kind}")
        print(f"      {sel}")
        if alt:
            print(f"      {alt}")
        print(f"      // {why}")


if __name__ == "__main__":
    main()
