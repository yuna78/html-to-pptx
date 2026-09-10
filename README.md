# html-to-pptx

**Turn an HTML deck into a PowerPoint file you can actually edit.**
**把 HTML 幻灯片转成真正可以编辑的 PowerPoint。**

Most "HTML → PPT" tools screenshot each page and drop the image on a slide. This one
renders your page in a real headless Chrome, reads the resulting layout, and rebuilds it
as **native DrawingML shapes**: every paragraph, table cell, colour block and chart
bar is a normal PowerPoint object you can retype, recolour and move.

大多数「HTML → PPT」工具是把每页截图贴进幻灯片。本项目用真实的无头 Chrome 渲染页面、读取布局，
再重建成 **PPT 原生形状**：每段文字、每个表格单元格、每个色块、每根图表柱子，都是能改字、改色、
挪位置的普通 PowerPoint 对象。

```bash
bin/html-to-pptx report.html      # → report.pptx, right next to report.html
```

- Works with **any canvas size** — 1280×720, 1600×900, A4-ish, whatever your deck declares.
- Handles **long scrolling reports** too: they are paginated on block boundaries, tables
  split by rows with the header repeated.
- **Zero network** while rendering: the browser resolves no hostnames, so a deck can never
  phone home or leak local files during conversion.
- No cloud service, no API key, nothing uploaded. Everything runs on your machine.

---

## Table of contents

[Install](#install) · [Prerequisites](#prerequisites--环境依赖) · [Usage](#usage--用法) ·
[Options](#options--参数) · [How it works](#how-it-works--工作原理) ·
[Limitations](#limitations--已知限制) · [Troubleshooting](#troubleshooting--排查) ·
[Development](#development--开发) · [Credits](#credits--致谢)

---

## Install

### As a Claude Code / Claude Desktop skill

Clone into your skills directory; the folder name becomes the skill name:

```bash
git clone https://github.com/yuna78/html-to-pptx.git ~/.claude/skills/html-to-pptx
~/.claude/skills/html-to-pptx/bin/html-to-pptx --doctor
```

Then just ask: *"convert this HTML report to an editable PPT"* / *「把这个 HTML 转成可编辑的 PPT」*.

### As a plain command-line tool

```bash
git clone https://github.com/yuna78/html-to-pptx.git
cd html-to-pptx
./bin/html-to-pptx examples/sample-deck.html -o /tmp/sample.pptx
```

The first run creates a local `.venv` and installs two Python packages. There is no
separate setup step, and nothing is installed system-wide.

## Prerequisites / 环境依赖

| Requirement | Why it is needed | Install |
|---|---|---|
| **Node.js ≥ 22** | runs the DOM→SVG extractor (uses only Node built-ins, no `npm install`) | `brew install node` · `apt install nodejs` |
| **Google Chrome or Chromium** | used headlessly as the layout engine | [google.com/chrome](https://www.google.com/chrome/) · `apt install chromium-browser` |
| **Python ≥ 3.11** | `python-pptx` + `beautifulsoup4`, installed into a local venv on first run | preinstalled on macOS; `apt install python3-venv` |
| **CJK fonts** (Chinese/Japanese/Korean decks) | text and chart labels | preinstalled on macOS; `apt install fonts-noto-cjk` |

Check them all with one command:

```bash
bin/html-to-pptx --doctor
```

It prints a ✓/✗ line per prerequisite plus the exact command to fix anything missing.

## Usage / 用法

```bash
# Output goes next to the input, same base name
bin/html-to-pptx path/to/report.html

# Explicit output path (a directory works too)
bin/html-to-pptx path/to/report.html -o path/to/deck.pptx

# Force the canvas size instead of measuring it
bin/html-to-pptx deck.html --canvas 1600x900

# Feed the HTML to the engine untouched
bin/html-to-pptx deck.html --no-prepare
```

**Where the file lands / 产物位置**: without `-o`, the `.pptx` is written to the *same
directory as the source HTML*, with the same base name — so the deck and its export stay
together. 默认 `.pptx` 与来源 HTML **同目录同名**。

### What your HTML should look like / 输入契约

The converter is happiest with a **fixed-canvas deck**: one element per page, with an
explicit pixel width and height.

```html
<section class="slide" style="width:1280px;height:720px">…page 1…</section>
<section class="slide" style="width:1280px;height:720px">…page 2…</section>
```

Recognised page classes: `.deck-slide`, `.slide`, `.cover`. If none is present the document
is treated as a scrolling report and paginated automatically. Inline your CSS, images and
fonts — the render has no network access, so remote assets simply will not load.

> Writing a new deck? Avoid `<table>` for pure layout. Semantically it is not tabular data,
> and the converter has to work much harder to keep it intact.

## Options / 参数

| Flag | Meaning |
|---|---|
| `-o, --output PATH` | output `.pptx` file or directory (default: beside the input) |
| `--canvas auto\|WxH` | slide size in CSS px; `auto` measures the first page (default) |
| `--no-prepare` | skip all pre-conversion transforms |
| `--no-reshape` | keep prepare, skip dense-table / rich-text reshaping |
| `--no-pseudo` | do not materialise `::before` / `::after` decorations |
| `--keep-prepared` | write the intermediate HTML next to the input for inspection |
| `--chrome PATH` | Chrome/Chromium executable (default: auto-discovered) |
| `--doctor` | check prerequisites and exit |
| `--quiet` | less output |

## How it works / 工作原理

```
your.html
   │  prepare.py        pagination · canvas sizing · reshaping · offline charts
   ▼
prepared.html
   │  headless Chrome   real CSS layout, computed styles, rendered charts
   ▼
editable SVG            rects, text runs, paths — one file per page
   │  svg_to_pptx
   ▼
your.pptx               native DrawingML shapes, one slide per page
```

The interesting part is the middle: the extractor walks the rendered DOM and emits a
primitive per visual element rather than a picture, which is what makes the result
editable. A handful of HTML shapes lose content in that walk, and `prepare.py` rewrites
them first — multi-line table cells, `<b>` inside a text-bearing `<div>`, `<br>` runs,
CSS-counter list markers, gradients and pseudo elements.
The full explanation, with the exact rule that causes each case, is in
[`docs/how-it-works.md`](./docs/how-it-works.md).

## Limitations / 已知限制

- **Text wrapping is per element.** A paragraph that wraps across several lines is emitted
  as one text shape positioned at the element's box; long prose can therefore sit slightly
  differently than in the browser. Slide-style content (short lines) is unaffected.
- **`rowspan` is not expanded** when a dense table is reshaped — it leaves a gap rather
  than a misalignment.
- **Inline bold inside a mixed text+`<b>` `<div>` becomes a single weight.** The
  alternative was losing that text entirely; see `docs/how-it-works.md`.
- **Animations, transitions, video and iframes** do not survive — a slide is a static page.
- **Remote assets are not fetched.** Inline them, or they will be missing.
- **`<col width>` column sizing** is not carried across the table reshape; use cell-level
  widths.

## Troubleshooting / 排查

| Symptom | What to do |
|---|---|
| `node: command not found` / `no global WebSocket` | install Node.js ≥ 22 |
| Chrome not found | install Chrome/Chromium, or pass `--chrome <path>` |
| `ModuleNotFoundError: pptx` / `bs4` | use `bin/html-to-pptx` (it builds the venv), or run `bash setup.sh` |
| Only one slide in the output | no page structure was recognised; check the page class names above |
| A cell's lines are glued together, or `<b>` text is missing | reshaping is off (`--no-reshape`) or that table was not classified as dense |
| Column widths drift | the deck sizes columns via `<col width>`; move the width onto the cells |
| Chart renders black | chart fills come from CSS variables removed at render time — normally patched; please open an issue |
| Chinese text shows as boxes | install a CJK font |
| Layout looks worse after conversion | try `--no-reshape`, then `--no-prepare`, and open an issue with the input |

## Development / 开发

```bash
bash setup.sh                                   # venv + dependency check
.venv/bin/pip install -r requirements-dev.txt   # adds pytest
.venv/bin/python -m pytest tests -q             # unit tests + end-to-end smoke test
```

`tests/test_prepare.py` is pure Python and runs anywhere. `tests/test_smoke.py` converts
real decks and is skipped automatically when Node or Chrome is unavailable.

Layout of the repo:

| Path | What it is |
|---|---|
| `convert.py` | CLI: preflight checks, prepare, engine invocation |
| `prepare.py` | pre-conversion DOM transforms (pagination, reshaping, controls) |
| `engine/` | vendored HTML→SVG→PPTX engine (see `engine/UPSTREAM.md`) |
| `bin/html-to-pptx` | one-command wrapper that bootstraps the venv |
| `vendor/echarts.min.js` | offline ECharts bundle for zero-network chart rendering |
| `examples/` | sample decks used by the smoke test |

Contributions welcome — see [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Credits / 致谢

- Conversion engine: [`GX-Alex/html2pptx`](https://github.com/GX-Alex/html2pptx) (MIT),
  vendored with local patches documented in [`engine/UPSTREAM.md`](./engine/UPSTREAM.md).
- [Apache ECharts](https://echarts.apache.org/) (Apache-2.0) for offline chart rendering.
- [Font Awesome Free](https://fontawesome.com/license/free) (CC BY 4.0) icon paths.
- [python-pptx](https://python-pptx.readthedocs.io/) (MIT) and
  [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) (MIT).

Licensed under the [MIT License](./LICENSE). Third-party notices: [`NOTICE`](./NOTICE).
