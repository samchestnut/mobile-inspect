# Visual docs — mobile-inspect

5-language walkthrough of the skill, generated from `build.py`.

## View

Open any HTML in a browser:
- `visual.vi.html` 🇻🇳 Tiếng Việt
- `visual.en.html` 🇬🇧 English (default via `index.html`)
- `visual.zh.html` 🇨🇳 简体中文
- `visual.ja.html` 🇯🇵 日本語
- `visual.ko.html` 🇰🇷 한국어

A language dropdown is fixed in the top-right of every page.

## Regenerate

```bash
python3 docs/build.py
```

Pulls mermaid v10 from CDN once, then writes 5 HTML files + `index.html`. Works offline (mermaid is bundled).
