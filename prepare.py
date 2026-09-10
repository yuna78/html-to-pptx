"""Pre-conversion transform: turn arbitrary report/deck HTML into a conversion-friendly variant.

Key design: this runs **at export time only** — it never rewrites the HTML the user
looks at in a browser. The original file keeps its interactivity; the converter is fed
a throwaway copy.

Two paths, picked automatically by shape detection:

* **Slide-shaped** (has ``.slide`` / ``.cover`` / ``.deck-slide``): tag the pagination
  class, neutralise ``transform: scale()`` fit-to-viewport wrappers, flatten interactive
  controls into static text.
* **Scroll-shaped** (a long scrolling report, no slide structure): inline ECharts offline
  (so charts still render with zero network access) and paginate top-level semantic blocks
  into fixed-canvas slides.

Everything here is BeautifulSoup DOM surgery — pure Python, no browser, unit-testable.
A small runtime script is injected for the two things that genuinely need computed styles
(CSS gradients and ``::before`` / ``::after`` pseudo elements); it runs in the headless
Chrome that the engine already launches.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

DEFAULT_CANVAS = (1280, 720)

# Style overrides injected into <head>:
#   --scale / .frame  → common "fit the deck into the viewport" wrappers use a CSS variable
#                        or a transform on .frame; both must be neutralised or every slide
#                        is exported at the shrunken on-screen size.
#   .deck-slide       → make every page visible to the extractor (it shows them one by one).
_OVERRIDE_CSS = (
    ":root{--scale:1!important}"
    ".frame{transform:none!important}"
    ".deck-slide{display:block!important}"
    "[data-pseudo-materialized]::before{content:none!important}"
    "[data-pseudo-materialized-after]::after{content:none!important}"
)

# Offline ECharts bundle (vendored). Charts drawn by ECharts from a CDN would silently
# disappear under the engine's zero-network render, so the CDN <script> is swapped for this.
_ECHARTS_BUNDLE = Path(__file__).parent / "vendor" / "echarts.min.js"
# Placeholder first, raw string replacement last: BeautifulSoup would escape the < > &
# inside 1 MB of minified JS and break it.
_ECHARTS_PLACEHOLDER = "/*__HTML2PPTX_ECHARTS_INLINE__*/"

# Match core echarts only (echarts.min.js / echarts.js), not extensions (echarts-gl.min.js …)
_ECHARTS_CORE_RE = re.compile(r"(^|/)echarts(\.min)?\.js($|\?)", re.I)
# Non-content tags skipped when slicing a scrolling page into blocks
_SKIP_BLOCK_TAGS = {"script", "style", "template", "link", "meta", "noscript"}

# Rows of table body that fit on one generated page (static estimate:
# ~550px usable height / ~34px per row).
_ROWS_PER_PAGE = 16


@dataclass
class PrepareStats:
    """What the transform actually touched — printed by the CLI so surprises are visible."""

    shape: str = "slide"            # "slide" | "scroll"
    pages_generated: int = 0        # pages created by scroll pagination
    slides_tagged: int = 0          # existing .slide/.cover elements tagged for pagination
    echarts_inlined: bool = False
    controls_flattened: int = 0     # interactive filters/selects turned into static text
    reshape: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        bits = [f"shape={self.shape}"]
        if self.pages_generated:
            bits.append(f"paginated={self.pages_generated}")
        if self.slides_tagged:
            bits.append(f"slides={self.slides_tagged}")
        if self.echarts_inlined:
            bits.append("echarts=inlined")
        if self.controls_flattened:
            bits.append(f"controls={self.controls_flattened}")
        for key, value in (self.reshape or {}).items():
            if value:
                bits.append(f"{key}={value}")
        return " · ".join(bits)


def _has_class(tag, name: str) -> bool:
    return name in (tag.get("class") or [])


def _is_slide_shaped(soup) -> bool:
    """True when the document already looks like a deck (``.slide`` / ``.cover`` / ``.deck-slide``)."""
    return soup.find(
        lambda t: _has_class(t, "slide") or _has_class(t, "cover") or _has_class(t, "deck-slide")
    ) is not None


# ─────────────────────────────────────────────────────────────────────
# Scroll-shaped reports → paginated deck
# ─────────────────────────────────────────────────────────────────────

def _inline_echarts_offline(soup) -> bool:
    """Replace the ECharts CDN <script src> with an inline placeholder for the vendored bundle.

    Only acts when the local bundle exists; otherwise the original CDN script is left alone
    (it still works for anyone rendering online).
    """
    if not _ECHARTS_BUNDLE.exists():
        return False
    inlined = False
    for script in soup.find_all("script", src=True):
        if not _ECHARTS_CORE_RE.search(script.get("src") or ""):
            continue  # not core echarts (extension bundle / unrelated library)
        if not inlined:
            new = soup.new_tag("script")
            new.string = _ECHARTS_PLACEHOLDER
            script.replace_with(new)
            inlined = True
        else:
            script.decompose()  # drop duplicate CDN tags rather than inline 1 MB twice
    return inlined


def _block_kind(block) -> str:
    classes = set(block.get("class") or [])
    if "chart-row" in classes:
        return "chart"
    if "section" in classes or block.name in {"section", "article"}:
        return "section"
    if "footer" in classes or block.name == "footer":
        return "footer"
    return "small"  # header / KPI grid / subtitle and friends


def _split_table_section(section):
    """Split a section whose table has more rows than fit on one page into several copies.

    Each copy repeats the section heading and ``<thead>`` and keeps only its slice of
    ``<tbody>`` rows. No row is lost. ``<tfoot>`` totals and anything after the table
    (footnotes, a second table) stay on the last page instead of repeating.
    """
    table = section.find("table")
    if table is None:
        return [section]
    tbody = table.find("tbody", recursive=False)  # direct child only; ignore nested tables
    if tbody is None:
        return [section]  # non-standard structure — be conservative, do not split
    rows = tbody.find_all("tr", recursive=False)
    if len(rows) <= _ROWS_PER_PAGE:
        return [section]
    chunks = [rows[i:i + _ROWS_PER_PAGE] for i in range(0, len(rows), _ROWS_PER_PAGE)]
    last = len(chunks) - 1
    parts = []
    for index, chunk in enumerate(chunks):
        page = copy.copy(section)  # deep copy: heading + table head + body
        page_table = page.find("table")
        page_tbody = page_table.find("tbody", recursive=False)
        for row in list(page_tbody.find_all("tr", recursive=False)):
            row.extract()  # empty the cloned body
        for row in chunk:
            page_tbody.append(copy.copy(row))
        if index != last:
            tfoot = page_table.find("tfoot", recursive=False)
            if tfoot is not None:
                tfoot.decompose()
            for sibling in list(page_table.find_next_siblings()):
                sibling.decompose()
        parts.append(page)
    return parts


def _paginate_scroll(soup, canvas: tuple[int, int]) -> int:
    """Slice a scrolling report into fixed-canvas ``.deck-slide`` pages.

    Charts and sections get a page each; footers join the last page; small blocks
    (header, KPI strip, subtitle) accumulate onto the first. Cuts always land on block
    boundaries — a chart or table is never sliced in half.
    """
    container = soup.find(class_="container") or soup.body
    if container is None:
        return 0
    blocks = [
        b for b in container.find_all(recursive=False)
        if getattr(b, "name", None) and b.name not in _SKIP_BLOCK_TAGS
    ]
    if len(blocks) < 2:
        return 0  # a single block needs no pagination

    pages: list[list] = []
    current: list = []
    for block in blocks:
        kind = _block_kind(block)
        if kind in ("chart", "section"):
            if current:
                pages.append(current)
                current = []
            if kind == "section":
                parts = _split_table_section(block)
                for part in parts:
                    pages.append([part])
                if len(parts) > 1 or parts[0] is not block:
                    block.decompose()  # the oversized original was copied onto each page
            else:
                pages.append([block])
        elif kind == "footer":
            (pages[-1] if pages else current).append(block)
        else:
            current.append(block)
    if current:
        pages.append(current)
    if not pages:
        return 0

    width, height = canvas
    # The generated page carries its size explicitly: a surrounding `max-width` container
    # would otherwise squeeze it and the canvas would be measured too narrow.
    frame_style = (
        f"width:{width}px;height:{height}px;max-width:none;margin:0;"
        "box-sizing:border-box;overflow:hidden;background:#fff"
    )
    page_style = (
        f"width:{width}px;height:{height}px;box-sizing:border-box;"
        "padding:44px 56px;background:#fff;overflow:hidden"
    )
    for page in pages:
        section = soup.new_tag("section")
        section["class"] = ["slide", "deck-slide"]
        section["style"] = frame_style
        inner = soup.new_tag("div")
        inner["style"] = page_style
        for block in page:
            inner.append(block.extract())
        section.append(inner)
        container.append(section)
    return len(pages)


# ─────────────────────────────────────────────────────────────────────
# Reshaping for the extractor
#
# The extractor walks the DOM with one hit-and-return rule
# (engine/html_dom_to_editable_svg.js):
#
#     if (shouldEmitText(el)) { emit(text of el); return; }   // stops descending
#     for (child of el.children) walk(child)
#
# `shouldEmitText` takes `innerText` — the whole subtree — for non-DIV text tags
# (TD/TH/LI/P/SPAN/B…), but only the direct text nodes for a DIV. That produces three
# shapes where content silently disappears; each is fixed below:
#
#   (1) <td> holding several lines or a list  → the cell collapses into one run
#   (2) <div>bare text + <b>inline</b></div>  → the text inside <b> vanishes entirely
#   (3) <br> anywhere                         → lines are glued together by whitespace
#       collapsing
# ─────────────────────────────────────────────────────────────────────

_INLINE_TAGS = {"b", "strong", "span", "em", "i", "code", "small", "u", "a", "mark", "sub", "sup"}
_BLOCK_TAGS = {"div", "p", "ul", "ol", "table", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}

# <table> family → the equivalent CSS display value. Rendered as DIVs the layout is
# byte-identical (automatic column widths included), but the extractor takes its DIV
# branch and keeps descending, so every child emits its own text.
_TABLE_DISPLAY = {
    "table": "table", "thead": "table-header-group", "tbody": "table-row-group",
    "tfoot": "table-footer-group", "tr": "table-row", "td": "table-cell",
    "th": "table-cell", "caption": "table-caption", "colgroup": None, "col": None,
}


def _is_dense_cell(cell) -> bool:
    """Is this cell multi-line? Only multi-line cells get collapsed; one-value cells are safe."""
    if cell.find(["ul", "ol"]):
        return True
    if cell.find("br"):
        return True
    return len([c for c in cell.children if getattr(c, "name", None) in _BLOCK_TAGS]) >= 2


def _expand_colspans(table) -> None:
    """``display: table`` ignores ``colspan`` → a merged cell would only paint one column.

    Pad with (N-1) empty cells carrying the same classes so background and borders stay
    continuous. ``rowspan`` is left alone (rare in decks; it leaves a gap, not a misalignment).
    """
    for cell in table.find_all(["td", "th"]):
        try:
            span = int(cell.get("colspan") or 1)
        except ValueError:
            span = 1
        if span <= 1:
            continue
        del cell["colspan"]
        anchor = cell
        for _ in range(span - 1):
            filler = BeautifulSoup("<td></td>", "html.parser").td
            if cell.get("class"):
                filler["class"] = list(cell["class"])
            filler["data-export-filler"] = "1"
            anchor.insert_after(filler)
            anchor = filler


def _reshape_dense_tables(soup) -> int:
    """Dense tables: retag ``<td>`` & co as ``display:table-*`` DIVs so the extractor descends.

    Only dense tables are touched — a plain one-value-per-cell table is left exactly as is,
    so this cannot regress simple data tables.
    """
    count, renamed = 0, set()
    for table in soup.find_all("table"):
        cells = table.find_all(["td", "th"])
        if not any(_is_dense_cell(c) for c in cells):
            continue  # sparse table: leave alone
        _expand_colspans(table)
        for element in [table] + table.find_all(True):
            display = _TABLE_DISPLAY.get(element.name)
            if display is None and element.name in _TABLE_DISPLAY:
                element.decompose()  # <col>/<colgroup> would become stray empty boxes
                continue
            if display is None:
                continue
            style = (element.get("style") or "").rstrip().rstrip(";")
            element["style"] = (style + ";" if style else "") + f"display:{display}"
            renamed.add(element.name)
            element["data-was"] = element.name
            element.name = "div"
        count += 1
    if count:
        _carry_table_css(soup, renamed)
    return count


_TABLE_TAG_RE = re.compile(r"(?<![\w.#\-\[])(table|thead|tbody|tfoot|tr|td|th|caption)(?![\w\-\]])")


def _carry_table_css(soup, renamed_tags: set) -> int:
    """Keep table CSS working after the retag.

    ``td.col-wide{width:112px}`` stops matching once the cell is a DIV, and column widths
    drift. Every rule whose selector mentions a table tag is therefore duplicated with
    ``td`` rewritten as ``[data-was="td"]`` and appended to the stylesheet. The original
    rules stay untouched. This is the step that lets the converter eat HTML it did not write.
    """
    if not renamed_tags:
        return 0
    added = 0
    for style in soup.find_all("style"):
        css = style.string or ""
        if not css or "data-was" in css:
            continue  # idempotent
        extra = []
        # Coarse rule split: selector { declarations }; at-rules are skipped
        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            selector, declarations = match.group(1).strip(), match.group(2).strip()
            if not selector or selector.startswith("@") or not declarations:
                continue
            if not _TABLE_TAG_RE.search(selector):
                continue
            new_selector = ",".join(
                _TABLE_TAG_RE.sub(lambda m: f'[data-was="{m.group(1)}"]', part.strip())
                for part in selector.split(",")
            )
            if new_selector != selector:
                extra.append(f"{new_selector}{{{declarations}}}")
        if extra:
            style.string = (
                css
                + "\n/* --- export: equivalents for retagged table elements --- */\n"
                + "\n".join(extra)
            )
            added += len(extra)
    return added


def _split_line_breaks(soup) -> int:
    """``<br>`` → separate block-level lines.

    The extractor collapses whitespace, so lines separated by ``<br>`` end up glued into
    one run. Splitting them into block DIVs is visually equivalent (a ``<br>`` *is* a line
    break) and each line then emits its own text shape.
    """
    count = 0
    for element in soup.find_all(["div", "p", "td", "th", "li", "span"]):
        if not element.find_all("br", recursive=False):
            continue
        parts, current = [], []
        for child in list(element.contents):
            if getattr(child, "name", None) == "br":
                parts.append(current)
                current = []
                child.extract()
            else:
                current.append(child.extract())
        parts.append(current)
        element.clear()
        for part in parts:
            if not any(str(x).strip() for x in part):
                continue
            line = soup.new_tag("div")
            line["style"] = "display:block"
            line["data-export-line"] = "1"
            for child in part:
                line.append(child)
            element.append(line)
        count += 1
    return count


def _fix_text_dropping_divs(soup) -> int:
    """``<div>bare text + <b>inline</b></div>`` → flatten to plain text.

    Without this the text inside ``<b>`` disappears completely. Only the shape the
    extractor is guaranteed to drop is touched: a DIV holding *both* a bare text node and
    inline children. The cost is that inline bolding inside that one element becomes a
    single weight — much cheaper than losing the sentence. DIVs with only inline children
    and no bare text are left alone (those descend fine and keep their bold).
    """
    count = 0
    for element in soup.find_all("div"):
        children = [c for c in element.children if getattr(c, "name", None)]
        if not children or any(c.name not in _INLINE_TAGS for c in children):
            continue  # has block children → extractor descends, do not touch
        if not any(isinstance(c, NavigableString) and c.strip() for c in element.contents):
            continue  # no bare text → extractor descends into each inline child
        text = element.get_text(" ", strip=True)
        element.clear()
        element.append(NavigableString(text))
        count += 1
    return count


def _materialize_list_markers(soup) -> int:
    """``<ol>`` numbers live in a CSS counter / pseudo element the extractor cannot read,
    so write them into the ``<li>`` as real text. Idempotent."""
    count = 0
    for ordered_list in soup.find_all("ol"):
        for index, item in enumerate(ordered_list.find_all("li", recursive=False), 1):
            if item.find(attrs={"data-export-marker": "1"}):
                continue
            marker = soup.new_tag("span")
            marker["data-export-marker"] = "1"
            marker["style"] = "margin-right:6px"
            marker.string = f"{index}."
            item.insert(0, marker)
            count += 1
    return count


def reshape_for_engine(soup) -> dict[str, int]:
    """Fix every shape the extractor would silently drop. Returns per-step hit counts."""
    return {
        "dense_tables": _reshape_dense_tables(soup),
        "line_breaks": _split_line_breaks(soup),
        "inline_text_rescued": _fix_text_dropping_divs(soup),
        "list_markers": _materialize_list_markers(soup),
    }


# ─────────────────────────────────────────────────────────────────────
# Interactive controls → static text
# ─────────────────────────────────────────────────────────────────────

_CONTROL_STYLE = (
    "display:inline-block;padding:4px 10px;border-radius:6px;background:#eef2f7;"
    "border:1px solid #d6deea;color:#1f2937;font-size:12px;font-weight:700"
)


def _flatten_controls(soup) -> int:
    """Replace segmented filters, tab strips and ``<select>`` with their current value.

    A PPTX has no interactivity; leaving the control markup in place exports every
    inactive option as if it were selected. Only the active choice survives.
    """
    count = 0

    def replace_with_label(node, label: str) -> None:
        nonlocal count
        static = soup.new_tag("span")
        static["class"] = ["export-static-control"]
        static["style"] = _CONTROL_STYLE
        static.string = label
        node.replace_with(static)
        count += 1

    for group in soup.find_all(
        lambda t: _has_class(t, "segmented") or _has_class(t, "tabs") or t.get("role") == "tablist"
    ):
        active = (
            group.find(attrs={"aria-selected": "true"})
            or group.find(class_="active")
            or group.find(["button", "a", "li"])
        )
        replace_with_label(group, active.get_text(strip=True) if active else "")

    for select in soup.find_all("select"):
        chosen = select.find("option", selected=True) or select.find("option")
        replace_with_label(select, chosen.get_text(strip=True) if chosen else "")

    return count


# ─────────────────────────────────────────────────────────────────────
# Browser-side runtime fixes (need computed styles, so they run in the headless Chrome)
# ─────────────────────────────────────────────────────────────────────

# 1. CSS gradients: the extractor captures solid backgrounds only, so a white-on-dark
#    gradient header would vanish entirely. Swap each gradient for a representative
#    solid colour taken from the gradient itself.
# 2. ::before / ::after pseudo elements: coloured dots, badges and glyph icons live
#    outside the DOM and are invisible to the extractor. Materialise them as real spans
#    that copy the pseudo element's own computed box, then suppress the pseudo.
_RUNTIME_SCRIPT = r"""<script data-export-runtime="1">
(function () {
  // The extractor stops descending as soon as an element has direct text of its own, so a
  // freshly injected pseudo element would never be visited. Wrapping the host's bare text
  // in a span removes that direct text and both children get emitted.
  function wrapBareText(el) {
    Array.prototype.slice.call(el.childNodes).forEach(function (node) {
      if (node.nodeType === 3 && node.textContent.trim()) {
        var wrapper = document.createElement("span");
        wrapper.setAttribute("data-export-textwrap", "1");
        wrapper.textContent = node.textContent;
        el.replaceChild(wrapper, node);
      }
    });
  }

  function run() {
    document.querySelectorAll("*").forEach(function (el) {
      var bg = getComputedStyle(el).backgroundImage;
      if (bg && bg.indexOf("gradient") > -1) {
        var stops = bg.match(/#[0-9a-fA-F]{3,8}|rgba?\([^)]+\)/g);
        if (stops && stops.length) {
          el.style.backgroundImage = "none";
          el.style.backgroundColor = stops[Math.floor(stops.length / 2)];
        }
      }
    });
    if (window.__HTML2PPTX_NO_PSEUDO__) return;
    ["::before", "::after"].forEach(function (which) {
      var attr = which === "::before" ? "data-pseudo-materialized" : "data-pseudo-materialized-after";
      document.querySelectorAll("*").forEach(function (el) {
        if (el.hasAttribute(attr)) return;
        if (el.querySelector("[data-export-marker]")) return;   // list numbers already handled
        var cs = getComputedStyle(el, which);
        if (!cs || cs.content === "none" || cs.content === "normal") return;
        var text = "";
        var literal = cs.content.match(/^"(.*)"$/);
        if (literal) text = literal[1];
        var bg = cs.backgroundColor || "";
        var hasFill = bg && bg !== "transparent" && !/rgba\(0, 0, 0, 0\)/.test(bg);
        var w = parseFloat(cs.width) || 0;
        var h = parseFloat(cs.height) || 0;
        if (!text && !(hasFill && w > 0 && h > 0)) return;      // decorative/clearfix: skip
        if (text.length > 12) return;                            // long generated copy: skip
        var span = document.createElement("span");
        span.setAttribute("data-export-pseudo", which === "::before" ? "before" : "after");
        span.textContent = text;
        var s = span.style;
        s.display = "inline-block";
        s.flex = "none";
        s.verticalAlign = cs.verticalAlign || "middle";
        if (w > 0) s.width = w + "px";
        if (h > 0) s.height = h + "px";
        if (hasFill) s.background = bg;
        s.color = cs.color;
        s.font = cs.font || "";
        s.fontSize = cs.fontSize;
        s.fontFamily = cs.fontFamily;
        s.borderRadius = cs.borderRadius;
        s.margin = cs.margin;
        if (cs.position === "absolute" || cs.position === "fixed") {
          s.position = "absolute";
          ["top", "right", "bottom", "left"].forEach(function (side) {
            if (cs[side] && cs[side] !== "auto") s[side] = cs[side];
          });
        }
        if (which === "::before") { el.insertBefore(span, el.firstChild); } else { el.appendChild(span); }
        el.setAttribute(attr, "1");
        wrapBareText(el);   // otherwise the extractor emits the host's own text and never descends
      });
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
</script>"""


def prepare_html(
    html: str,
    *,
    reshape: bool = True,
    canvas: tuple[int, int] = DEFAULT_CANVAS,
    materialize_pseudo: bool = True,
) -> tuple[str, PrepareStats]:
    """Turn source HTML into the conversion-friendly variant. Idempotent.

    Args:
        html: the original document.
        reshape: also fix the shapes the extractor drops (see ``reshape_for_engine``).
        canvas: page size used when paginating a scrolling report.
        materialize_pseudo: turn ``::before`` / ``::after`` decorations into real elements.

    Returns:
        ``(transformed_html, stats)``.
    """
    soup = BeautifulSoup(html, "html.parser")
    stats = PrepareStats()

    if reshape:
        stats.reshape = reshape_for_engine(soup)

    if not _is_slide_shaped(soup):
        stats.shape = "scroll"
        stats.echarts_inlined = _inline_echarts_offline(soup)
        stats.pages_generated = _paginate_scroll(soup, canvas)

    # Tag existing slides for pagination
    for tag in soup.find_all(lambda t: _has_class(t, "slide") or _has_class(t, "cover")):
        classes = tag.get("class", [])
        if "deck-slide" not in classes:
            tag["class"] = classes + ["deck-slide"]
            stats.slides_tagged += 1

    stats.controls_flattened = _flatten_controls(soup)

    # Override stylesheet (idempotent)
    if not soup.find("style", attrs={"data-export-prepare": "1"}):
        head = soup.head
        if head is None:
            head = soup.new_tag("head")
            if soup.html:
                soup.html.insert(0, head)
            else:
                soup.insert(0, head)
        style_tag = soup.new_tag("style")
        style_tag["data-export-prepare"] = "1"
        style_tag.string = _OVERRIDE_CSS
        head.append(style_tag)

    out = str(soup)
    if stats.echarts_inlined:
        # Raw replacement so BeautifulSoup never escapes the minified bundle
        out = out.replace(_ECHARTS_PLACEHOLDER, _ECHARTS_BUNDLE.read_text(encoding="utf-8"))

    if "data-export-runtime" not in out:
        script = _RUNTIME_SCRIPT
        if not materialize_pseudo:
            script = '<script>window.__HTML2PPTX_NO_PSEUDO__=1;</script>' + script
        if "</head>" in out:
            out = out.replace("</head>", script + "</head>", 1)
        elif "</body>" in out:
            out = out.replace("</body>", script + "</body>", 1)
        else:
            out = out + script
    return out, stats
