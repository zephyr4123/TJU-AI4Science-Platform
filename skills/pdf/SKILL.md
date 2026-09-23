---
name: pdf
description: 把一篇论文 PDF（本地文件或链接）解析成 paper.md 正文、images/ 图与公式、structured.json（分节、表格、图注、参考文献、题目作者年份 DOI）。研究者给了论文要起草需求、要核对论文里的数、文献阶段要读论文细节时用。纯 CPU，一篇二十页的论文两秒。
compatibility: Python 3.12 以上（脚本自带，与平台 venv 无关）；纯 CPU，无 GPU；不做 OCR，扫描件解析不出文字
metadata:
  ai4sci-backend: pymupdf4llm 1.28 版面模式（pymupdf-layout，ONNX 小模型）
---

# pdf：解析论文

一篇 PDF 进，三样东西出。后端可换，这三样的形状不变（文档即接口）。

## 什么时候用

- 研究者给了一篇论文（文件放在 `materials/`，或者只给了链接）——先解析，再照 `paper.md` 起草需求。
- 需求或分析里要引用论文报的数——从 `structured.json` 的 `tables` 里抄，不凭记忆写。
- 执行层会话要读论文——同一条命令，`--out` 指向自己的产出目录。

不是这些情况就别调：它只解析，不总结、不判断。

## 怎么运行

```bash
ai4sci skill run pdf --input materials/<论文>.pdf --out materials/<论文>/ --ws <工作区>
ai4sci skill run pdf --input https://arxiv.org/pdf/<id> --out materials/<论文>/ --ws <工作区>
```

- `--input`：本地路径或 http(s) 链接。链接时原件会存成 `--out/source.pdf`（原件也是材料，留一份）。
- `--out`：产物目录，写哪里由你定；本地文件不给 `--out` 就写在它旁边的同名目录。链接必须给。
- 幂等：重跑覆盖同名文件，`images/` 先清空。

stdout 一行 JSON：`{"out": …, "pages": 22, "sections": 12, "tables": 4, "figures": 4, "formulas": 26,
"references": 24, "files": ["paper.md", "structured.json", "images/"]}`。诊断在 stderr。

退出码：`0` 成；`2` 输入文件不在（或链接没给 `--out`）；`3` 下载失败、链接返回的不是 PDF；
`4` 文件不是能打开的 PDF。

## 留下哪几个文件

| 文件 | 内容 |
|---|---|
| `paper.md` | 正文 markdown：标题层级、段落、列表、表格（单元格文本）、图与公式的引用（指向 `images/`）、脚注、参考文献原文。页眉页脚去掉 |
| `images/` | 图（`picture`）与公式（`formula`）切出来的 png，文件名与 `paper.md` 里的引用一致 |
| `structured.json` | 给机器读的：`metadata`（题目、作者行、年份、DOI、arXiv 号、PDF 自带元数据）、`sections`（层级、标题、页码）、`tables`（页码、图注、表头、每行单元格、markdown）、`figures`（页码、文件、图注）、`formulas`（页码、文件）、`references`（一条一段原文）、`links`（PDF 里的链接，代码仓地址多半在这）、`source`（文件名、sha256、页数、链接）、`backend` |

字段细节与一份真实样例在 `references/structured.md`。

## 后端与它的边界

现在是 pymupdf4llm 的版面模式（`references/backends.md` 有两家后端的实测对比与切换记录）：

- 公式**不出 LaTeX**，切成图片放 `images/`；要公式原文得看图。
- 表格取的是单元格文本；跨页表、无线框的表可能拆错或漏，用之前对着 `tables[].markdown` 核一眼。
- 图注按同页「Table …」「Figure …」配对；一页里对象与图注数目不等时按最近的配，可能配错。
- 不做 OCR：扫描件（没有文字层）解析出来是空的，`pages` 有数但 `sections` 为 0——那就是扫描件，告诉研究者换一份带文字层的。
- 参考文献按「References」节之后的条目切，编号 `[n]` 开头的切得准；作者年份式（无编号）的可能几条粘成一条。

## 常见失败

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `uv` 报 offline / 找不到包 | 环境没预热 | 起服务的人跑 `make skills`（唯一联网的一步） |
| 退出码 3，「链接返回的不是 PDF」 | 给的是论文页面不是 PDF 直链 | arXiv 用 `https://arxiv.org/pdf/<id>`；期刊页面多半要登录，让研究者把文件放进 `materials/` |
| `sections` 为 0、`paper.md` 几乎空 | 扫描件 | 换带文字层的版本 |
| 表格数字对不上原文 | 版面切错 | 看 `paper.md` 里那张表的 markdown，或让研究者核对那一页 |
