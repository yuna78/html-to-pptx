---
name: html-to-pptx
description: >-
  把已有的幻灯片式 HTML（报告 / deck / dashboard）转成**真可编辑**的 PowerPoint .pptx——
  每段文字、每个表格单元格、每个色块、每根图表柱子都是 PPT 原生形状（DrawingML），
  可以在 PowerPoint 里直接改字改色，不是把整页截成一张图。用真实无头 Chrome 渲染取布局，
  保真度高。当用户说「把 HTML 转成 PPT」「html 转 ppt」「导出成 pptx」「生成可编辑的
  PowerPoint」「把这个报告 / 幻灯片 / dashboard 做成 PPT」，或 "html to pptx"、
  "convert this HTML to PowerPoint"、"export the deck as an editable ppt" 时使用。
  最适合固定画布、每页一屏的 deck，长滚动报告也能自动分页。
  ❌ 不用于从零新做一套 HTML 幻灯片——本 skill 只转已经存在的 HTML。
tags: [ppt, pptx, html, powerpoint, presentation, export, editable]
license: MIT
---

# html-to-pptx — HTML 转可编辑 PowerPoint

管线：`HTML → 真实浏览器渲染取布局 → 可编辑 SVG 图元 → 原生 DrawingML → .pptx`

完整文档见 [`README.md`](./README.md)（中文）/ [`README.en.md`](./README.en.md)；
引擎内部机制见 [`docs/how-it-works.md`](./docs/how-it-works.md)。本文件是给 agent 看的操作要点。

## 什么时候用

- ✅ 用户已有 HTML 报告 / 幻灯片 / dashboard，想要能继续改的 `.pptx`。
- ✅ 固定画布、每页一屏（任意尺寸：1280×720、1600×900……都行）。
- ✅ 长滚动报告——会自动按语义块分页。
- ❌ 用户想**从零新做**一套幻灯片 → 那是做 deck 的 skill 的活。
- ❌ 用户想要**每页一张 AI 出图**的图片式 PPT → 用图片 deck 类 skill。
- ❌ 输入是 PDF → 用 `pdf-to-pptx` skill。

## 用法

一律走包装脚本，它会自举环境再转换：

```bash
H2P="$HOME/.claude/skills/html-to-pptx/bin/html-to-pptx"

# 默认：产物与来源 HTML 同目录同名
"$H2P" /path/to/report.html

# 指定输出文件或目录
"$H2P" /path/to/report.html -o /path/to/deck.pptx

# 画布尺寸默认实测，可强制指定
"$H2P" /path/to/deck.html --canvas 1600x900

# 逃生口：某个变换帮了倒忙时
"$H2P" deck.html --no-prepare      # 原样交给引擎
"$H2P" deck.html --no-reshape      # 保留 prepare，不做表格/富文本重整
"$H2P" deck.html --no-pseudo       # 不物化 ::before / ::after
"$H2P" deck.html --keep-prepared   # 留下中间 HTML 便于排查
"$H2P" deck.html --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

**产物位置约定**：不带 `-o` 时，`.pptx` 写到**来源 HTML 的同目录、同文件名**。
转完把绝对路径告诉用户，并用 `SendUserFile` 把文件发过去。

## 环境依赖

| 依赖 | 缺了会怎样 |
|---|---|
| **Node.js ≥ 22** | `node: command not found` / 提示没有全局 WebSocket |
| **Google Chrome / Chromium** | 转换失败、找不到 chrome |
| **Python ≥ 3.11**（首次自动建 venv） | `ModuleNotFoundError` |
| **中文字体**（中文 deck） | 中文变方框（macOS 罕见） |

一键自检，缺什么直接给安装命令：

```bash
"$HOME/.claude/skills/html-to-pptx/bin/html-to-pptx" --doctor
```

## 转换替你做的事（都可单独关掉）

1. **切页**——给 `.slide` / `.cover` 打分页标记；滚动报告按块边界切页，超长表格按行拆页
   并重复表头，**一行都不丢**。
2. **画布探测**——实测首页尺寸并同步 PPTX 页面大小。
3. **版式重整**——修三种会丢内容的 HTML 形状：多行表格单元格、`<div>` 里的 `<b>`、`<br>` 换行。
4. **图表离线化**——ECharts 的 CDN 标签换成内置 bundle，零出网也出图。
5. **渐变与伪元素**——CSS 渐变拍平成代表色；`::before` / `::after` 的圆点、角标、字形物化成真形状。
6. **交互控件**——分段筛选、tab、`<select>` 压成当前选中值。

## 排查

| 现象 | 怎么办 |
|---|---|
| `node: command not found` | 装 Node.js ≥ 22（`brew install node`） |
| 找不到 Chrome | 装 Chrome，或 `--chrome <路径>` |
| `ModuleNotFoundError: pptx` | 用 `bin/html-to-pptx`，它会自建 venv |
| 只出了 1 页 | 没识别到分页结构；确认是幻灯片式，或让 prepare 分页（默认开） |
| 多行并成一段 / `<b>` 的字不见了 / 多行黏一行 | 重整被关了（`--no-reshape`），或该表没判为密排 |
| 列宽走形 | 该 deck 用 `<col width>` 定列宽；改成写在单元格上 |
| 图表变黑 | 填色来自被剥离的 CSS 变量——通常已被补丁覆盖，可提 issue |
| 中文变方框 | 装中文字体 |

## 仓库

本 skill 同时是开源仓库 <https://github.com/yuna78/html-to-pptx>（MIT），脱离 Claude 也能当命令行工具用。
改动这里的文件就是改仓库，改完记得 push。
