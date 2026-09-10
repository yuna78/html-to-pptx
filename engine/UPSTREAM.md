# Vendored engine — provenance

This directory is a **vendored fork** of the HTML→editable-PPTX engine from:

- Upstream: `GX-Alex/html2pptx` — https://github.com/GX-Alex/html2pptx
- License: MIT (see `LICENSE` in this directory)
- Pipeline: `html_dom_to_editable_svg.js` (Chromium DOM/CSS/SVG extractor, driven by Node)
  → `svg_to_pptx/` (native DrawingML converter) → `python-pptx` writes the `.pptx`.
- CLI entry point: `html2pptx.py deck.html -o deck.pptx [--canvas auto|WxH] [--chrome <path>]`
- Upstream at the time of writing: `1887e4b` (2026-06-08). The exact fork point is not
  recorded; diff against the `[fork patch]` markers below when rebasing.

**The hard part is upstream's.** Walking a rendered DOM and rebuilding it as native
DrawingML — the reason the output is editable at all — is `GX-Alex/html2pptx`'s design and
code. Everything listed below is repair and packaging work on top of it.

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

4. **Text is never re-spaced** — `html_dom_to_editable_svg.js`
   `wrapText()` used to re-tokenise a string and re-join it with a spacing heuristic,
   which inserted spaces that were not in the source (`18,420` → `18, 420`, `−3.2%` →
   `− 3.2%`). The slide still looked right, but the text could no longer be found by
   search. Wrapping now works on atoms that carry the original whitespace, so a line
   break can only replace existing whitespace or fall between CJK characters.

5. **Chrome start-up is diagnosable and self-healing** — `html_dom_to_editable_svg.js`
   Chrome was spawned with `stdio: "ignore"`, so a browser that refused to start produced
   only "Timed out waiting for Chrome remote debugging" with no reason. Its stderr is now
   captured and echoed, an early exit stops the wait immediately, and the launch is retried
   once with `--no-sandbox` — the failure mode on Ubuntu 24.04+, containers and CI runners.

6. **Node version is checked up front** — `html_dom_to_editable_svg.js`
   The CDP client uses the global `WebSocket`, which Node only exposes from v22. On older
   Node this surfaced as a `ReferenceError` mid-run; it now fails immediately with the
   version it found and how to upgrade.

## Not from upstream at all

`prepare.py` (pre-conversion DOM transforms), `convert.py` (CLI with preflight checks),
`bin/html-to-pptx`, `tests/`, `examples/` and the docs are this project's own work. The
vendored engine is only invoked at the end of that pipeline.

## Updating from upstream

Re-clone upstream → diff against the `[fork patch]` markers listed above → re-apply each
patch to the new version → run `pytest tests -q` (the smoke tests convert real decks).
