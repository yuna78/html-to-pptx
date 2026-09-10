---
name: html-to-pptx
description: >-
  Convert an existing slide-shaped HTML file (report, deck, dashboard) into a truly
  editable PowerPoint .pptx — every paragraph, table cell, colour block and chart bar
  becomes a native DrawingML shape you can retype and recolour in PowerPoint, not a
  screenshot of the page. Layout comes from a real headless Chrome render, so fidelity
  is high. Use when the user says "html to pptx", "convert this HTML to PowerPoint",
  "export the deck/report as an editable ppt", or 把 HTML 转成 PPT、html 转 ppt、
  导出成 pptx、生成可编辑的 PowerPoint、把这个报告/幻灯片/dashboard 做成 PPT。
  Works best on fixed-canvas decks (one screen per page) but also paginates long
  scrolling reports. NOT for authoring a brand-new HTML deck from scratch — this skill
  only converts HTML that already exists.
tags: [ppt, pptx, html, powerpoint, presentation, export, editable]
license: MIT
---

# html-to-pptx

Convert **slide-shaped HTML** into an **editable PowerPoint deck**.
把**幻灯片式 HTML** 转成**可编辑的 PowerPoint**。

Pipeline / 管线：`HTML → real browser layout → editable SVG primitives → native DrawingML → .pptx`

The output is **tier-1 editable**: every run of text, table cell, colour block and chart
bar/line/label is a native PowerPoint shape. Nothing is rasterised into a page image.
产物是**真可编辑**：每段文字、每个表格单元格、每个色块、图表里的柱/线/标签都是 PPT 原生形状
——不是把整页截成一张图。

## When to use / 何时用

- ✅ The user already has an HTML report, deck or dashboard and wants a `.pptx` they can
  keep editing. 用户已有 HTML，想要能二次编辑的 pptx。
- ✅ Fixed-canvas, one-screen-per-page HTML (any canvas size — 1280×720, 1600×900 …).
  固定画布、每页一屏的 HTML（任意画布尺寸）。
- ✅ Long scrolling reports too — they are paginated automatically. 长滚动报告也能转，会自动分页。
- ❌ The user wants a **new** deck designed from scratch → that is a deck-authoring skill's job.
  用户想**从零新做**一套幻灯片 → 那不是本 skill 的活。
- ❌ The user wants an **image-per-slide** PPT (AI-rendered pictures) → use an image-deck skill.

## Prerequisites / 环境依赖

| Needed | Why | If missing |
|---|---|---|
| **Node.js** ≥ 22 | runs the DOM→SVG extractor (no npm install needed) | `node: command not found` |
| **Google Chrome / Chromium** | headless layout engine, auto-discovered | conversion fails / Chrome not found |
| **Python** ≥ 3.11 + this skill's `.venv` | python-pptx + beautifulsoup4, created on first run | `ModuleNotFoundError` |
| **CJK fonts** (for Chinese decks) | text and chart labels | boxes instead of glyphs (rare on macOS) |

Check everything at once / 一键自检：

```bash
"$HOME/.claude/skills/html-to-pptx/bin/html-to-pptx" --doctor
```

It prints one line per prerequisite and the exact install command for anything missing.
The venv is created automatically on first use — no separate setup step.

## Usage / 用法

Always prefer the wrapper — it bootstraps the environment, then converts:

```bash
H2P="$HOME/.claude/skills/html-to-pptx/bin/html-to-pptx"

# Default: report.pptx lands NEXT TO the input HTML, same folder, same name
"$H2P" /path/to/report.html

# Explicit output file or directory
"$H2P" /path/to/report.html -o /path/to/deck.pptx

# Force a canvas size (default is measured from the deck itself)
"$H2P" /path/to/deck.html --canvas 1600x900

# Escape hatches when a transform makes things worse
"$H2P" deck.html --no-prepare      # hand the HTML to the engine untouched
"$H2P" deck.html --no-reshape      # keep prepare, skip table/rich-text reshaping
"$H2P" deck.html --no-pseudo       # skip ::before / ::after materialisation
"$H2P" deck.html --keep-prepared   # keep the intermediate HTML for debugging
"$H2P" deck.html --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

**Output location rule / 产物位置约定**: with no `-o`, the `.pptx` is written to the same
directory as the source HTML with the same base name. 默认产物与来源 HTML **同目录同名**。
Report that absolute path back to the user, and send the file with `SendUserFile`.

## What the conversion does for you / 转换替你做的事

Run automatically before rendering (all can be turned off individually):

1. **Pagination / 切页** — tags `.slide` / `.cover` pages; a scrolling report is cut into
   fixed-canvas pages on block boundaries (a table too long for one page is split by rows,
   with the header repeated — no row is ever lost).
2. **Canvas detection / 画布探测** — the first page is measured and the PPTX slide size
   matches it. 1280×720, 1600×900 or anything else all work.
3. **Reshaping for the extractor / 版式重整** — three HTML shapes lose content otherwise:
   multi-line table cells, `<b>` inside a text-bearing `<div>`, and `<br>` runs.
   See [`docs/how-it-works.md`](./docs/how-it-works.md).
4. **Offline charts / 图表离线化** — an ECharts CDN tag is swapped for a vendored bundle so
   charts still draw under the zero-network render.
5. **Gradients & pseudo elements / 渐变与伪元素** — CSS gradients are flattened to a
   representative solid colour, and `::before` / `::after` dots, badges and glyphs become
   real shapes.
6. **Interactive controls / 交互控件** — segmented filters, tab strips and `<select>`
   collapse to the value that is currently selected.

## Troubleshooting / 排查

| Symptom | Fix |
|---|---|
| `node: command not found` | `brew install node` (macOS) / `apt install nodejs` |
| Chrome not found | install Google Chrome, or pass `--chrome <path>` |
| `ModuleNotFoundError: pptx` | run the wrapper `bin/html-to-pptx`, which builds the venv |
| Only 1 slide came out | the HTML has no page structure the converter recognises — check it is slide-shaped, or let prepare paginate it (it is on by default) |
| Multi-line cell collapsed / `<b>` text missing / lines glued together | reshaping was disabled (`--no-reshape`), or that table is not classified as dense |
| Column widths drift after conversion | the deck sets widths via `<col width>`; add inline `style="width:…"` on the cells |
| Chart is black | chart colours come from a CSS variable stripped at render time — the vendored engine patch normally handles this; report it as a bug |
| Chinese text renders as boxes | install a CJK font on the machine |

## Repo / 仓库

This skill is a standalone open-source repo — it also runs as a plain CLI without Claude.
本 skill 同时是一个独立开源仓库，脱离 Claude 也能当命令行工具用。
Details: [`README.md`](./README.md) · internals: [`docs/how-it-works.md`](./docs/how-it-works.md)
· engine provenance: [`engine/UPSTREAM.md`](./engine/UPSTREAM.md).
