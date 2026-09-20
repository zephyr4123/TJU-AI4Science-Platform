# 两家后端的实测（2026-09-20）

同一篇论文：Raissi, Perdikaris, Karniadakis, *Physics Informed Deep Learning (Part I)*，arXiv 1711.10561，22 页，580 KB，LaTeX 排版、带文字层。机器：Apple M5 Pro，48 GB，纯 CPU。

| | pymupdf4llm 1.28.2（版面模式） | MinerU 4.0.4 `--tier basic` |
|---|---|---|
| 22 页耗时 | **1.7 s**（含模型加载） | 27.6 s 推理（0.8 页/s）+ 常驻服务启动约 20 s |
| 环境 | 214 MB（uv 脚本环境，12 个包，含 pymupdf-layout 的 ONNX 模型） | 1.2 GB venv（116 个包；Apple Silicon 上 `mineru` 无条件带 `torch` `torchvision` `transformers`）+ 854 MB 模型在 `~/.mineru` |
| 运行形态 | 一个脚本，`uv run --locked --offline`，跑完退出 | 常驻服务：`mineru server start`（UDS socket、SQLite 文档库、解析缓存）+ 解析子进程（`mineru.parser.api_server`，端口 16580）；`parse` 是向服务提交任务 |
| 节标题 | 12 个，带层级与页码 | 12 个（markdown `##`） |
| 表格 | 4 张全对，单元格文本；Table 1 的 N_u=100 / N_f=10000 = 6.7e-04 | 4 张全对，同样的数；表头多一行空行、`N<sub>f</sub> N<sub>u</sub>` 这类残留 |
| 公式 | **不出 LaTeX**，26 处切成 png | **LaTeX**，56 处 `$$ … $$` 带 `\tag{1}`，行内 `$u(t,x)$`；偶有误判（`$B u r g e r s ^ { \prime }$`） |
| 图 | 4 张 png 落盘，文件名与 markdown 引用一致，图注配对 | 12 个块以定位符引用（`doc:…/tier:basic/page:8/block:1`），要拿文件得再逐个 `mineru read … -f image -o` |
| 参考文献 | 24 条，`[n]` 切开 | 24 条 |
| 断词 | 好 | 偶有「ap proximators」这类空格残留 |
| 扫描件 | 不做 OCR（关掉了） | 可 OCR |
| 联网 | 只在 `make skills` 预热 | 首次要 `mineru-kit models download --tier basic`（HuggingFace，4 分 41 秒）；遥测默认开（`MINERU_TELEMETRY=off` 关）；`--pages` 缺省只前 10 页，要 `all` |

**结论（主人 2026-09-20 定）：缺省用 pymupdf4llm，MinerU 是备选，真碰到复杂的再部署。** 两家在「起草需求、核对表里的数」这两个用途上给的数一样；MinerU 多出来的是公式 LaTeX，代价是 15 倍耗时、10 倍体积、一个常驻服务——常驻服务不合 skill 的形状（脚本、`uv run --offline`、跑完退出，纲领 P-22）。什么时候切：复现的课题要抄论文里的公式（PDE、损失函数）时，先用 MinerU 手工出一份 `paper.md` 放进 `materials/`，等第二个这样的课题出现再决定要不要把它包成 `--script mineru` 的第二个脚本。

## 备选：MinerU 部署成服务

MinerU 4.0 自己的形状就是一个服务（`parse_server.local.self_hosted_url` 就是给自建解析服务器用的），真要用它不在本机装，而是：

```
算力服务器（Linux + GPU）            本机 / 工作区
┌──────────────────────────┐        ┌──────────────────────────────┐
│ mineru server（常驻）     │ HTTP   │ 本 skill 的第二个脚本          │
│ tier standard / advanced │◀───────│ --script mineru：传 PDF、收   │
│ 公式 LaTeX、表、图、OCR    │        │ paper.md + JSON，落到 --out   │
└──────────────────────────┘        └──────────────────────────────┘
                                     地址走环境变量 AI4SCI_MINERU_URL（纲领 P-14）
```

触发条件：第一篇「复现要抄论文公式」的论文出现。到那时先在实验室服务器起一个 `mineru server`、加 `--script mineru` 跑通那一篇；GPU 档（OmniDocBench 95.75）确实比 basic（86.47）好、且成了常用路径，再拿数据去申请资源。三样产物的契约不变。

## 复现 MinerU 的实测

```bash
python -m uv venv --python 3.12 mineru-venv && python -m uv pip install --python mineru-venv/bin/python mineru
export MINERU_TELEMETRY=off
mineru-venv/bin/mineru-kit models download --tier basic
mineru-venv/bin/mineru config set parse_server.local.mode managed
mineru-venv/bin/mineru config set parse_server.local.managed_tier basic
mineru-venv/bin/mineru server start            # 等 ~20 s，`mineru server status` 里 parse-server 起来
mineru-venv/bin/mineru parse --tier basic --pages all --wait 800 -o out/paper.md paper.pdf
mineru-venv/bin/mineru server stop
```

坑：`parse` 在服务没起、或 `parse_server.local.mode` 还是 `disabled` 时报 `no_engine`，要先 `config set` 再 `server restart`；`config set` 在模型没下载时会拒绝。
