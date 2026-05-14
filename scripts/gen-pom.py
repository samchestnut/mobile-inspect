#!/usr/bin/env python3
"""Generate Appium WebdriverIO Page Object skeletons from saved snapshots.

Reads snapshots/ios/*.xml and snapshots/android/*.xml (paired by page name),
classifies elements as cross-page (basePage) vs page-specific, and emits
TypeScript class skeletons ready to paste into a project.

Templates (pick with --template <name>):
  raw                       — default. driver.isIOS ternary, no helper assumptions.
  cross-platform            — uses CrossPlatformSelectors.getPlatformAccessibility(ios, android)
                              wrapped in single-line getters.
  cross-platform-registry   — splits page object and selector registry into 2 files
                              (pages/<x>.page.ts + selectors/registries/<x>.ts).

Run `--list-templates` to see all options.

Usage:
  gen-pom.py <snapshots-base-dir> [--template raw|cross-platform|cross-platform-registry]
  gen-pom.py --list-templates
"""
import argparse
import sys
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

BASE_THRESHOLD = 2  # element appearing on >= this many pages goes into basePage


# --- Parsing (unchanged) -----------------------------------------------------
def short_type_ios(tag):
    return tag.replace("XCUIElementType", "") if tag else "?"


def extract_ios(xml):
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
    root = ET.fromstring(xml)
    for el in root.iter():
        rid = el.attrib.get("resource-id", "").strip()
        desc = el.attrib.get("content-desc", "").strip()
        cls = el.attrib.get("class", "").rsplit(".", 1)[-1]
        if rid:
            yield rid.split("/")[-1], "id", cls, rid
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


def reg_var_name(page):
    """videoDetail → videoDetailSelectors"""
    cls = class_name(page).replace("Page", "")
    return cls[0].lower() + cls[1:] + "Selectors"


def collect_per_page(snap_dir):
    out = defaultdict(lambda: {"ios": {}, "android": {}})
    for plat, key_yield in (("ios", extract_ios), ("android", extract_android)):
        plat_dir = os.path.join(snap_dir, plat)
        if not os.path.isdir(plat_dir):
            continue
        for fname in os.listdir(plat_dir):
            if not fname.endswith(".xml"):
                continue
            page = fname[:-4]
            try:
                xml = open(os.path.join(plat_dir, fname)).read()
            except OSError:
                continue
            try:
                if plat == "ios":
                    for name, label, typ in key_yield(xml):
                        out[page]["ios"][name] = (label, typ)
                else:
                    for key, kind, cls, full in key_yield(xml):
                        out[page]["android"][key] = (kind, cls, full)
            except ET.ParseError:
                pass
    return out


# --- Selector string builders ------------------------------------------------
def ios_sel(name):
    return f'$("~{name}")'


def android_sel(kind, key, full_id):
    if kind == "id":
        return f'$(\'android=new UiSelector().resourceId("{full_id}")\')'
    return f'$("~{key}")'


# --- Template: raw -----------------------------------------------------------
def emit_raw_getter(varname, ios_name, android_key, android_kind, android_full_id):
    has_ios = bool(ios_name)
    has_android = bool(android_key)
    if has_ios and has_android:
        return [
            f"  get {varname}() {{",
            f"    return driver.isIOS",
            f"      ? {ios_sel(ios_name)}",
            f"      : {android_sel(android_kind, android_key, android_full_id)};",
            f"  }}",
        ]
    if has_ios:
        return [f'  get {varname}() {{ return {ios_sel(ios_name)}; }}  // iOS only']
    return [f'  get {varname}() {{ return {android_sel(android_kind, android_key, android_full_id)}; }}  // Android only']


# --- Template: cross-platform ------------------------------------------------
HELPER_IMPORT = 'import { CrossPlatformSelectors } from "@selectors/builders/crossPlatform.selector";'


def emit_cross_platform_getter(varname, ios_name, android_key, android_kind, android_full_id):
    has_ios = bool(ios_name)
    has_android = bool(android_key)
    if has_ios and has_android:
        # Both have accessibility-id-style names → use getPlatformAccessibility shorthand.
        if android_kind == "desc":
            return [
                f'  get {varname}() {{ return CrossPlatformSelectors.getPlatformAccessibility("{ios_name}", "{android_key}"); }}',
            ]
        # Android uses resource-id, not desc → fall back to ternary inside helper-style comment.
        return [
            f"  // Android uses resource-id, not accessibility — wire manually if your helper supports it.",
            f"  get {varname}() {{",
            f"    return driver.isIOS",
            f"      ? {ios_sel(ios_name)}",
            f"      : {android_sel(android_kind, android_key, android_full_id)};",
            f"  }}",
        ]
    if has_ios:
        return [f'  get {varname}() {{ return {ios_sel(ios_name)}; }}  // iOS only']
    return [f'  get {varname}() {{ return {android_sel(android_kind, android_key, android_full_id)}; }}  // Android only']


# --- Template: cross-platform-registry ---------------------------------------
def emit_registry_entry(varname, ios_name, android_key, android_kind, android_full_id):
    """Single entry in a registry object literal."""
    has_ios = bool(ios_name)
    has_android = bool(android_key)
    if has_ios and has_android and android_kind == "desc":
        return f'  {varname}: () => CrossPlatformSelectors.getPlatformAccessibility("{ios_name}", "{android_key}"),'
    if has_ios and has_android:
        # mixed kind
        return (f'  {varname}: () => (driver.isIOS '
                f'? {ios_sel(ios_name)} '
                f': {android_sel(android_kind, android_key, android_full_id)}),')
    if has_ios:
        return f'  {varname}: () => {ios_sel(ios_name)},'
    return f'  {varname}: () => {android_sel(android_kind, android_key, android_full_id)},'


# --- Available templates -----------------------------------------------------
TEMPLATES = {
    "raw": {
        "desc": "Default. driver.isIOS ternary, no helper imports, no convention assumptions.",
    },
    "cross-platform": {
        "desc": "Uses CrossPlatformSelectors.getPlatformAccessibility(ios, android) when both platforms have desc-style ids.",
    },
    "cross-platform-registry": {
        "desc": "Splits each page into pages/<x>.page.ts + selectors/registries/<x>.ts. Imports CrossPlatformSelectors.",
    },
}


# --- Renderers (driven by template) ------------------------------------------
def render_raw(pages, base_keys, ios_presence, android_presence):
    print(f"// === FILE: pages/base.page.ts ===\n")
    print(f"// Elements seen on ≥{BASE_THRESHOLD} of {len(pages)} pages\n")
    print("export class BasePage {")
    for k in base_keys:
        ios_name = k if k in {n for n, ps in ios_presence.items() if len(ps) >= BASE_THRESHOLD} else ""
        and_key = k if k in {n for n, ps in android_presence.items() if len(ps) >= BASE_THRESHOLD} else ""
        and_kind, and_full = _lookup_android(pages, and_key)
        for line in emit_raw_getter(to_camel(k), ios_name, and_key, and_kind, and_full):
            print(line)
    print("}\n")

    for page in sorted(pages.keys()):
        data = pages[page]
        ios_specific = sorted(n for n in data["ios"] if len(ios_presence[n]) == 1)
        and_specific = sorted(k for k in data["android"] if len(android_presence[k]) == 1)
        if not ios_specific and not and_specific:
            continue
        cls = class_name(page)
        print(f"// === FILE: pages/{page}.page.ts ===\n")
        print(f"export class {cls} extends BasePage {{")
        emitted = set()
        for n in ios_specific:
            if n in data["android"]:
                kind, _, full = data["android"][n]
                for line in emit_raw_getter(to_camel(n), n, n, kind, full):
                    print(line)
                emitted.add(("ios", n)); emitted.add(("android", n))
            else:
                for line in emit_raw_getter(to_camel(n), n, "", "", ""):
                    print(line)
                emitted.add(("ios", n))
        for k in and_specific:
            if ("android", k) in emitted:
                continue
            kind, _, full = data["android"][k]
            for line in emit_raw_getter(to_camel(k), "", k, kind, full):
                print(line)
        print("}\n")


def render_cross_platform(pages, base_keys, ios_presence, android_presence):
    base_ios_set = {n for n, ps in ios_presence.items() if len(ps) >= BASE_THRESHOLD}
    base_and_set = {n for n, ps in android_presence.items() if len(ps) >= BASE_THRESHOLD}

    print(f"// === FILE: pages/base.page.ts ===\n")
    print(HELPER_IMPORT)
    print()
    print("export class BasePage {")
    for k in base_keys:
        ios_name = k if k in base_ios_set else ""
        and_key = k if k in base_and_set else ""
        and_kind, and_full = _lookup_android(pages, and_key)
        for line in emit_cross_platform_getter(to_camel(k), ios_name, and_key, and_kind, and_full):
            print(line)
    print("}\n")

    for page in sorted(pages.keys()):
        data = pages[page]
        ios_specific = sorted(n for n in data["ios"] if len(ios_presence[n]) == 1)
        and_specific = sorted(k for k in data["android"] if len(android_presence[k]) == 1)
        if not ios_specific and not and_specific:
            continue
        cls = class_name(page)
        print(f"// === FILE: pages/{page}.page.ts ===\n")
        print(HELPER_IMPORT)
        print('import { BasePage } from "@pages/base.page";')
        print()
        print(f"export class {cls} extends BasePage {{")
        emitted = set()
        for n in ios_specific:
            if n in data["android"]:
                kind, _, full = data["android"][n]
                for line in emit_cross_platform_getter(to_camel(n), n, n, kind, full):
                    print(line)
                emitted.add(("ios", n)); emitted.add(("android", n))
            else:
                for line in emit_cross_platform_getter(to_camel(n), n, "", "", ""):
                    print(line)
                emitted.add(("ios", n))
        for k in and_specific:
            if ("android", k) in emitted:
                continue
            kind, _, full = data["android"][k]
            for line in emit_cross_platform_getter(to_camel(k), "", k, kind, full):
                print(line)
        print("}\n")


def render_cross_platform_registry(pages, base_keys, ios_presence, android_presence):
    base_ios_set = {n for n, ps in ios_presence.items() if len(ps) >= BASE_THRESHOLD}
    base_and_set = {n for n, ps in android_presence.items() if len(ps) >= BASE_THRESHOLD}

    # base registry
    print("// === FILE: selectors/registries/base.ts ===\n")
    print(HELPER_IMPORT)
    print()
    print("export const baseSelectors = {")
    for k in base_keys:
        ios_name = k if k in base_ios_set else ""
        and_key = k if k in base_and_set else ""
        and_kind, and_full = _lookup_android(pages, and_key)
        print(emit_registry_entry(to_camel(k), ios_name, and_key, and_kind, and_full))
    print("};\n")

    # base page
    print("// === FILE: pages/base.page.ts ===\n")
    print('import { baseSelectors } from "@selectors/registries/base";')
    print()
    print("export class BasePage {")
    for k in base_keys:
        v = to_camel(k)
        print(f"  get {v}() {{ return baseSelectors.{v}(); }}")
    print("}\n")

    # per-page
    for page in sorted(pages.keys()):
        data = pages[page]
        ios_specific = sorted(n for n in data["ios"] if len(ios_presence[n]) == 1)
        and_specific = sorted(k for k in data["android"] if len(android_presence[k]) == 1)
        if not ios_specific and not and_specific:
            continue
        reg = reg_var_name(page)
        cls = class_name(page)

        # registry file
        print(f"// === FILE: selectors/registries/{page}.ts ===\n")
        print(HELPER_IMPORT)
        print()
        print(f"export const {reg} = {{")
        emitted = set()
        for n in ios_specific:
            if n in data["android"]:
                kind, _, full = data["android"][n]
                print(emit_registry_entry(to_camel(n), n, n, kind, full))
                emitted.add(("ios", n)); emitted.add(("android", n))
            else:
                print(emit_registry_entry(to_camel(n), n, "", "", ""))
                emitted.add(("ios", n))
        for k in and_specific:
            if ("android", k) in emitted:
                continue
            kind, _, full = data["android"][k]
            print(emit_registry_entry(to_camel(k), "", k, kind, full))
        print("};\n")

        # page file
        print(f"// === FILE: pages/{page}.page.ts ===\n")
        print('import { BasePage } from "@pages/base.page";')
        print(f'import {{ {reg} }} from "@selectors/registries/{page}";')
        print()
        print(f"export class {cls} extends BasePage {{")
        # Re-iterate to mirror the registry order
        page_keys = []
        emitted2 = set()
        for n in ios_specific:
            page_keys.append(to_camel(n))
            emitted2.add(n)
        for k in and_specific:
            v = to_camel(k)
            if v not in [to_camel(n) for n in ios_specific]:
                page_keys.append(v)
        for v in page_keys:
            print(f"  get {v}() {{ return {reg}.{v}(); }}")
        print("}\n")


# --- Helpers -----------------------------------------------------------------
def _lookup_android(pages, and_key):
    if not and_key:
        return "", ""
    for p in pages.values():
        if and_key in p["android"]:
            kind, _, full = p["android"][and_key]
            return kind, full
    return "", ""


# --- Main --------------------------------------------------------------------
FILE_MARKER_RE = re.compile(r"^//\s*===\s*FILE:\s*(.+?)\s*===\s*$")


def split_into_files(blob: str):
    """Parse rendered blob into [(rel_path, content), ...] using FILE markers."""
    files = []
    cur_path = None
    cur_lines = []
    for line in blob.splitlines():
        m = FILE_MARKER_RE.match(line)
        if m:
            if cur_path is not None:
                files.append((cur_path, "\n".join(cur_lines).strip() + "\n"))
            cur_path = m.group(1).strip()
            cur_lines = []
        elif cur_path is not None:
            cur_lines.append(line)
    if cur_path is not None and cur_lines:
        files.append((cur_path, "\n".join(cur_lines).strip() + "\n"))
    return files


def write_to_target(blob: str, target_dir: Path, force: bool):
    """Write each FILE-marked section into target_dir/<rel_path>.

    Refuses to overwrite existing files unless --force. Refuses paths that
    escape target_dir.
    """
    target = target_dir.resolve()
    if not target.is_dir():
        print(f"Target dir not found: {target}", file=sys.stderr)
        sys.exit(2)

    files = split_into_files(blob)
    if not files:
        print("No FILE markers found in output — nothing to write.", file=sys.stderr)
        sys.exit(2)

    written, skipped, conflict = [], [], []
    for rel, content in files:
        # Path traversal guard
        out = (target / rel).resolve()
        try:
            out.relative_to(target)
        except ValueError:
            print(f"Refusing path outside target: {rel}", file=sys.stderr)
            skipped.append(rel)
            continue

        if out.exists() and not force:
            conflict.append(rel)
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content)
        written.append(rel)

    print(f"\n[--target] {target}", file=sys.stderr)
    if written:
        print(f"  ✓ written ({len(written)}):", file=sys.stderr)
        for r in written:
            print(f"      {r}", file=sys.stderr)
    if conflict:
        print(f"  ⚠ already exists ({len(conflict)}) — use --force to overwrite:",
              file=sys.stderr)
        for r in conflict:
            print(f"      {r}", file=sys.stderr)
    if skipped:
        print(f"  ✗ skipped ({len(skipped)}):", file=sys.stderr)
        for r in skipped:
            print(f"      {r}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="", help="snapshots base dir")
    ap.add_argument("--template", default="raw", choices=list(TEMPLATES.keys()))
    ap.add_argument("--list-templates", action="store_true")
    ap.add_argument("--target", default="",
                    help="write output to this project dir (parses FILE markers)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing files when --target is set")
    args = ap.parse_args()

    if args.list_templates:
        print("Available templates (use with --template <name>):\n")
        for name, info in TEMPLATES.items():
            print(f"  {name}")
            print(f"    {info['desc']}")
        sys.exit(0)

    if not args.base or not os.path.isdir(args.base):
        print(f"Snapshots base dir not found: {args.base}", file=sys.stderr)
        sys.exit(2)

    pages = collect_per_page(args.base)
    if not pages:
        print("No snapshots. Take some with `inspect.sh <plat> --snapshot <page>` first.",
              file=sys.stderr)
        sys.exit(1)

    ios_presence = defaultdict(set)
    android_presence = defaultdict(set)
    for page, data in pages.items():
        for n in data["ios"]:
            ios_presence[n].add(page)
        for k in data["android"]:
            android_presence[k].add(page)

    base_ios = {n for n, ps in ios_presence.items() if len(ps) >= BASE_THRESHOLD}
    base_android = {k for k, ps in android_presence.items() if len(ps) >= BASE_THRESHOLD}
    base_keys = sorted(set(base_ios) | set(base_android), key=lambda k: k.lower())

    renderers = {
        "raw": render_raw,
        "cross-platform": render_cross_platform,
        "cross-platform-registry": render_cross_platform_registry,
    }

    # Capture stdout into a string when --target is set, so we can split + write.
    if args.target:
        import io
        buf = io.StringIO()
        sys_stdout_orig = sys.stdout
        sys.stdout = buf
        try:
            renderers[args.template](pages, base_keys, ios_presence, android_presence)
        finally:
            sys.stdout = sys_stdout_orig
        write_to_target(buf.getvalue(), Path(args.target), args.force)
        print(f"\nTemplate: {args.template} | Pages: {len(pages)} | basePage candidates: {len(base_keys)}",
              file=sys.stderr)
        return

    renderers[args.template](pages, base_keys, ios_presence, android_presence)

    print("// =============================================================")
    print(f"// Done. Template: {args.template} | Pages: {len(pages)} ({', '.join(sorted(pages.keys()))})")
    print(f"// basePage candidates: {len(base_keys)}")
    print("// Tip: run `--merge` first to sanity-check the cross-page split.")
    print("// Tip: pass --target /path/to/project to write files directly.")
    print("// =============================================================")


# Path needs to be importable
from pathlib import Path

if __name__ == "__main__":
    main()
