# mobile-inspect

A Claude Code skill that inspects the live UI element tree of any Android or iOS app and suggests the best Appium/XCUITest/UIAutomator selector for any element on screen.

## What it does

- **Dump** the on-screen view hierarchy of a real device, emulator, or simulator
- **Filter** the tree by keyword to scope down before reading
- **Suggest** ranked selector candidates for any element — accessibility id, predicate, class chain, indexed xpath, etc. — with reasoning about stability, runtime speed, and locale safety
- **Detect** duplicate identifiers in the dump and automatically fall back to safer alternatives (label, indexed xpath, parent-scoped UiSelector)

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

# Raw XML / JSON
~/.claude/skills/mobile-inspect/scripts/inspect.sh android --raw
```

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
