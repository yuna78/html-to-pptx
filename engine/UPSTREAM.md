# Vendored engine — provenance

This directory is a **vendored fork** of the HTML→editable-PPTX engine from:

- Upstream: `GX-Alex/html2pptx` — https://github.com/GX-Alex/html2pptx
- License: MIT (see `LICENSE` in this directory)
- Pipeline: `html_dom_to_editable_svg.js` (Chromium DOM/CSS/SVG extractor, driven by Node)
  → `svg_to_pptx/` (native DrawingML converter) → `python-pptx` writes the `.pptx`.
- CLI entry point: `html2pptx.py deck.html -o deck.pptx [--canvas auto|WxH] [--chrome <path>]`

## Local changes / 本地改动

Each is marked `[fork patch]` in the source so the fork can be rebased later.

1. **Chart fill fidelity** — `html_dom_to_editable_svg.js`
   `collectSvg()` inlines each SVG element's *computed* paint (fill / stroke / stroke-width
   / `*-opacity` / stop-color) onto the element **before** `<style>` is stripped. Otherwise
   chart colours that come from a CSS class or variable (e.g. `.bar-actual{fill:var(--brand-blue)}`)
   fall back to black once the stylesheet is removed.

2. **Zero-network rendering** — `html_dom_to_editable_svg.js`
   Chrome is launched with `--host-resolver-rules=MAP * ~NOTFOUND`, so no hostname resolves
   during conversion: no SSRF, no cloud-metadata probing, no exfiltration of a local file
   that a malicious deck managed to read. `file://` input and the 127.0.0.1 debugging socket
   are unaffected.

3. **Configurable canvas size** — `html_dom_to_editable_svg.js`, `html2pptx.py`
   The canvas was hard-coded to 1280×720, which made any other deck size fail to convert.
   It is now measured from the first `.deck-slide` before extraction (Chrome is re-sized to
   match) and can be forced with `--canvas WxH`; the PPTX slide size follows the generated
   SVG viewBox.

## Updating from upstream

Re-clone upstream → diff against the `[fork patch]` markers listed above → re-apply each
patch to the new version → run `pytest tests -q` (the smoke tests convert real decks).
