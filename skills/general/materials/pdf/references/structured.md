# structured.json 的字段

给机器读的那份。页码从 1 起；空值写 `null` 不写空串；文件路径相对产物目录。样例来自 Raissi et al. 2017（arXiv 1711.10561，PINNs Part I）。

```json
{
  "source": {"file": "pinns-part1.pdf", "sha256": "2a8db677…", "pages": 22, "url": null},
  "backend": {"name": "pymupdf4llm", "version": "1.28.2", "mode": "layout", "formulas": "image"},
  "metadata": {
    "title": "Physics Informed Deep Learning (Part I): Data-driven Solutions of Nonlinear Partial Differential Equations",
    "authors_line": "Maziar Raissi 1 , Paris Perdikaris 2 , and George Em Karniadakis 1",
    "year": 2017,
    "doi": null,
    "arxiv": null,
    "pdf_metadata": {"format": "PDF 1.5", "creator": "LaTeX with hyperref package", "creationDate": "D:20171130012707Z"}
  },
  "sections": [
    {"level": 2, "title": "Abstract", "page": 1},
    {"level": 2, "title": "1. Introduction", "page": 1},
    {"level": 2, "title": "2.1. Example (Burgers’ Equation)", "page": 4}
  ],
  "tables": [
    {
      "page": 9,
      "caption": "Table 1: Burgers’ equation: Relative L 2 error … 9 layers with 20 neurons per hidden layer.",
      "header": ["Nu Nf", "2000", "4000", "6000", "7000", "8000", "10000"],
      "rows": [["20", "2.9e-01", "4.4e-01", "8.9e-01", "1.2e+00", "9.9e-02", "4.2e-02"],
               ["100", "6.6e-02", "2.7e-01", "7.2e-03", "6.8e-04", "2.2e-03", "6.7e-04"]],
      "markdown": "|_Nu_<br>_Nf_|2000|4000|…"
    }
  ],
  "figures": [
    {"page": 8, "file": "images/pinns-part1.pdf-0008-00.png", "caption": "Figure 1: Burgers’ equation: Top: Predicted solution u ( t, x ) …"}
  ],
  "formulas": [{"page": 4, "file": "images/pinns-part1.pdf-0004-02.png"}],
  "references": ["[1] A. Krizhevsky, I. Sutskever, G. E. Hinton, Imagenet classification with deep convolutional neural networks, in: Advances in neural information processing systems, pp. 1097–1105."],
  "links": ["https://github.com/maziarraissi/PINNs"]
}
```

| 字段 | 含义 | 怎么来的 |
|---|---|---|
| `source.file` `sha256` `pages` `url` | 原件名、内容哈希、页数、来源链接（本地文件为 `null`） | 哈希算的是解析的那个文件 |
| `backend` | 后端名、版本、模式；`formulas` 说公式是 `image` 还是 `latex` | 换后端只改这一块 |
| `metadata.title` | 题目 | 版面里的 `title` 框；没有就用 PDF 元数据里的 |
| `metadata.authors_line` | 作者行原文 | 题目后第一段文字，不拆人名（拆错比不拆糟） |
| `metadata.year` | 年份 | PDF 元数据的日期；没有就在首页文字里找一个年份 |
| `metadata.doi` `arxiv` | DOI、arXiv 号 | 首页文字与来源链接里正则找；arXiv 侧栏是竖排的，版面模式读不到，所以本地文件的 arXiv 号多半是 `null`，链接下载的有 |
| `metadata.pdf_metadata` | PDF 自带的元数据 | 只留非空项 |
| `sections[]` | 层级、标题、页码 | 版面里的 `section-header` 框；`level` 是后端估的（本样例全是 2） |
| `tables[]` | 页码、图注、表头（第一行）、其余行、后端出的 markdown | 单元格文本；`caption` 按同页「Table …」配对，配不上是 `null` |
| `figures[]` | 页码、文件、图注 | `picture` 框；`caption` 按同页「Figure …」配对 |
| `formulas[]` | 页码、文件 | `formula` 框切成图；没有 LaTeX |
| `references[]` | 一条一段原文 | 「References」节之后的条目；`[n]` 开头的按编号切 |
| `links[]` | PDF 里的超链接，去重 | 代码仓、数据集地址多半在这 |

不要拿 `metadata.year` 当发表年份：预印本的 PDF 日期是上传日期。要引用就看 `references` 或 DOI。
