"""Unit tests for the prepare transform (pure Python — no browser needed)."""
from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare import prepare_html  # noqa: E402

SLIDE = """<!doctype html><html><head><style>
td.wide{{width:120px}}
</style></head><body><section class="slide">{body}</section></body></html>"""


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_slide_is_tagged_for_pagination():
    out, stats = prepare_html(SLIDE.format(body="<h1>Title</h1>"))
    assert stats.shape == "slide"
    assert stats.slides_tagged == 1
    assert "deck-slide" in soup_of(out).find("section").get("class")


def test_prepare_is_idempotent():
    once, _ = prepare_html(SLIDE.format(body="<h1>Title</h1>"))
    twice, stats = prepare_html(once)
    assert stats.slides_tagged == 0
    assert twice.count("data-export-runtime") == 1
    assert twice.count("data-export-prepare") == 1


def test_dense_table_is_retagged_and_css_carried():
    body = (
        '<table><tbody><tr><td class="wide"><ul><li>one</li><li>two</li></ul></td>'
        "<td>plain</td></tr></tbody></table>"
    )
    out, stats = prepare_html(SLIDE.format(body=body))
    assert stats.reshape["dense_tables"] == 1
    doc = soup_of(out)
    assert doc.find("table") is None                      # retagged as DIVs
    assert doc.find(attrs={"data-was": "td"}) is not None  # provenance kept
    assert '[data-was="td"].wide' in out                   # column width rule carried over
    assert "one" in out and "two" in out                   # list content survives


def test_sparse_table_is_left_alone():
    body = "<table><tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    out, stats = prepare_html(SLIDE.format(body=body))
    assert stats.reshape["dense_tables"] == 0
    assert soup_of(out).find("table") is not None


def test_line_breaks_become_blocks():
    out, stats = prepare_html(SLIDE.format(body="<div>alpha<br>beta</div>"))
    assert stats.reshape["line_breaks"] == 1
    lines = soup_of(out).find_all(attrs={"data-export-line": "1"})
    assert [line.get_text(strip=True) for line in lines] == ["alpha", "beta"]


def test_inline_text_is_rescued():
    out, stats = prepare_html(SLIDE.format(body="<div>before <b>bold</b> after</div>"))
    assert stats.reshape["inline_text_rescued"] == 1
    assert "bold" in soup_of(out).find("section").get_text()


def test_ordered_list_markers_are_materialized():
    out, stats = prepare_html(SLIDE.format(body="<ol><li>first</li><li>second</li></ol>"))
    assert stats.reshape["list_markers"] == 2
    markers = [m.get_text() for m in soup_of(out).find_all(attrs={"data-export-marker": "1"})]
    assert markers == ["1.", "2."]


def test_controls_are_flattened_to_the_active_value():
    body = (
        '<div class="segmented"><button>Q1</button><button class="active">Q2</button></div>'
        "<select><option>A</option><option selected>B</option></select>"
    )
    out, stats = prepare_html(SLIDE.format(body=body))
    assert stats.controls_flattened == 2
    doc = soup_of(out)
    assert doc.find("select") is None
    assert [c.get_text() for c in doc.find_all(class_="export-static-control")] == ["Q2", "B"]


def test_scrolling_report_is_paginated_without_losing_rows():
    rows = "".join(f"<tr><td>Row {i}</td></tr>" for i in range(1, 41))
    html = (
        "<!doctype html><html><body><div class='container'>"
        "<div class='header'><h1>Report</h1></div>"
        "<div class='chart-row'><div id='c'></div></div>"
        f"<div class='section'><table><thead><tr><th>Item</th></tr></thead><tbody>{rows}</tbody></table></div>"
        "<div class='footer'>end</div>"
        "</div></body></html>"
    )
    out, stats = prepare_html(html)
    assert stats.shape == "scroll"
    assert stats.pages_generated >= 3          # header page + chart page + table pages
    for i in range(1, 41):
        assert f"Row {i}" in out               # pagination never drops a row
    pages = soup_of(out).find_all(class_="deck-slide")
    assert len(pages) == stats.pages_generated


def test_canvas_size_is_applied_to_generated_pages():
    html = (
        "<!doctype html><html><body><div class='container'>"
        "<div class='header'>h</div><div class='section'><p>a</p></div>"
        "<div class='section'><p>b</p></div></div></body></html>"
    )
    out, _ = prepare_html(html, canvas=(1600, 900))
    assert "width:1600px;height:900px" in out


def test_pseudo_materialisation_can_be_disabled():
    out, _ = prepare_html(SLIDE.format(body="<div>x</div>"), materialize_pseudo=False)
    assert "__HTML2PPTX_NO_PSEUDO__" in out
