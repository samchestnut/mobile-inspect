# mobile-inspect

A Claude Code skill that inspects the live UI element tree of any Android or iOS app and suggests the best Appium/XCUITest/UIAutomator selector for any element on screen.

## What it does

- **Dump** the on-screen view hierarchy of a real device, emulator, or simulator
- **Filter** the tree by keyword to scope down before reading
- **Suggest** ranked selector candidates for any element — accessibility id, predicate, class chain, indexed xpath, etc. — with reasoning about stability, runtime speed, and locale safety
- **Detect** duplicate identifiers in the dump and automatically fall back to safer alternatives (label, indexed xpath, parent-scoped UiSelector)
- **Enumerate** every named/tappable element on screen with one-shot Page Object suggestions
- **Snapshot + merge** multiple screens to see which elements are shared (BasePage candidates) vs page-specific
- **Auto-explore zones** (top app bar / bottom nav) — tap each element, dump the resulting screen, recover, repeat
- **Crawl the whole app** in one command — auto-snapshot every bottom-tab plus its top-bar sub-screens (`--crawl-app`)
- **Generate Page Objects** in TypeScript with a choice of templates (raw / cross-platform / cross-platform-registry) and write them straight into your project (`--target /path/to/project`)

Backends:

| Platform | Source of truth | Notes |
|----------|-----------------|-------|
| Android  | `adb shell uiautomator dump` | Works with real devices and emulators out of the box |
| iOS Simulator | WebDriverAgent (XCTest) over HTTP `:8100` | Skill clones + builds WDA on first iOS run (~3 min) |
| iOS real device | An already-running WDA endpoint on `:8100` | Skill does not provision/sign — bring your own (Appium counts) |

Why WDA and not `idb`? `idb ui describe-all` only returns nodes where `isAccessibilityElement == true`. Many apps set `accessibilityIdentifier` on automation-only buttons but leave the a11y flag off; `idb` misses those, WDA does not.

## Installation

```bash
git clone https://github.com/samchestnut/mobile-inspect.git ~/.claude/skills/mobile-inspect
```

(Or use the `npx` skill installer once published.)

### Android prerequisites

`adb` must be on `PATH`:

```bash
brew install --cask android-platform-tools
```

### iOS prerequisites (one-time)

Xcode (full IDE, not just CLI tools) is required.

```bash
~/.claude/skills/mobile-inspect/scripts/setup-wda.sh
```

This clones `appium/WebDriverAgent` into the skill folder and pre-builds it. Subsequent runs reuse the build cache.

To use a WDA checkout you already have:

```bash
export MOBILE_INSPECT_WDA_DIR=/path/to/WebDriverAgent
```

## Usage

The skill is invoked by Claude when you ask things like *"inspect this screen"*, *"find a selector for the bell icon"*, *"why can't Appium find this button?"*. You can also call it directly:

```bash
# Full tree, auto-detect platform
~/.claude/skills/mobile-inspect/scripts/inspect.sh

# Just the subtree containing "subtitle"
~/.claude/skills/mobile-inspect/scripts/inspect.sh ios --filter subtitle

# Suggest the best selector for an element matching "icon-more-vertical"
~/.claude/skills/mobile-inspect/scripts/inspect.sh ios --suggest icon-more-vertical

# List every named/tappable element with Page Object hints
~/.claude/skills/mobile-inspect/scripts/inspect.sh android --enumerate

# Raw XML / JSON
~/.claude/skills/mobile-inspect/scripts/inspect.sh android --raw
```

### Snapshot multiple screens, then build a Page Object library

```bash
# Manually: navigate to each screen, snapshot one at a time
~/.claude/skills/mobile-inspect/scripts/inspect.sh android --snapshot home
~/.claude/skills/mobile-inspect/scripts/inspect.sh android --snapshot videoDetail
~/.claude/skills/mobile-inspect/scripts/inspect.sh android --snapshot library

# Or auto: crawl every bottom-tab + top-bar sub-screen of the app at once
~/.claude/skills/mobile-inspect/scripts/inspect.sh android --crawl-app

# See which elements are shared vs page-specific
~/.claude/skills/mobile-inspect/scripts/inspect.sh --merge

# Pick a code style and (optionally) write straight into your project
~/.claude/skills/mobile-inspect/scripts/inspect.sh --list-templates
~/.claude/skills/mobile-inspect/scripts/inspect.sh android --gen-pom \
    --template cross-platform-registry \
    --target /path/to/your/wdio-project
# Add --force to overwrite existing files.
```

#### Templates available for `--gen-pom`

| Template | Output style |
|----------|-------------|
| `raw` (default) | `driver.isIOS ? $('~ios') : $('~android')` ternary, no helper imports |
| `cross-platform` | `CrossPlatformSelectors.getPlatformAccessibility(ios, android)` one-liner |
| `cross-platform-registry` | Splits each page into `pages/<x>.page.ts` + `selectors/registries/<x>.ts` |

#### `--crawl-app` safety scope

- **Guest mode by default** — never logs in, never fills forms.
- Skips any element whose name contains danger keywords (`Create`, `Upload`, `Camera`, `Record`, `Pay`, `Delete`, `Sign out`, `Subscribe`, `Buy`, …).
- If a tap navigates outside the target package, presses BACK and skips — never follows external apps.
- Does **not** recurse below the top-bar level (single-level depth from each tab).
- Relaunches the app between tabs for clean state.

### Example output (`--suggest`)

```
Element:
  Button [name="ContentCard-Regular-Video", label="icon-more-vertical"]
  frame=274,195,29x29
  (8 elements matched query; picked highest-scoring)

Selector recommendations (best first):
  ✅ [1] accessibility id (NON-UNIQUE)
      $("~ContentCard-Regular-Video")
      // WARNING: matches 56 elements; first one picked
     [2] class chain (by name)
      $('-ios class chain:**/XCUIElementTypeButton[`name == "ContentCard-Regular-Video"`]')
     [3] predicate (by name)
      $('-ios predicate string:name == "ContentCard-Regular-Video"')
     [4] indexed xpath
      $('(//XCUIElementTypeButton[@name="ContentCard-Regular-Video"])[1]')
      // element #1 of 8; combine with label predicate AND label == "icon-more-vertical" for safety
     [5] xpath
      $('//XCUIElementTypeButton[@name="ContentCard-Regular-Video"]')
```

## Selector priority — TL;DR

**iOS (XCUIElement):**
1. `~name` (accessibility id) — when unique
2. `-ios class chain` — fast, type-narrowed
3. `-ios predicate string` — flexible
4. Indexed xpath `(//Type[@name="X"])[N]` — when name+label both duplicated
5. xpath — last resort

**Android (UiAutomator):**
1. `resource-id` (full `pkg:id/foo`) — most stable
2. `~content-desc` — when unique
3. `UiSelector` chain with parent scope — when desc duplicated
4. `text` — locale-fragile, flagged
5. xpath — last resort

## Limitations

- iOS real-device WDA provisioning is out of scope (use Apple Developer signing / Appium / Xcode once)
- Native webviews appear as a single opaque node
- Off-screen virtualized cells aren't in the tree until they scroll into view
- Animations may produce stale nodes if dumped too early

## License

MIT — see [LICENSE](./LICENSE)
