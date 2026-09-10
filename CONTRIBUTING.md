# 参与贡献 / Contributing

中文说明在下方英文之后。

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

---

## 中文说明

```bash
bash setup.sh                                   # 建 .venv 并做依赖自检
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

`bin/html-to-pptx --doctor` 会告诉你缺什么。

**提 PR 之前**

- **补一个测试**。`tests/test_prepare.py` 覆盖 DOM 变换，不需要浏览器；
  `tests/test_smoke.py` 覆盖端到端转换，没有 Node / Chrome 时自动跳过。
- **变换要保守**。任何变换对「没有这个问题的 HTML」必须是 no-op，而且必须幂等
  ——对自己的输出再跑一次不应有任何变化。这两点测试里都有断言。
- **注释写「为什么」**。这些变换的存在都是因为提取器的某条具体行为；
  点名那条行为的注释，比复述代码的注释有价值得多。
- **报 bug 请带最小复现**：能暴露问题的最小 HTML、你期望在 PowerPoint 里看到什么、实际看到什么。

**改 vendored 引擎**：`engine/` 是 [GX-Alex/html2pptx](https://github.com/GX-Alex/html2pptx) 的 fork。
本地改动请用 `[fork patch]` 注释标记，并登记到 `engine/UPSTREAM.md`，方便日后 rebase 上游。

**范围**：在范围内——转换保真度、依赖与诊断、文档；不在范围内——新做 deck、HTML 模板，
以及任何需要联网服务的东西（离线转换是设计前提）。
