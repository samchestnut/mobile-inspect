#!/usr/bin/env python3
"""Generate Appium WebdriverIO Page Object skeletons from saved snapshots.

Reads snapshots/ios/*.xml and snapshots/android/*.xml (paired by page name),
classifies elements as cross-page (basePage) vs page-specific, and emits
TypeScript class skeletons ready to paste into a project.

Cross-platform pairing:
  - element appears on iOS only        -> $('~name')
  - element appears on Android only    -> $('~content-desc')   (or resource-id)
  - element appears on BOTH platforms  -> emits a both-platform comment so
                                         you can wire it into your helper
                                         (CrossPlatformSelectors / getPlatformAccessibility).

Usage:
  gen-pom.py <snapshots-base-dir> [--style plain|wdio]
"""
import sys
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict


def short_type_ios(tag):
    return tag.replace("XCUIElementType", "") if tag else "?"


def extract_ios(xml):
    """yield (name, label, type) for visible named iOS elements."""
    root = ET.fromstring(xml)
    for el in root.iter():
        if el.attrib.get("visible", "true") == "false":
            continue
        name = el.attrib.get("name", "").strip()
        if not name:
            continue
        if el.tag in ("XCUIElementTypeApplication", "XCUIElementTypeWindow"):
            continue
        yield name, el.attrib.get("label", "").strip(), short_type_ios(el.tag)


def extract_android(xml):
    """yield (key, kind, class) — kind in {'id','desc'}."""
    root = ET.fromstring(xml)
    for el in root.iter():
        rid = el.attrib.get("resource-id", "").strip()
        desc = el.attrib.get("content-desc", "").strip()
        cls = el.attrib.get("class", "").rsplit(".", 1)[-1]
        if rid:
            yield rid.split("/")[-1], "id", cls, rid  # full id kept for resource-id selector
        elif desc:
            yield desc, "desc", cls, desc


def to_camel(s, suffix=""):
    parts = re.split(r"[\s\.\-_/]+", s)
    parts = [p for p in parts if p]
    if not parts:
        return "elem" + suffix
    head = parts[0][0].lower() + parts[0][1:]
    rest = "".join(p[0].upper() + p[1:] for p in parts[1:])
    return head + rest + suffix


def class_name(page):
    return "".join(p[0].upper() + p[1:] for p in re.split(r"[\s_\-]+", page) if p) + "Page"


def emit_getter(varname, ios_name, android_key, android_kind, android_full_id):
    """Render a single getter line(s) for one element."""
    has_ios = bool(ios_name)
    has_android = bool(android_key)
    if has_ios and has_android:
        # Both platforms — emit dual selector w/ a hint to wire into project helpers.
        if android_kind == "id":
            and_sel = f'$(\'android=new UiSelector().resourceId("{android_full_id}")\')'
        else:
            and_sel = f'$("~{android_key}")'
        return [
            f"  // cross-platform — consider wiring through your helper "
            f"(e.g. CrossPlatformSelectors.getPlatformAccessibility):",
            f"  get {varname}() {{",
            f"    return driver.isIOS",
            f"      ? $(\"~{ios_name}\")",
            f"      : {and_sel};",
            f"  }}",
        ]
    if has_ios:
        return [f'  get {varname}() {{ return $("~{ios_name}"); }}  // iOS only']
    # android only
    if android_kind == "id":
        return [f'  get {varname}() {{ return $(\'android=new UiSelector().resourceId("{android_full_id}")\'); }}']
    return [f'  get {varname}() {{ return $("~{android_key}"); }}  // android desc']


def collect_per_page(snap_dir):
    """Return {page_name: {"ios": {name: (label, type)}, "android": {key: (kind, class, full_id)}}}."""
    out = defaultdict(lambda: {"ios": {}, "android": {}})

    ios_dir = os.path.join(snap_dir, "ios")
    if os.path.isdir(ios_dir):
        for fname in os.listdir(ios_dir):
            if not fname.endswith(".xml"):
                continue
            page = fname[:-4]
            with open(os.path.join(ios_dir, fname)) as f:
                xml = f.read()
            try:
                for name, label, typ in extract_ios(xml):
                    out[page]["ios"][name] = (label, typ)
            except ET.ParseError:
                pass

    and_dir = os.path.join(snap_dir, "android")
    if os.path.isdir(and_dir):
        for fname in os.listdir(and_dir):
            if not fname.endswith(".xml"):
                continue
            page = fname[:-4]
            with open(os.path.join(and_dir, fname)) as f:
                xml = f.read()
            try:
                for key, kind, cls, full in extract_android(xml):
                    out[page]["android"][key] = (kind, cls, full)
            except ET.ParseError:
                pass

    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: gen-pom.py <snapshots-base-dir>", file=sys.stderr)
        sys.exit(2)
    base = sys.argv[1]
    if not os.path.isdir(base):
        print(f"Snapshots base dir not found: {base}", file=sys.stderr)
        sys.exit(2)

    pages = collect_per_page(base)
    if not pages:
        print("No snapshots found. Take some with `inspect.sh <plat> --snapshot <page>` first.",
              file=sys.stderr)
        sys.exit(1)

    # Cross-page presence: count how many pages each element appears on, per platform.
    ios_presence = defaultdict(set)
    android_presence = defaultdict(set)
    for page, data in pages.items():
        for n in data["ios"]:
            ios_presence[n].add(page)
        for k in data["android"]:
            android_presence[k].add(page)

    total_pages = len(pages)
    base_threshold = 2  # element appearing on >=2 pages goes into basePage
    base_ios = {n for n, ps in ios_presence.items() if len(ps) >= base_threshold}
    base_android = {k for k, ps in android_presence.items() if len(ps) >= base_threshold}

    # Try to pair iOS name with Android key by exact-match first.
    # (Apps that already follow the same convention on both platforms — like App —
    #  will pair cleanly. Otherwise the iOS-only / android-only branches handle it.)

    # === Emit basePage.ts additions ===
    print("// =============================================================")
    print("// basePage.ts — suggested additions")
    print(f"// Elements seen on ≥{base_threshold} of {total_pages} pages")
    print("// =============================================================\n")
    print("export class BasePage {")
    base_keys = sorted(set(base_ios) | set(base_android), key=lambda k: k.lower())
    for k in base_keys:
        ios_name = k if k in base_ios else ""
        and_key = k if k in base_android else ""
        and_kind, and_full = "", ""
        if and_key:
            # Pick from any page where this android key was found
            for p in pages.values():
                if and_key in p["android"]:
                    and_kind, _, and_full = p["android"][and_key]
                    break
        for line in emit_getter(to_camel(k), ios_name, and_key, and_kind, and_full):
            print(line)
    print("}\n")

    # === Emit per-page classes ===
    for page in sorted(pages.keys()):
        data = pages[page]
        # Page-specific = appears only on this page (per platform)
        ios_specific = sorted(n for n in data["ios"] if len(ios_presence[n]) == 1)
        and_specific = sorted(k for k in data["android"] if len(android_presence[k]) == 1)
        if not ios_specific and not and_specific:
            continue
        cls = class_name(page)
        print("// =============================================================")
        print(f"// pages/{page}.page.ts — suggested skeleton")
        print(f"// {len(ios_specific)} iOS-specific, {len(and_specific)} Android-specific elements")
        print("// =============================================================\n")
        print(f"export class {cls} extends BasePage {{")
        # Pair by name if same key shows up on both platforms but only on this page
        emitted = set()
        for n in ios_specific:
            if n in data["android"]:
                kind, _, full = data["android"][n]
                for line in emit_getter(to_camel(n), n, n, kind, full):
                    print(line)
                emitted.add(("ios", n))
                emitted.add(("android", n))
            else:
                for line in emit_getter(to_camel(n), n, "", "", ""):
                    print(line)
                emitted.add(("ios", n))
        for k in and_specific:
            if ("android", k) in emitted:
                continue
            kind, _, full = data["android"][k]
            for line in emit_getter(to_camel(k), "", k, kind, full):
                print(line)
        print("}\n")

    # Hint footer
    print("// =============================================================")
    print(f"// Done. Pages: {total_pages} ({', '.join(sorted(pages.keys()))})")
    print(f"// basePage candidates: {len(base_keys)}")
    print("// Tip: run `--merge` first to sanity-check the cross-page split before pasting.")
    print("// =============================================================")


if __name__ == "__main__":
    main()
