---
name: mobile-inspect
description: "Inspect Android/iOS app UI on a connected device, find Appium selectors, and generate a full Page Object library. Use this skill whenever the user mentions: inspecting a screen, dumping page source / UI tree, finding a selector for any button/element, debugging 'element not found' / NoSuchElement errors, listing tappable elements, snapshotting screens, generating Page Objects, crawling the whole app automatically, or writing test code into a project. Vietnamese trigger phrases: 'tìm selector', 'chụp UI', 'liệt kê element', 'khám phá app', 'sinh page object', 'crawl app', 'Appium không thấy element'. Trigger even if the user doesn't mention 'mobile-inspect' explicitly — apply whenever they're working with mobile UI selectors, Appium / XCUITest / UIAutomator tests, or building a Page Object library. Backends: Android via adb, iOS Simulator via WebDriverAgent."
license: MIT
metadata:
  author: khanhnguyen
  version: "0.2.0"
allowed-tools: Bash Read
compatibility: "Android: requires `adb` (Android platform-tools). iOS Simulator: requires Xcode. First-time iOS setup runs `scripts/setup-wda.sh` to clone WebDriverAgent into the skill folder and pre-build it (~3 min, one-time). iOS real device is not supported in v0.2 (would need code signing)."
---

# Mobile Inspect — Live UI Tree for Android & iOS

Dump the current on-screen view hierarchy and return a compact tree Claude can read to:
- suggest a robust selector (`resource-id` / accessibility-id / name / xpath)
- explain why an element isn't being found
- diff two screens (before/after a tap)

## When to use this skill

Trigger on phrases like:
- "inspect [the current screen / this app]"
- "dump page source"
- "show the DOM / view hierarchy"
- "find a selector for [label/button]"
- "why can't Appium find [element]"

## Backends

| Platform | Backend | Why |
|----------|---------|-----|
| Android  | `adb shell uiautomator dump` | Native, zero extra deps once `adb` is installed |
| iOS Simulator | WebDriverAgent (XCTest) over HTTP :8100 | Returns the **full XCUIElement tree** — same as Appium Inspector. iOS Accessibility-only tools (`idb`) miss elements where `isAccessibilityElement = false`, even when `accessibilityIdentifier` is set; WDA does not. |

## First-time setup

**Android:** install `adb` if missing — `brew install --cask android-platform-tools`.

**iOS:** the skill ships with no WDA bundled. On first iOS use, run:
```bash
~/.claude/skills/mobile-inspect/scripts/setup-wda.sh
```
This clones `appium/WebDriverAgent` into `~/.claude/skills/mobile-inspect/wda/` and pre-builds it via `xcodebuild` (~3 min, idempotent). Subsequent dumps reuse the build cache.

To point at an existing WDA checkout instead of cloning:
```bash
export MOBILE_INSPECT_WDA_DIR=/path/to/WebDriverAgent
```

## How to invoke

```bash
~/.claude/skills/mobile-inspect/scripts/inspect.sh [android|ios] [--raw] [--filter <substring>]
```

Flags:
- no platform arg → auto-detect (errors if both an Android device and an iOS sim are connected)
- `--raw` → print the unprocessed XML (skip the compact formatter)
- `--filter <substring>` → only show subtrees whose tag, name, label, or value contains the substring (case-insensitive)
- `--gen-pom [--template <name>] [--target <project-path>] [--force]` → Generate Page Object TypeScript from saved snapshots.
  - **Templates** select the code style:
    - `raw` (default) — `driver.isIOS ? $('~ios') : $('~android')` ternary, no helper imports
    - `cross-platform` — uses `CrossPlatformSelectors.getPlatformAccessibility(ios, android)`
    - `cross-platform-registry` — splits each page into `pages/<x>.page.ts` + `selectors/registries/<x>.ts`
  - `--target <dir>` → instead of printing to stdout, write each `// === FILE: <path> ===` section into `<dir>/<path>`. Refuses to overwrite existing files unless `--force`. Refuses paths that escape the target dir.
  - `--list-templates` → enumerate all templates.
- `--explore-zone <top|bottom|middle>` → **Android only.** Auto-tap each named element in the chosen screen zone, dump the resulting screen, diff vs the starting screen, then recover (back/relaunch) before the next tap. Skips child-duplicates and pure labels. Outputs `explore/<timestamp>-<zone>/` with one XML per element + `_index.md`. Safety: only taps within the picked zone — does NOT recurse into newly opened screens.
- `--crawl-app` → **Android only.** Full app crawl: snapshot the current screen, detect bottom-nav tabs, then for each tab also explore top-bar elements. Aggregates everything into `snapshots/android/` so a single `--merge` + `--gen-pom` can build the whole Page Object library. Safety:
  - **Guest mode by default.** Skill never logs in or fills forms.
  - Skips elements whose name matches danger keywords (Create / Upload / Camera / Record / Pay / Delete / Sign out / Subscribe / Buy).
  - If a tap navigates outside the target package, BACK and skip — never follows external apps.
  - Does NOT recurse below the top-bar level (one-screen depth from each tab).
  - Relaunches the app between tabs for clean state.

> ⚠️ **Safety caveats for `--explore-zone`** — read before running:
> 1. **Use a test account, never a production one.** The skill taps real elements. On a logged-in account, taps can trigger destructive actions (Like, Comment, Send, Delete, Pay, Subscribe). The `top` and `bottom` zones are usually navigation icons (safe). The `middle` zone is content/forms — high risk of triggering side effects. Prefer `top`/`bottom`. Use `middle` only on screens you've manually verified.
> 2. **Recovery may force-stop the app.** When BACK doesn't return to the start screen, the skill runs `am force-stop <pkg>` and relaunches. Any unsaved in-app state (half-filled form, draft message) is lost.
> 3. **Dumps may contain PII.** Saved XML files reflect what's on screen — emails, names, search history, message previews. The `explore/` and `snapshots/` directories are gitignored by default, but treat them as sensitive. Don't share, don't commit, prune periodically.
> 4. **WDA listens on localhost only by default.** Don't bind it to `0.0.0.0` — anyone on your LAN could control the device. After a session: `kill $(cat /tmp/mobile-inspect-wda.pid)`.

## Output format

Indented text tree. Each node:
```
<Type> [name="<name>", label="<label>", value="<value>", frame=<x,y,wxh>]
```
Empty fields are omitted. Examples:
```
Button [name="BottomNav.Home", label="Home", frame=14,780,71x70]
Image [name="icon-subtitle-off", label="ImageView", frame=329,275,21x21]
```

## Workflow

1. Detect or ask which platform.
2. **iOS only:** verify `~/.claude/skills/mobile-inspect/wda/` exists. If not, instruct the user to run `setup-wda.sh` and stop. Do not run setup yourself unless the user explicitly asks.
3. Make sure the app under test is **already in the foreground** on the device/sim. The skill does NOT launch apps.
4. Run `inspect.sh <platform>`. iOS will auto-launch WDA on port 8100 if it's not running yet (~10s using the pre-built cache; ~3 min on a cold first run if `setup-wda.sh` was skipped).
5. Read the tree, then answer the user's actual question (suggest selector, explain missing element). Quote the relevant 5-15 lines — do not paste a 200-node dump back at them.
6. If the tree is large, re-run with `--filter <keyword>` to scope down before answering.

## Suggesting selectors

**Android — preference order:**
1. `resource-id` (most stable)
2. `content-desc` → `~content-desc`
3. `text` → text-based (locale-fragile, flag this)
4. xpath as last resort

**iOS — preference order:**
1. `name` / accessibility id → `~name`
2. `-ios predicate string:name == "X"`
3. `` -ios class chain:**/XCUIElementType_____[`name == "X"`] `` (often fastest at runtime)
4. xpath as last resort

If the user's project has helper builders (`getAndroidElem`, `getIosElem`, `CrossPlatformSelectors`), match their convention by reading `selectors/` or `pages/`.

## State files (iOS)

The skill keeps WDA running between calls so subsequent dumps are fast (~1s):
- `/tmp/mobile-inspect-wda.pid` — the `xcodebuild test-without-building` process
- `/tmp/mobile-inspect-wda-session.txt` — current WDA session id (auto-recreated if invalid)
- `/tmp/mobile-inspect-wda.log` — xcodebuild stdout/stderr

To stop WDA: `kill $(cat /tmp/mobile-inspect-wda.pid)`. The next iOS dump will relaunch it.

## iOS real device

Supported when WDA is already running and reachable at `localhost:8100`. The skill does NOT set up WDA on a real device — that requires Apple Developer signing, provisioning profile, and `iproxy 8100 8100 -u <UDID>` (USB forward) or Wi-Fi access. The two common ways to satisfy this:

1. **Run Appium with a real-device session** — Appium installs/launches WDA and sets up port forwarding for you. While the session is alive, this skill reuses that same WDA endpoint.
2. **Manual WDA launch** — `xcodebuild test -destination "id=<real-UDID>"` after signing WDA in Xcode once, plus `iproxy 8100 8100 -u <UDID>` in another terminal.

The skill checks `localhost:8100/status` first; if WDA answers, it reuses that endpoint (real device or simulator — doesn't care) and prints which device it's connected to so you can verify the target. Only if no WDA is up does it fall back to launching its own against a booted simulator.

### Avoid the silent-sim-fallback trap

If you started Appium against an iPad and Appium dies (or you stopped the run), `:8100` goes down — and the skill will helpfully (and wrongly) launch WDA on whatever sim happens to be booted. To prevent that during real-device workflows:

```bash
# Refuse to launch our own WDA — fail loudly if Appium isn't keeping :8100 alive.
MOBILE_INSPECT_NO_LAUNCH=1 inspect.sh ios --suggest icon-bell

# Or pin the target UDID when launching ourselves (skips the booted-sim auto-pick):
MOBILE_INSPECT_TARGET_UDID=<udid> inspect.sh ios --enumerate

# Use a non-default WDA port (Appium is sometimes on 8101 etc.):
MOBILE_INSPECT_WDA_PORT=8101 inspect.sh ios --raw
```

When WDA is reused, the skill logs a one-line target hint (`device=...  iosVersion=...  hint=device|simulator`) to stderr; verify it before trusting the dump.

## Limitations (v0.3)

- The skill itself does not provision/sign WDA for real devices — bring your own running WDA.
- Webviews inside native apps are returned as a single opaque node — no inner DOM.
- Animations / loading spinners may produce stale or missing nodes if dumped too early.
- WDA's `/source` reflects what is currently *on screen*. Off-screen / virtualized cells are not in the tree until they scroll into view.
