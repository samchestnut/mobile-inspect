#!/usr/bin/env python3
"""Suggest the best Appium/UiAutomator selector for an element on Android.

Usage: cat uiautomator.xml | suggest-android.py "<query>"
The query is a case-insensitive substring matched against
resource-id, content-desc, text, and class. The script picks the
single best-scoring match and prints ranked selector candidates
with reasoning.
"""
import sys
import xml.etree.ElementTree as ET


PRIORITY_NOTES = {
    "resource-id": "stable, package-scoped, runtime-fast",
    "content-desc-unique": "unique a11y label, runtime-fast",
    "content-desc-scoped": "desc duplicated; scope via parent UiSelector",
    "text": "locale-fragile — breaks when language changes",
    "xpath": "fragile to layout changes, slowest",
}


def all_descendants(root):
    out = []
    for el in root.iter():
        out.append(el)
    return out


def matches_query(el, q):
    q = q.lower()
    for k in ("resource-id", "content-desc", "text", "class"):
        if q in (el.attrib.get(k, "") or "").lower():
            return True
    return False


def score_match(el, q):
    """Higher = better match for the query."""
    q = q.lower()
    s = 0
    if q == (el.attrib.get("content-desc") or "").lower(): s += 100
    if q == (el.attrib.get("text") or "").lower(): s += 80
    if q in (el.attrib.get("resource-id") or "").lower(): s += 60
    if q in (el.attrib.get("content-desc") or "").lower(): s += 40
    if q in (el.attrib.get("text") or "").lower(): s += 30
    return s


def attr_count(nodes, key, value):
    if not value:
        return 0
    return sum(1 for n in nodes if n.attrib.get(key) == value)


def parent_chain(root, target):
    parents = {c: p for p in root.iter() for c in p}
    chain = []
    cur = target
    while cur in parents:
        cur = parents[cur]
        chain.append(cur)
    return chain  # nearest parent first


def build_selectors(el, all_nodes, root):
    out = []
    rid = el.attrib.get("resource-id", "")
    desc = el.attrib.get("content-desc", "")
    text = el.attrib.get("text", "")

    # 1. resource-id (best)
    if rid:
        out.append(("resource-id",
                    f'$("id={rid}")',
                    f"// or: $('android=new UiSelector().resourceId(\"{rid}\")')",
                    PRIORITY_NOTES["resource-id"]))

    # 2. content-desc — unique?
    if desc:
        n_dups = attr_count(all_nodes, "content-desc", desc)
        if n_dups == 1:
            out.append(("content-desc",
                        f'$("~{desc}")',
                        "",
                        PRIORITY_NOTES["content-desc-unique"]))
        else:
            # Find nearest ancestor with a unique desc to scope into
            chain = parent_chain(root, el)
            scope_desc = ""
            for p in chain:
                pd = p.attrib.get("content-desc", "")
                if pd and pd != desc and attr_count(all_nodes, "content-desc", pd) == 1:
                    scope_desc = pd
                    break
            if scope_desc:
                ui = (f'new UiSelector().description("{scope_desc}")'
                      f'.childSelector(new UiSelector().description("{desc}"))')
                out.append(("content-desc + parent scope",
                            f"$('android={ui}')",
                            f"// '{desc}' has {n_dups} duplicates; scoped via ancestor '{scope_desc}'",
                            PRIORITY_NOTES["content-desc-scoped"]))
            else:
                out.append(("content-desc (NON-UNIQUE)",
                            f'$("~{desc}")',
                            f"// WARNING: matches {n_dups} elements; first one will be picked",
                            "duplicated desc with no unique ancestor — flag for dev"))

    # 3. text
    if text:
        n_dups = attr_count(all_nodes, "text", text)
        if n_dups == 1:
            ui = f'new UiSelector().text("{text}")'
            out.append(("text", f"$('android={ui}')",
                        "", PRIORITY_NOTES["text"]))

    # 4. xpath fallback
    cls = el.attrib.get("class", "")
    if desc:
        xp = f'//{cls}[@content-desc="{desc}"]'
    elif rid:
        xp = f'//{cls}[@resource-id="{rid}"]'
    elif text:
        xp = f'//{cls}[@text="{text}"]'
    else:
        xp = f'//{cls}'
    out.append(("xpath", f'$(\'{xp}\')', "", PRIORITY_NOTES["xpath"]))

    return out


def fmt_element(el):
    a = el.attrib
    parts = [a.get("class", "?").rsplit(".", 1)[-1]]
    extras = []
    for k in ("resource-id", "content-desc", "text"):
        v = a.get(k, "")
        if v:
            extras.append(f'{k}="{v}"')
    if extras:
        parts.append("[" + ", ".join(extras) + "]")
    if a.get("clickable") == "false":
        parts.append("(clickable=false)")
    return " ".join(parts)


def main():
    if len(sys.argv) < 2:
        print("Usage: cat dump.xml | suggest-android.py <query>", file=sys.stderr)
        sys.exit(2)
    query = sys.argv[1]
    xml = sys.stdin.read()
    root = ET.fromstring(xml)
    nodes = all_descendants(root)
    matches = [n for n in nodes if matches_query(n, query)]
    if not matches:
        print(f"No element matches '{query}'", file=sys.stderr)
        sys.exit(1)
    matches.sort(key=lambda n: -score_match(n, query))
    target = matches[0]

    print("Element:")
    print(f"  {fmt_element(target)}")
    print(f"  bounds={target.attrib.get('bounds','')}")
    if len(matches) > 1:
        print(f"  ({len(matches)} elements matched query; picked highest-scoring)")
    print()

    sels = build_selectors(target, nodes, root)
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
