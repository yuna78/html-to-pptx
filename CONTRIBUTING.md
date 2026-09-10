# Contributing

Thanks for helping out. This project is small on purpose — a CLI, one transform module,
and a vendored rendering engine.

## Getting set up

```bash
bash setup.sh                                   # creates .venv and checks prerequisites
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

`bin/html-to-pptx --doctor` tells you what is missing if the engine cannot run.

## Before you open a pull request

- **Add a test.** `tests/test_prepare.py` covers DOM transforms and needs no browser;
  `tests/test_smoke.py` covers end-to-end conversion and is skipped without Node/Chrome.
- **Keep transforms conservative.** Every transform must be a no-op for HTML that does not
  exhibit the problem it fixes, and must be idempotent — running `prepare_html` on its own
  output must not change it further. Both properties are asserted by the tests.
- **Explain the "why" in the code.** The transforms exist because of specific extractor
  behaviour; a comment that names the behaviour is worth more than one that restates the code.
- **Include a minimal reproducer** for bug reports: the smallest HTML that shows the problem,
  what you expected in PowerPoint, and what you got.

## Changing the vendored engine

`engine/` is a fork of [GX-Alex/html2pptx](https://github.com/GX-Alex/html2pptx). Mark any
local change with a `[fork patch]` comment and add it to the list in `engine/UPSTREAM.md`,
so the fork can be rebased onto a newer upstream later.

## Scope

In scope: fidelity of the HTML → editable-shape conversion, prerequisites and diagnostics,
documentation.

Out of scope: authoring new decks, HTML templating, and anything that requires a network
service — conversion runs entirely offline by design.
