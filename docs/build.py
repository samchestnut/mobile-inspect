#!/usr/bin/env python3
"""Generate 5-language visual docs for the mobile-inspect skill.

Outputs to the same folder as this script:
  visual.{vi,en,zh,ja,ko}.html  — visual walkthroughs with mermaid diagrams
  index.html                    — redirects to the English version
  mermaid.min.js                — bundled JS for offline rendering

Run: python3 docs/build.py
"""
from __future__ import annotations

import re
import shutil
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

LANGS = [
    ("vi", "Tiếng Việt", "🇻🇳", "visual.vi.html"),
    ("en", "English",    "🇬🇧", "visual.en.html"),
    ("zh", "简体中文",    "🇨🇳", "visual.zh.html"),
    ("ja", "日本語",      "🇯🇵", "visual.ja.html"),
    ("ko", "한국어",      "🇰🇷", "visual.ko.html"),
]

# --- Inline markdown converter ----------------------------------------------
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def md_inline(s: str) -> str:
    s = _BOLD.sub(r"<strong>\1</strong>", s)
    s = _CODE.sub(r"<code>\1</code>", s)
    return s


# --- Translation strings (per-language) -------------------------------------
T = {
    "vi": {
        "title": "mobile-inspect — Visual Overview",
        "intro": "Skill chụp UI tree của app Android/iOS để Claude tìm Appium selector, có thể tự crawl toàn bộ app và sinh Page Object luôn. Mỗi page chụp ra 3 file: `.xml` (tree), `.png` (ảnh màn hình), `.elements.md` (bảng element).",
        "h_what": "1. Skill làm gì?",
        "h_when": "2. Khi nào dùng?",
        "h_outputs": "3. Output mỗi page — 3 file song song",
        "h_cheat": "4. Cheatsheet — bảng lệnh",
        "h_full": "5. Workflow đầy đủ — sinh Page Object library",
        "h_warn": "⚠️ Cảnh báo an toàn",
        "lbl_situ": "Tình huống",
        "lbl_say": "Bạn bảo Claude",
        "lbl_do": "Skill làm",
        "outputs_intro": "Mỗi lần snapshot 1 page (hoặc khi `--crawl-app` tự chụp), skill ra **3 file song song** cùng tên:",
        "outputs_xml": "**`<name>.xml`** — UI tree data (đầu vào cho `--gen-pom`)",
        "outputs_png": "**`<name>.png`** — Ảnh chụp màn hình thật của page đó. Để bạn nhìn lại sau, hoặc so sánh visual với XML.",
        "outputs_md": "**`<name>.elements.md`** — Bảng markdown liệt kê tất cả element có tên: `Name | Type | Bounds | Tap` — đọc nhanh không cần parse XML.",
        "outputs_skip": "Skip 2 file extra bằng env `MOBILE_INSPECT_NO_EXTRAS=1` nếu chỉ cần XML.",
        "case1_h": "🔍 Case 1 — Tìm tên element cụ thể",
        "case1_situ": "Đang viết test 'Click Like' nhưng không biết nút Like tên gì.",
        "case1_say": '"find selector cho nút Like"',
        "case1_do": "Chụp UI hiện tại → trả về `~LikeButton` hoặc `id/like_btn` để copy vào test.",
        "case2_h": "🐛 Case 2 — Test fail 'không thấy element'",
        "case2_situ": "Appium báo `NoSuchElement` nhưng nhìn thấy nút rõ ràng.",
        "case2_say": '"inspect screen, sao Appium không thấy SaveButton?"',
        "case2_do": "Chụp UI, chỉ ra element thật tên gì (vd `SaveBtn` không phải `SaveButton`) hoặc bị overlay che.",
        "case3_h": "🗺️ Case 3 — Crawl toàn bộ app trong 1 lần",
        "case3_situ": "Vừa join project, muốn Page Object cho cả app, không phải gõ tay từng tab.",
        "case3_say": '"crawl toàn bộ app trên emulator"',
        "case3_do": "Tự tap qua từng bottom-tab + icon top-bar, mỗi page ra 3 file (`.xml` + `.png` + `.elements.md`). ~3-5 phút.",
        "case4_h": "📦 Case 4 — Sinh Page Object code thẳng vào project",
        "case4_situ": "Có 20+ file XML, muốn TypeScript paste-able vào WDIO project.",
        "case4_say": '"sinh code POM, ghi vào /Users/me/Code/my-project"',
        "case4_do": "Đọc XML, gom element xuất hiện ≥2 page vào `BasePage`, mỗi page ra 1 file riêng, ghi thẳng vào project (không đè cũ trừ khi `--force`).",
        "case5_h": "🛟 Case 5 — Khi dump fail, dùng Appium Inspector làm fallback",
        "case5_situ": "ADB không thấy device, WDA crash, hoặc dump trả về XML rỗng — skill báo lỗi.",
        "case5_say": '"không dump được, làm thế nào?"',
        "case5_do": "Skill chỉ là wrapper quanh Appium/UIAutomator2/XCUITest driver — cùng thứ Appium Inspector dùng. Mở [Appium Inspector](https://github.com/appium/appium-inspector), connect với capabilities bình thường, click **Refresh Source** → **Save Source** → có file XML. Drop file đó vào `~/.claude/skills/mobile-inspect/snapshots/<platform>/<page>.xml`. Tất cả lệnh khác của skill (`--gen-pom`, `--merge`, `format-*`, `suggest-*`, `elements-summary`) work bình thường — XML từ Inspector và skill là **interchangeable**.",
        "warn_account": "**Dùng test account, KHÔNG dùng prod.** Skill tap thật. Trên account login → có thể trigger Like/Comment/Send/Delete/Pay ngoài ý muốn. `--crawl-app` mặc định guest mode + skip danger keyword.",
        "warn_pii": "**Dump XML + PNG có thể chứa PII.** Email, tên, history, message preview. Folder `snapshots/` đã gitignore, vẫn coi là nhạy cảm. Đừng share, đừng commit.",
        "tbl_say": "Bạn nói với Claude",
        "tbl_run": "Skill chạy",
        "tbl_out": "Output",
        "full_intro": "Dựng Page Object library cho cả app — 4 lệnh:",
        "full_steps": [
            "1️⃣ **Mở app, dừng ở Home** — guest mode",
            "2️⃣ **Auto-crawl** — `inspect.sh android --crawl-app` (~3-5 phút)",
            "3️⃣ **Chọn template** — `inspect.sh --list-templates`",
            "4️⃣ **Sinh code + ghi vào project** — `inspect.sh android --gen-pom --template cross-platform-registry --target /path/to/wdio-project`",
        ],
        "full_result": "Kết quả: `pages/*.page.ts` + `selectors/registries/*.ts` paste-able, element shared tự promote vào `BasePage`.",
    },
    "en": {
        "title": "mobile-inspect — Visual Overview",
        "intro": "Captures the live UI tree of Android/iOS apps so Claude can find Appium selectors, auto-crawl the whole app, and generate Page Objects. Each captured page produces 3 files: `.xml` (tree), `.png` (screenshot), `.elements.md` (element table).",
        "h_what": "1. What does it do?",
        "h_when": "2. When to use",
        "h_outputs": "3. Per-page output — 3 side-by-side files",
        "h_cheat": "4. Cheatsheet",
        "h_full": "5. Full workflow — build a Page Object library",
        "h_warn": "⚠️ Safety",
        "lbl_situ": "Situation",
        "lbl_say": "You tell Claude",
        "lbl_do": "Skill does",
        "outputs_intro": "Every snapshot (or each page captured by `--crawl-app`) writes **3 sibling files** with the same basename:",
        "outputs_xml": "**`<name>.xml`** — UI tree data (consumed by `--gen-pom`).",
        "outputs_png": "**`<name>.png`** — Real screenshot of the page. Look back at the visual context later, or compare against the XML.",
        "outputs_md": "**`<name>.elements.md`** — Markdown table of every named element: `Name | Type | Bounds | Tap` — readable without parsing XML.",
        "outputs_skip": "Skip the two extras with `MOBILE_INSPECT_NO_EXTRAS=1` if you only need the XML.",
        "case1_h": "🔍 Case 1 — Find a specific element's name",
        "case1_situ": "You're writing 'Click Like' but don't know the Like element's id.",
        "case1_say": '"find a selector for the Like button"',
        "case1_do": "Dumps current UI → returns `~LikeButton` or `id/like_btn` to paste into your test.",
        "case2_h": "🐛 Case 2 — Test fails 'element not found'",
        "case2_situ": "Appium throws `NoSuchElement` but the button is clearly visible.",
        "case2_say": '"inspect screen, why doesn\'t Appium find SaveButton?"',
        "case2_do": "Dumps UI, points out the actual element name (e.g. `SaveBtn`, not `SaveButton`) or that an overlay is covering it.",
        "case3_h": "🗺️ Case 3 — Crawl the whole app in one go",
        "case3_situ": "Just joined the project, want a Page Object library without visiting every tab manually.",
        "case3_say": '"crawl the whole app on the emulator"',
        "case3_do": "Auto-taps each bottom-tab + top-bar icon; per page writes 3 files (`.xml` + `.png` + `.elements.md`). ~3-5 min.",
        "case4_h": "📦 Case 4 — Generate Page Objects straight into your project",
        "case4_situ": "You have 20+ XML files and want pasteable TypeScript dropped into your WDIO project.",
        "case4_say": '"generate POM, write to /Users/me/Code/my-project"',
        "case4_do": "Reads the XMLs, groups shared elements (≥2 pages) into `BasePage`, writes one file per page into the project (won't overwrite without `--force`).",
        "case5_h": "🛟 Case 5 — When dump fails, fall back to Appium Inspector",
        "case5_situ": "ADB doesn't see the device, WDA crashed, or the dump returns empty XML — the skill errors out.",
        "case5_say": '"can\'t dump, what now?"',
        "case5_do": "The skill is a thin wrapper around the same Appium / UIAutomator2 / XCUITest driver Appium Inspector talks to. Open [Appium Inspector](https://github.com/appium/appium-inspector), connect with your normal capabilities, click **Refresh Source** → **Save Source** → you get an XML. Drop it into `~/.claude/skills/mobile-inspect/snapshots/<platform>/<page>.xml`. All other skill commands (`--gen-pom`, `--merge`, `format-*`, `suggest-*`, `elements-summary`) work as if the XML came from us — **interchangeable**.",
        "warn_account": "**Use a test account, NEVER production.** The skill taps real elements. On a logged-in account, taps can fire Like/Comment/Send/Delete/Pay unintentionally. `--crawl-app` defaults to guest mode + skips danger keywords.",
        "warn_pii": "**XML + PNG dumps may contain PII.** Emails, names, search history, message previews. `snapshots/` is gitignored, but still treat as sensitive. Don't share, don't commit.",
        "tbl_say": "What you say to Claude",
        "tbl_run": "Skill runs",
        "tbl_out": "Output",
        "full_intro": "Build a Page Object library for the whole app in 4 commands:",
        "full_steps": [
            "1️⃣ **Open the app, stop at Home** — guest mode",
            "2️⃣ **Auto-crawl** — `inspect.sh android --crawl-app` (~3-5 min)",
            "3️⃣ **Pick a template** — `inspect.sh --list-templates`",
            "4️⃣ **Generate + write to project** — `inspect.sh android --gen-pom --template cross-platform-registry --target /path/to/wdio-project`",
        ],
        "full_result": "Result: `pages/*.page.ts` + `selectors/registries/*.ts` ready to paste, shared elements auto-promoted to `BasePage`.",
    },
    "zh": {
        "title": "mobile-inspect — 可视化总览",
        "intro": "抓取 Android/iOS 应用实时 UI 树,让 Claude 帮你找 Appium 选择器、自动爬取整个应用、直接生成 Page Object。每个截屏页面产出 3 个文件:`.xml`(树)、`.png`(截图)、`.elements.md`(元素表)。",
        "h_what": "1. 这个技能做什么?",
        "h_when": "2. 什么时候用?",
        "h_outputs": "3. 每页输出 — 3 个并行文件",
        "h_cheat": "4. 速查表",
        "h_full": "5. 完整工作流 — 构建 Page Object 库",
        "h_warn": "⚠️ 安全",
        "lbl_situ": "情况",
        "lbl_say": "你对 Claude 说",
        "lbl_do": "技能做",
        "outputs_intro": "每次快照(或 `--crawl-app` 抓的每个页面)都写出**3 个同名文件**:",
        "outputs_xml": "**`<name>.xml`** — UI 树数据(`--gen-pom` 的输入)。",
        "outputs_png": "**`<name>.png`** — 页面真实截图。事后回顾视觉上下文,或与 XML 对照。",
        "outputs_md": "**`<name>.elements.md`** — 所有命名元素的 markdown 表:`Name | Type | Bounds | Tap` — 不解析 XML 也能快速读。",
        "outputs_skip": "如果只要 XML,用 `MOBILE_INSPECT_NO_EXTRAS=1` 跳过另两个文件。",
        "case1_h": "🔍 场景1 — 找某个具体元素的名字",
        "case1_situ": "在写 '点击 Like' 但不知道 Like 元素叫什么。",
        "case1_say": '"找 Like 按钮的 selector"',
        "case1_do": "dump 当前 UI → 返回 `~LikeButton` 或 `id/like_btn` 让你粘到测试里。",
        "case2_h": "🐛 场景2 — 测试报 '找不到元素'",
        "case2_situ": "Appium 抛 `NoSuchElement` 但按钮明明能看到。",
        "case2_say": '"inspect 屏幕,为啥 Appium 找不到 SaveButton?"',
        "case2_do": "dump UI,指出元素真实名字(比如其实叫 `SaveBtn`)或被遮罩盖住。",
        "case3_h": "🗺️ 场景3 — 一次性爬完整个应用",
        "case3_situ": "刚加入项目,想要 Page Object 库,不想手动访问每个 tab。",
        "case3_say": '"在模拟器上爬整个应用"',
        "case3_do": "自动点击每个底部 tab + 顶部栏图标,每个页面输出 3 个文件(`.xml` + `.png` + `.elements.md`)。约 3-5 分钟。",
        "case4_h": "📦 场景4 — 直接将 Page Object 生成到项目",
        "case4_situ": "已有 20+ 个 XML 文件,想要可直接粘贴的 TypeScript 落地到 WDIO 项目。",
        "case4_say": '"生成 POM,写入 /Users/me/Code/my-project"',
        "case4_do": "读 XML,把出现在 ≥2 个页面的元素归入 `BasePage`,每页一个文件写入项目(不带 `--force` 不覆盖)。",
        "case5_h": "🛟 场景5 — Dump 失败时用 Appium Inspector 兜底",
        "case5_situ": "ADB 看不到设备、WDA 崩溃、或 dump 返回空 XML — 技能报错。",
        "case5_say": '"dump 不出来,怎么办?"',
        "case5_do": "技能只是 Appium / UIAutomator2 / XCUITest driver 的薄包装,跟 Appium Inspector 用的是同一套。打开 [Appium Inspector](https://github.com/appium/appium-inspector),用你平时的 capabilities 连接,点 **Refresh Source** → **Save Source** → 得到 XML。放到 `~/.claude/skills/mobile-inspect/snapshots/<platform>/<page>.xml`。技能的其他命令(`--gen-pom`、`--merge`、`format-*`、`suggest-*`、`elements-summary`)照常工作 — Inspector 和技能产出的 XML **可互换**。",
        "warn_account": "**用测试账号,绝对不要用生产账号。** 技能真实点击。已登录账号上 → 可能误触 Like/Comment/Send/Delete/Pay。`--crawl-app` 默认游客模式 + 跳过危险关键词。",
        "warn_pii": "**XML + PNG 可能包含 PII。** 邮箱、姓名、搜索历史、消息预览。`snapshots/` 已 gitignore,但仍按敏感数据对待。",
        "tbl_say": "你对 Claude 说",
        "tbl_run": "技能执行",
        "tbl_out": "输出",
        "full_intro": "用 4 条命令为整个应用构建 Page Object 库:",
        "full_steps": [
            "1️⃣ **打开 app,停在 Home** — 游客模式",
            "2️⃣ **自动爬取** — `inspect.sh android --crawl-app`(约 3-5 分钟)",
            "3️⃣ **选模板** — `inspect.sh --list-templates`",
            "4️⃣ **生成代码 + 写入项目** — `inspect.sh android --gen-pom --template cross-platform-registry --target /path/to/wdio-project`",
        ],
        "full_result": "结果:`pages/*.page.ts` + `selectors/registries/*.ts` 可直接粘贴,共享元素自动归入 `BasePage`。",
    },
    "ja": {
        "title": "mobile-inspect — ビジュアル概要",
        "intro": "Android/iOS アプリのライブ UI ツリーをキャプチャ。Claude が Appium セレクタを見つけ、アプリ全体を自動クロールし、Page Object を直接生成できます。各画面ごとに 3 ファイル出力:`.xml`(ツリー)、`.png`(スクショ)、`.elements.md`(要素表)。",
        "h_what": "1. このスキルは何をする?",
        "h_when": "2. いつ使う?",
        "h_outputs": "3. ページごとの出力 — 3 ファイル並列",
        "h_cheat": "4. チートシート",
        "h_full": "5. 完全ワークフロー — Page Object ライブラリ構築",
        "h_warn": "⚠️ 安全",
        "lbl_situ": "状況",
        "lbl_say": "Claude に言う",
        "lbl_do": "スキルがやる",
        "outputs_intro": "スナップショット(または `--crawl-app` が捕捉する各ページ)ごとに、同じベース名の**3 ファイル**を出力:",
        "outputs_xml": "**`<name>.xml`** — UI ツリーデータ(`--gen-pom` の入力)。",
        "outputs_png": "**`<name>.png`** — ページの実スクショ。後で視覚的コンテキストを振り返ったり、XML と照合したり。",
        "outputs_md": "**`<name>.elements.md`** — 名前付き要素のマークダウン表:`Name | Type | Bounds | Tap` — XML をパースせずに素早く読める。",
        "outputs_skip": "XML だけ欲しい場合は `MOBILE_INSPECT_NO_EXTRAS=1` で 2 ファイルをスキップ。",
        "case1_h": "🔍 ケース1 — 特定要素の名前を探す",
        "case1_situ": "「Like ボタンをクリック」を書きたいけど Like 要素の ID が分からない。",
        "case1_say": '"Like ボタンの selector を探して"',
        "case1_do": "現在の UI を dump → `~LikeButton` や `id/like_btn` を返し、テストに貼れる。",
        "case2_h": "🐛 ケース2 — 「要素が見つからない」エラー",
        "case2_situ": "Appium が `NoSuchElement` を投げるけど、ボタンははっきり見える。",
        "case2_say": '"inspect screen、なぜ Appium は SaveButton を見つけられない?"',
        "case2_do": "UI を dump し、実際の要素名(例:`SaveBtn`、`SaveButton` ではない)やオーバーレイで隠れていることを指摘。",
        "case3_h": "🗺️ ケース3 — アプリ全体を一度にクロール",
        "case3_situ": "プロジェクト参加直後、各タブを手動訪問せず Page Object ライブラリが欲しい。",
        "case3_say": '"エミュレータでアプリ全体をクロール"',
        "case3_do": "各ボトムタブ + トップバーアイコンを自動タップ、ページごとに 3 ファイル出力(`.xml` + `.png` + `.elements.md`)。約 3-5 分。",
        "case4_h": "📦 ケース4 — Page Object をプロジェクトに直接生成",
        "case4_situ": "20 以上の XML があり、ペースト可能な TypeScript を WDIO プロジェクトに直接配置したい。",
        "case4_say": '"POM 生成、/Users/me/Code/my-project に書き出し"',
        "case4_do": "XML を読み、≥2 ページに出る要素を `BasePage` に集約、ページごとに 1 ファイルをプロジェクトに書き込み(`--force` なしでは上書きしない)。",
        "case5_h": "🛟 ケース5 — dump が失敗したら Appium Inspector でフォールバック",
        "case5_situ": "ADB がデバイスを認識しない、WDA がクラッシュ、または dump が空の XML を返す — スキルがエラー。",
        "case5_say": '"dump できない、どうすれば?"',
        "case5_do": "スキルは Appium / UIAutomator2 / XCUITest driver の薄いラッパーで、Appium Inspector と同じ仕組み。[Appium Inspector](https://github.com/appium/appium-inspector) を開き、いつもの capabilities で接続、**Refresh Source** → **Save Source** で XML を取得。`~/.claude/skills/mobile-inspect/snapshots/<platform>/<page>.xml` に置く。スキルの他のコマンド(`--gen-pom`、`--merge`、`format-*`、`suggest-*`、`elements-summary`)はそのまま動く — Inspector とスキルが出す XML は**互換**。",
        "warn_account": "**テストアカウントを使用、本番アカウントは絶対 NG。** スキルは実際にタップします。ログイン中のアカウントでは Like/Comment/Send/Delete/Pay を意図せず発火する可能性。`--crawl-app` はデフォルトでゲストモード + 危険キーワードスキップ。",
        "warn_pii": "**XML + PNG に PII が含まれる可能性。** メール、名前、検索履歴、メッセージプレビュー。`snapshots/` は gitignore 済みですが、機密データとして扱ってください。",
        "tbl_say": "Claude への指示",
        "tbl_run": "スキルが実行",
        "tbl_out": "出力",
        "full_intro": "アプリ全体の Page Object ライブラリを 4 コマンドで構築:",
        "full_steps": [
            "1️⃣ **アプリを開き、Home で停止** — ゲストモード",
            "2️⃣ **自動クロール** — `inspect.sh android --crawl-app`(約 3-5 分)",
            "3️⃣ **テンプレート選択** — `inspect.sh --list-templates`",
            "4️⃣ **生成 + プロジェクトに書き込み** — `inspect.sh android --gen-pom --template cross-platform-registry --target /path/to/wdio-project`",
        ],
        "full_result": "結果:`pages/*.page.ts` + `selectors/registries/*.ts` をペースト可能、共有要素は自動的に `BasePage` に昇格。",
    },
    "ko": {
        "title": "mobile-inspect — 시각 개요",
        "intro": "Android/iOS 앱의 실시간 UI 트리를 캡처합니다. Claude 가 Appium 셀렉터를 찾고, 앱 전체를 자동 크롤링하고, Page Object 를 직접 생성합니다. 캡처된 각 페이지마다 3 개 파일을 출력:`.xml`(트리)、`.png`(스크린샷)、`.elements.md`(요소 표).",
        "h_what": "1. 이 스킬은 무엇을 하나요?",
        "h_when": "2. 언제 사용하나요?",
        "h_outputs": "3. 페이지별 출력 — 3 개 병렬 파일",
        "h_cheat": "4. 치트시트",
        "h_full": "5. 전체 워크플로우 — Page Object 라이브러리 구축",
        "h_warn": "⚠️ 안전",
        "lbl_situ": "상황",
        "lbl_say": "Claude 에게 말하기",
        "lbl_do": "스킬이 함",
        "outputs_intro": "각 스냅샷(또는 `--crawl-app` 이 캡처하는 각 페이지)마다 같은 베이스 이름의 **3 개 형제 파일**을 작성:",
        "outputs_xml": "**`<name>.xml`** — UI 트리 데이터(`--gen-pom` 의 입력).",
        "outputs_png": "**`<name>.png`** — 페이지의 실제 스크린샷. 나중에 시각적 맥락을 다시 보거나, XML 과 대조.",
        "outputs_md": "**`<name>.elements.md`** — 명명된 모든 요소의 마크다운 표:`Name | Type | Bounds | Tap` — XML 을 파싱하지 않고 빠르게 읽기.",
        "outputs_skip": "XML 만 필요하면 `MOBILE_INSPECT_NO_EXTRAS=1` 로 두 추가 파일 스킵.",
        "case1_h": "🔍 케이스 1 — 특정 요소 이름 찾기",
        "case1_situ": "'Like 버튼 클릭' 을 작성 중인데 Like 요소의 ID 를 모름.",
        "case1_say": '"Like 버튼 selector 찾아줘"',
        "case1_do": "현재 UI dump → `~LikeButton` 또는 `id/like_btn` 반환, 테스트에 붙여넣기 가능.",
        "case2_h": "🐛 케이스 2 — 테스트가 '요소를 찾을 수 없음' 실패",
        "case2_situ": "Appium 이 `NoSuchElement` 를 던지는데 버튼이 분명히 보임.",
        "case2_say": '"inspect screen, 왜 Appium 이 SaveButton 을 못 찾아?"',
        "case2_do": "UI dump 후 실제 요소 이름(예:`SaveBtn`, `SaveButton` 이 아님)이나 오버레이가 가렸음을 알려줌.",
        "case3_h": "🗺️ 케이스 3 — 앱 전체 한 번에 크롤링",
        "case3_situ": "프로젝트 합류 직후, 각 탭을 수동 방문하지 않고 Page Object 라이브러리를 원함.",
        "case3_say": '"에뮬레이터에서 앱 전체 크롤"',
        "case3_do": "각 하단 탭 + 상단바 아이콘 자동 탭, 페이지별 3 개 파일 출력(`.xml` + `.png` + `.elements.md`). 약 3-5 분.",
        "case4_h": "📦 케이스 4 — Page Object 를 프로젝트에 직접 생성",
        "case4_situ": "20+ 개 XML 이 있고 붙여넣기 가능한 TypeScript 를 WDIO 프로젝트에 직접 배치하고 싶음.",
        "case4_say": '"POM 생성, /Users/me/Code/my-project 에 쓰기"',
        "case4_do": "XML 을 읽고, ≥2 페이지에 등장하는 요소를 `BasePage` 로 묶고, 페이지별 1 파일을 프로젝트에 작성(`--force` 없이는 덮어쓰지 않음).",
        "case5_h": "🛟 케이스 5 — Dump 실패 시 Appium Inspector 폴백",
        "case5_situ": "ADB 가 디바이스를 못 봄, WDA 가 크래시, 또는 dump 가 빈 XML 을 반환 — 스킬이 에러.",
        "case5_say": '"dump 안 돼, 어떻게 해?"',
        "case5_do": "스킬은 Appium / UIAutomator2 / XCUITest driver 의 얇은 래퍼 — Appium Inspector 와 같은 메커니즘. [Appium Inspector](https://github.com/appium/appium-inspector) 를 열고, 평소 capabilities 로 연결, **Refresh Source** → **Save Source** 클릭 → XML 획득. `~/.claude/skills/mobile-inspect/snapshots/<platform>/<page>.xml` 에 배치. 스킬의 다른 명령(`--gen-pom`, `--merge`, `format-*`, `suggest-*`, `elements-summary`)은 그대로 작동 — Inspector 와 스킬의 XML 은 **호환 가능**.",
        "warn_account": "**테스트 계정 사용, 운영 계정 절대 금지.** 스킬은 실제로 탭합니다. 로그인된 계정에서는 Like/Comment/Send/Delete/Pay 가 의도치 않게 발생 가능. `--crawl-app` 는 기본 게스트 모드 + 위험 키워드 스킵.",
        "warn_pii": "**XML + PNG 에 PII 포함 가능.** 이메일, 이름, 검색 기록, 메시지 미리보기. `snapshots/` 는 gitignore 되어 있지만, 민감한 데이터로 취급.",
        "tbl_say": "Claude 에게 말하기",
        "tbl_run": "스킬 실행",
        "tbl_out": "출력",
        "full_intro": "앱 전체의 Page Object 라이브러리를 4 명령어로 구축:",
        "full_steps": [
            "1️⃣ **앱 열고 Home 에서 정지** — 게스트 모드",
            "2️⃣ **자동 크롤** — `inspect.sh android --crawl-app`(약 3-5 분)",
            "3️⃣ **템플릿 선택** — `inspect.sh --list-templates`",
            "4️⃣ **생성 + 프로젝트에 쓰기** — `inspect.sh android --gen-pom --template cross-platform-registry --target /path/to/wdio-project`",
        ],
        "full_result": "결과:`pages/*.page.ts` + `selectors/registries/*.ts` 바로 붙여넣기 가능, 공유 요소는 자동으로 `BasePage` 로 승격.",
    },
}

# Cheat rows shared across languages (command syntax is universal)
CHEAT_ROWS = [
    ('"inspect screen"', "inspect.sh android", "Full element tree"),
    ('"find selector for X"', '--suggest "X"', "Best selector (id > desc > text > xpath)"),
    ('"list elements"', "--enumerate", "All named elements + Page Object hints"),
    ('"snapshot Home"', "--snapshot home", "Save .xml + .png + .elements.md"),
    ('"crawl whole app"', "--crawl-app", "Auto-snapshot every bottom-tab + sub-screen"),
    ('"merge snapshots"', "--merge", "Cross-page element analysis"),
    ('"list templates"', "--list-templates", "raw / cross-platform / cross-platform-registry"),
    ('"gen POM, write to /path"', "--gen-pom --template ... --target /path", "Write Page Objects straight to project"),
    ('"explore zone"', "--explore-zone top|bottom|middle", "Auto-tap each elem in zone"),
]

# Mermaid (language-agnostic — labels in English so codebase stays universal)
MERMAID_ARCH = """flowchart LR
  A[👤 User] --> B[🤖 Claude]
  B --> C[inspect.sh]
  C -->|Android| D[adb shell<br/>uiautomator dump<br/>+ screencap]
  C -->|iOS| E[WebDriverAgent<br/>:8100]
  D --> F[.xml + .png +<br/>.elements.md]
  E --> F
  F --> G[Selector suggest<br/>+ POM gen]
  G --> B
  style A fill:#e7f3ff
  style F fill:#fff8c5
  style G fill:#dafbe1"""

MERMAID_FULL = """flowchart TD
  A[1️⃣ App on Home] --> B[2️⃣ --crawl-app<br/>~3-5 min]
  B --> C[snapshots/android/<br/>20× .xml + .png + .elements.md]
  C --> D[3️⃣ --list-templates]
  D --> E[4️⃣ --gen-pom<br/>--template ...<br/>--target /path]
  E --> F[💾 pages/*.page.ts<br/>selectors/registries/*.ts]
  style A fill:#fff3cd
  style B fill:#dafbe1
  style E fill:#dafbe1
  style F fill:#e7f3ff"""


# --- SVG mockups ------------------------------------------------------------
def svg_phone(highlight=None, label=None, w=180, h=300):
    hl = ""
    if highlight:
        hl = f'''<rect x="40" y="160" width="100" height="36" fill="#ffe0e0" stroke="#cf222e" stroke-width="2.5"/>
        <text x="90" y="183" text-anchor="middle" font-size="13" font-weight="600" fill="#cf222e">{highlight}</text>'''
    svg = f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
    <rect x="5" y="5" width="{w-10}" height="{h-10}" rx="20" fill="#fff" stroke="#24292e" stroke-width="2.5"/>
    <rect x="{w//2-15}" y="10" width="30" height="4" rx="2" fill="#24292e"/>
    <rect x="20" y="30" width="{w-40}" height="40" fill="#f0f0f0"/>
    <text x="{w//2}" y="55" text-anchor="middle" font-size="11" fill="#666">App Top Bar</text>
    {hl}
    <rect x="20" y="{h-50}" width="{w-40}" height="35" fill="#e8e8e8"/>
    <text x="{w//2}" y="{h-28}" text-anchor="middle" font-size="10" fill="#666">Bottom Tabs</text>
    </svg>'''
    if label:
        return (f'<div style="display:inline-flex;flex-direction:column;align-items:center;gap:6px">'
                f'{svg}<div style="font-size:11px;color:#586069">{label}</div></div>')
    return svg


CASE1_SVG = f'''<div style="display:flex;align-items:center;gap:20px;justify-content:center;flex-wrap:wrap">
{svg_phone(highlight="Like", label="App on emulator")}
<div style="font-size:30px">→</div>
<div style="background:#e7f3ff;border:1px solid #0366d6;border-radius:14px;padding:10px 16px;max-width:200px">
  <div style="font-size:11px;color:#586069">You ask Claude:</div>
  <div style="font-family:ui-monospace,Menlo,monospace;font-size:13px">find selector for Like</div>
</div>
<div style="font-size:30px">→</div>
<div style="background:#dafbe1;border:1px solid #1a7f37;border-radius:8px;padding:14px 18px">
  <div style="font-size:11px;color:#586069;margin-bottom:6px">✅ Skill returns:</div>
  <code style="font-size:14px;font-weight:600">~LikeButton</code>
</div>
</div>'''

CASE2_SVG = '''<div style="display:flex;align-items:center;gap:18px;justify-content:center;flex-wrap:wrap">
<div style="background:#ffebe9;border:1px solid #cf222e;border-radius:8px;padding:14px 18px">
  <div style="font-size:11px;color:#586069">❌ Test code:</div>
  <code style="font-size:13px;display:block">$("~SaveButton")</code>
  <div style="color:#cf222e;font-size:11px">→ NoSuchElement</div>
</div>
<div style="font-size:24px">🔍</div>
<div style="background:#fff8c5;border:1px solid #d4a72c;border-radius:8px;padding:14px 18px">
  <div style="font-size:11px;color:#586069">Skill finds:</div>
  <code style="font-size:13px">name="<b>SaveBtn</b>"</code>
</div>
<div style="font-size:24px">→</div>
<div style="background:#dafbe1;border:1px solid #1a7f37;border-radius:8px;padding:14px 18px">
  <div style="font-size:11px;color:#586069">✅ Fixed:</div>
  <code style="font-size:13px">$("~SaveBtn")</code>
</div>
</div>'''


def svg_mini_phone(n):
    return f'''<svg width="80" height="130" viewBox="0 0 80 130">
  <rect x="5" y="5" width="70" height="120" rx="8" fill="#fff" stroke="#24292e" stroke-width="2"/>
  <rect x="15" y="15" width="50" height="20" fill="#f0f0f0"/>
  <rect x="15" y="40" width="50" height="60" fill="#e8e8e8"/>
  <rect x="15" y="105" width="50" height="15" fill="#d0d0d0"/>
  <text x="40" y="76" text-anchor="middle" font-size="10" font-weight="600" fill="#0366d6">Tab {n}</text>
</svg>'''


CASE3_SVG = f'''<div style="text-align:center">
<div style="display:flex;align-items:center;gap:6px;justify-content:center;margin-bottom:14px;flex-wrap:wrap">
{svg_mini_phone(1)}<span style="font-size:18px">→</span>
{svg_mini_phone(2)}<span style="font-size:18px">→</span>
{svg_mini_phone(3)}<span style="font-size:18px">→</span>
{svg_mini_phone(4)}<span style="font-size:18px">→</span>
{svg_mini_phone(5)}
</div>
<div style="font-size:24px;margin:6px 0">⬇️</div>
<div style="display:inline-block;background:#f6f8fa;border:1px solid #d0d7de;border-radius:8px;padding:14px 22px;font-family:ui-monospace,Menlo,monospace;font-size:12px;text-align:left;line-height:1.7">
  📁 snapshots/android/<br>
  &nbsp;&nbsp;📄 home.xml + home.png + home.elements.md<br>
  &nbsp;&nbsp;📄 shorts.xml + shorts.png + shorts.elements.md<br>
  &nbsp;&nbsp;📄 library.xml + library.png + library.elements.md<br>
  &nbsp;&nbsp;<span style="color:#586069">…20 pages × 3 files each</span>
</div>
</div>'''

CASE4_SVG = '''<div style="display:flex;align-items:center;gap:18px;justify-content:center;flex-wrap:wrap">
<div style="background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:12px 14px;font-family:ui-monospace,Menlo,monospace;font-size:11px;line-height:1.7;text-align:left">
  📁 snapshots/android/<br>
  📄 home.xml<br>
  📄 shorts.xml<br>
  📄 library.xml<br>
  <span style="color:#586069">…20 XML</span>
</div>
<div style="font-size:30px">→</div>
<div style="text-align:center">
  <div style="background:#dafbe1;border:1px solid #1a7f37;border-radius:8px;padding:8px 14px;font-family:ui-monospace,Menlo,monospace;font-size:12px;font-weight:600">
    --gen-pom --target /path
  </div>
  <div style="font-size:24px;margin:6px 0">⬇️</div>
</div>
<div style="background:#fff;border:1px solid #1a7f37;border-radius:8px;padding:12px 14px;font-family:ui-monospace,Menlo,monospace;font-size:11px;line-height:1.7;text-align:left">
  📁 my-wdio-project/<br>
  &nbsp;&nbsp;📁 pages/<br>
  &nbsp;&nbsp;&nbsp;&nbsp;📄 base.page.ts <span style="color:#1a7f37">← shared</span><br>
  &nbsp;&nbsp;&nbsp;&nbsp;📄 home.page.ts<br>
  &nbsp;&nbsp;&nbsp;&nbsp;📄 shorts.page.ts<br>
  &nbsp;&nbsp;📁 selectors/registries/<br>
  &nbsp;&nbsp;&nbsp;&nbsp;📄 base.ts<br>
  &nbsp;&nbsp;<span style="color:#586069">…20+ files</span>
</div>
</div>'''

CASE5_SVG = '''<div style="display:flex;align-items:center;gap:14px;justify-content:center;flex-wrap:wrap">
<div style="background:#ffebe9;border:1px solid #cf222e;border-radius:8px;padding:12px 16px;font-family:ui-monospace,Menlo,monospace;font-size:11px;text-align:left;line-height:1.6">
  ❌ inspect.sh android<br>
  <span style="color:#cf222e">No device / WDA dead / empty dump</span>
</div>
<div style="font-size:24px">→</div>
<div style="background:#fff8c5;border:1px solid #d4a72c;border-radius:8px;padding:14px 18px;text-align:center">
  <div style="font-size:11px;color:#7d4e00;margin-bottom:6px">Use Appium Inspector instead</div>
  <div style="font-weight:600;font-size:13px">Refresh Source<br>↓<br>Save Source</div>
</div>
<div style="font-size:24px">→</div>
<div style="background:#dafbe1;border:1px solid #1a7f37;border-radius:8px;padding:12px 16px;font-family:ui-monospace,Menlo,monospace;font-size:11px;text-align:left;line-height:1.6">
  ✅ snapshots/&lt;plat&gt;/<br>
  &nbsp;&nbsp;home.xml ← from Inspector<br>
  <span style="color:#1a7f37">--gen-pom works as usual</span>
</div>
</div>'''

CASE_SVGS = [None, CASE1_SVG, CASE2_SVG, CASE3_SVG, CASE4_SVG, CASE5_SVG]


# --- HTML template ----------------------------------------------------------
def render_html(lang_code):
    t = T[lang_code]
    options = "\n".join(
        f'  <option value="{f}"{" selected" if c == lang_code else ""}>{fl} {n}</option>'
        for c, n, fl, f in LANGS
    )

    cases = "\n".join(
        f"""  <div class="card">
    <h3>{t[f'case{i}_h']}</h3>
    <p><b>{t['lbl_situ']}:</b> {md_inline(t[f'case{i}_situ'])}</p>
    <div style="margin:12px 0">{CASE_SVGS[i]}</div>
    <p><b>{t['lbl_say']}:</b> <code>{t[f'case{i}_say']}</code></p>
    <p><b>{t['lbl_do']}:</b> {md_inline(t[f'case{i}_do'])}</p>
  </div>"""
        for i in range(1, 6)
    )

    cheat = "\n".join(
        f"<tr><td>{md_inline(say)}</td><td><code>{run}</code></td><td>{out}</td></tr>"
        for say, run, out in CHEAT_ROWS
    )

    full_steps = "\n".join(f"  <li>{md_inline(s)}</li>" for s in t["full_steps"])

    return f"""<!doctype html>
<html lang="{lang_code}">
<head>
<meta charset="utf-8">
<title>{t['title']}</title>
<script src="./mermaid.min.js"></script>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans","Apple SD Gothic Neo","Segoe UI",sans-serif;
       max-width:1100px;margin:40px auto;padding:0 24px;line-height:1.7;color:#24292e;font-size:15px;background:#fafbfc}}
  h1,h2,h3{{border-bottom:1px solid #eaecef;padding-bottom:.3em;margin-top:1.8em;font-weight:600}}
  h1{{font-size:2em;border:0}} h2{{font-size:1.4em}} h3{{font-size:1.15em;border:0;margin-top:0}}
  code{{background:#f6f8fa;padding:2px 6px;border-radius:3px;font-size:.88em;font-family:ui-monospace,Menlo,monospace}}
  pre{{background:#0d1117;color:#c9d1d9;padding:14px;border-radius:6px;overflow:auto}}
  pre code{{background:none;padding:0;color:inherit}}
  table{{border-collapse:collapse;margin:16px 0;width:100%;background:#fff;font-size:.92em}}
  th,td{{border:1px solid #dfe2e5;padding:8px 12px;text-align:left;vertical-align:top}}
  th{{background:#f6f8fa;font-weight:600}}
  .card{{background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:18px 24px;margin:18px 0;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
  .mermaid{{background:#fff;padding:16px;border-radius:6px;border:1px solid #eaecef;text-align:center}}
  .warn{{background:#fff8c5;border:2px solid #d4a72c;border-radius:8px;padding:18px 24px;margin:24px 0}}
  .warn h3{{border:0;margin:0 0 12px;color:#7d4e00}}
  .warn ul{{margin:8px 0;padding-left:22px;line-height:1.8}}
  .warn li{{margin:6px 0}}
  .lang-switch{{position:fixed;top:14px;right:18px;background:#fff;border:1px solid #d0d7de;border-radius:6px;padding:6px 10px;font-size:.85em;color:#24292e;box-shadow:0 1px 3px rgba(0,0,0,.05);cursor:pointer;font-family:inherit}}
</style>
</head>
<body>
<select class="lang-switch" onchange="if(this.value)location.href=this.value">
  <option value="" disabled>🌐 Language</option>
{options}
</select>

<h1>📱 {t['title']}</h1>
<p>{md_inline(t['intro'])}</p>

<h2>{t['h_what']}</h2>
<div class="card"><div class="mermaid">{MERMAID_ARCH}</div></div>

<h2>{md_inline(t['h_when'])}</h2>
<div>
{cases}
</div>

<h2>{md_inline(t['h_outputs'])}</h2>
<div class="card">
<p>{md_inline(t['outputs_intro'])}</p>
<ul style="line-height:2">
  <li>{md_inline(t['outputs_xml'])}</li>
  <li>{md_inline(t['outputs_png'])}</li>
  <li>{md_inline(t['outputs_md'])}</li>
</ul>
<p style="font-size:.92em;color:#586069">{md_inline(t['outputs_skip'])}</p>
</div>

<h2>{t['h_cheat']}</h2>
<table>
<tr><th>{t['tbl_say']}</th><th>{t['tbl_run']}</th><th>{t['tbl_out']}</th></tr>
{cheat}
</table>

<h2>{md_inline(t['h_full'])}</h2>
<div class="card">
<p>{md_inline(t['full_intro'])}</p>
<ol style="line-height:2">
{full_steps}
</ol>
<p>{md_inline(t['full_result'])}</p>
<div class="mermaid">{MERMAID_FULL}</div>
</div>

<div class="warn">
  <h3>{t['h_warn']}</h3>
  <ul>
    <li>{md_inline(t['warn_account'])}</li>
    <li>{md_inline(t['warn_pii'])}</li>
  </ul>
</div>

<script>
mermaid.initialize({{startOnLoad:true, theme:'default', flowchart:{{curve:'basis'}}}});
</script>
</body>
</html>"""


def main():
    # Download mermaid v10 UMD (works via file:// and http://)
    mm = OUT / "mermaid.min.js"
    if not mm.exists() or mm.stat().st_size < 1_000_000:
        print("Downloading mermaid v10...")
        urllib.request.urlretrieve(
            "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js", mm
        )

    for code, name, flag, fname in LANGS:
        (OUT / fname).write_text(render_html(code))
        print(f"  ✓ {fname}")

    # index.html redirects to English version
    (OUT / "index.html").write_text(
        '<!doctype html><meta charset=utf-8>'
        '<meta http-equiv=refresh content="0; url=visual.en.html">'
        '<link rel=canonical href=visual.en.html>'
        '<p>Redirecting… <a href="visual.en.html">click here</a></p>'
    )

    # Bundle README
    (OUT / "README.md").write_text("""# Visual docs — mobile-inspect

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
""")
    print(f"\nDone. Open: file://{OUT}/index.html")


if __name__ == "__main__":
    main()
