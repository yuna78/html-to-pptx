# How it works

> 中文版：[`how-it-works.md`](./how-it-works.md)

This document explains the parts that are not obvious from the code: why a
pre-conversion transform exists at all, and which HTML shapes silently lose content
without it.

## The pipeline

```
source.html
   │  prepare.py                    (pure Python, BeautifulSoup — no browser)
   ▼
prepared.html                       throwaway copy; your original file is never modified
   │  engine/html_dom_to_editable_svg.js
   │  ─ launches headless Chrome with zero network access
   │  ─ shows one page at a time and reads the computed layout
   ▼
one SVG per page                    <rect>, <text>, <path> primitives
   │  engine/svg_to_pptx/
   ▼
output.pptx                         native DrawingML shapes, editable in PowerPoint
```

Chrome is used **only as a layout engine**. Nothing is rasterised: the extractor asks the
DOM where each box, line and text run ended up, and writes a primitive for it.

## The extractor's one rule

`engine/html_dom_to_editable_svg.js` walks the DOM with a hit-and-return rule:

```js
if (shouldEmitText(el)) { emit(text of el); return; }   // stops descending here
for (const child of el.children) walk(child);
```

`shouldEmitText` takes `innerText` — the **whole subtree** — for non-`DIV` text tags
(`TD`, `TH`, `LI`, `P`, `SPAN`, `B` …), but only the **direct text nodes** for a `DIV`.
That single asymmetry produces every content-loss case below.

### Case 1 — a table cell with several lines

`<td>` containing `<ul>`, `<ol>` or several block children collapses into a single run:
the line boundaries are gone.

**Fix**: retag the whole table family (`table`, `tr`, `td`, …) as `<div>`s carrying the
equivalent `display: table-*` value. The layout — including automatic column widths — is
identical, but the walk now takes the `DIV` branch and keeps descending, so each line emits
its own text shape.

Two details make that safe:

- **CSS carry-over.** `td.wide{width:120px}` stops matching once the cell is a `<div>`.
  Every rule whose selector mentions a table tag is duplicated with `td` rewritten as
  `[data-was="td"]`, so column widths survive. Without this step the content is right and
  the layout is wrong — this is the step that lets the converter eat HTML it did not write.
- **`colspan` expansion.** `display: table` ignores `colspan`, so a merged cell would only
  paint one column; it is padded with empty cells that carry the same classes.

Only **dense** tables are touched — a table is dense when a cell holds a list, a `<br>`,
or two or more block children. A plain one-value-per-cell table is left exactly as it is,
so simple data tables cannot regress.

### Case 2 — `<div>text <b>bold</b> more text</div>`

The `DIV` has direct text, so the walk emits that text and returns — **the text inside
`<b>` disappears entirely**.

**Fix**: flatten the element to plain text. The cost is that inline bolding inside that
one element becomes a single weight; the alternative was losing the sentence. `DIV`s with
*only* inline children and no bare text are left alone — those descend fine and keep their
bold.

### Case 3 — `<br>`

Whitespace is collapsed during text cleanup, so lines separated by `<br>` are glued into
one run.

**Fix**: split at each `<br>` into block-level line `<div>`s. Visually equivalent — a
`<br>` *is* a line break — and each line now emits its own shape.

### Case 4 — things that are not in the DOM at all

Three decorations exist only in the CSS layer, so no DOM walk can see them. They are fixed
in a small script that runs inside the same headless Chrome, where computed styles are
available:

| Decoration | Fix |
|---|---|
| CSS `linear-gradient` / `radial-gradient` backgrounds | replaced by a representative solid colour from the gradient (a white-on-dark gradient header would otherwise vanish completely) |
| `::before` / `::after` dots, badges, glyphs | materialised into real `<span>`s that copy the pseudo element's computed box, then the pseudo is suppressed |
| `<ol>` numbers from CSS counters | written into the `<li>` as real text |

When a pseudo element is materialised, the host element's bare text is wrapped in a span
too — otherwise the host would emit its own text and return (case 2 again) and the freshly
injected decoration would never be visited.

## Pagination

- **Slide-shaped input** (`.deck-slide` / `.slide` / `.cover`): each page is tagged and
  exported as one slide.
- **Scroll-shaped input**: top-level blocks are grouped into fixed-canvas pages. Charts and
  sections get a page each, small blocks (header, KPI strip) accumulate onto the first, and
  a table longer than one page is split by rows with its heading and `<thead>` repeated.
  Totals in `<tfoot>` and anything after the table stay on the last page. **No row is ever
  dropped** — the test suite asserts it.

## Canvas size

Before extraction the first page is measured and Chrome is re-sized to match, and the PPTX
slide size follows the generated SVG's viewBox. A deck declaring 1600×900 exports at
1600×900. `--canvas WxH` overrides the measurement when a deck's own CSS is misleading.

## Zero-network rendering

Chrome is launched with `--host-resolver-rules=MAP * ~NOTFOUND`: every hostname fails to
resolve. A deck cannot phone home, probe cloud metadata or exfiltrate a local file during
conversion. The consequence is that **remote assets are not fetched** — inline your images,
CSS and fonts. ECharts loaded from a CDN is swapped for the vendored bundle so charts still
draw.
