---
name: download
description: 把论文的材料拉到工作区 materials/ 里：git 仓库（可指定 commit）、单个文件（可校验 sha256）、Hugging Face 上的数据集或权重。复现一篇论文时找到了官方代码、数据、权重就用它拉；它只下载、留收据，不判断该拉什么。
compatibility: Python 3.12 以上（脚本自带，与平台 venv 无关）；系统要有 git；hf 子命令要联网到 huggingface.co（私有仓库读环境变量 HF_TOKEN，不收参数）
metadata:
  ai4sci-system-tools: git
---

# download：拉材料

三个子命令，一样的收据。两层 agent 的命令只有 `ai4sci`、自带的网页读取写不了文件，clone 一个仓库、下一份数据都得经它（纲领 P-24）。

## 什么时候用

- 复现一篇论文：材料清单（`sources.md`）里选定了哪个仓库、哪份数据、哪个权重，就一样一样拉下来。
- 研究者给了一个数据文件的链接，要放进 `materials/`。

不是这些情况就别调：它只下载，不搜索、不挑、不解压、不装环境。该拉什么是你和研究者商量的事。

## 怎么运行

```bash
ai4sci skill run download git https://github.com/<org>/<repo> --commit <sha> --out materials/<名字>
ai4sci skill run download file https://<host>/<path>/<文件> --sha256 <hex> --out materials/<名字>
ai4sci skill run download hf <org>/<repo> --type dataset --out materials/<名字>
```

- `--out`：落到哪个目录，写哪里由你定；不给就是 `materials/<仓库名或文件名>`（相对当前目录，也就是工作区）。目录已存在就退 2，不覆盖——换个名字或删掉再拉。
- `git`：`--commit <sha 或 tag>` 拉完切到它（论文说的版本、或 sources.md 里记的）；不给就是默认分支最新。`.git/` 留着，收据记实际的 commit。
- `file`：`--sha256 <hex>` 给了就校验，不对退 4 并删掉；`--name <文件名>` 改落盘的名字（缺省用链接末尾那段）。
- `hf`：`--type dataset|model`（缺省 model），`--revision <分支或 commit>`；私有仓库读环境变量 `HF_TOKEN`，**不收 token 参数**。

stdout 一行 JSON 收据：`{"kind": "git", "source": "…", "commit": "…", "out": "materials/…", "files": 123, "bytes": 4567890, "license": "LICENSE"}`（`file` 是 `sha256` 与 `bytes`，`hf` 是 `commit` 与 `type`）。同一份收据写在 `<out>/.ai4sci-download.json`，之后哪颗能力拿到这个目录都知道它从哪来、是哪个 commit。诊断在 stderr。

退出码：`0` 成；`2` 参数不对、目录已存在、git 不在；`3` 网络或远端的错（clone 失败、404、HF 拒绝）；`4` 校验不过（sha256 对不上、commit 不存在）。

## 拉下来之后

- 代码进了 `materials/<名字>/`，设计阶段的「原码复现基线」用 `--code <名字>` 点名它，框架把它搬进 `code/`。
- 环境：仓库里有 `requirements.txt` 就 `ai4sci env resolve --from materials/<名字>/requirements.txt`（隔离新建）；机器上有现成的就 `ai4sci env use`。
- 把收据里的 commit / sha256 抄进 `sources.md`：复现性分析要写「用的是哪个版本」。

## 常见失败

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 退 2「目录已存在」 | 之前拉过 | 看 `<out>/.ai4sci-download.json` 是不是同一个来源同一个 commit；是就直接用，不是就换名字 |
| 退 3，clone 失败 | 私有仓库、网断了、地址写错 | 私有的让研究者把公钥加到那边或给公开镜像；地址复制原文 |
| 退 4，commit 不存在 | sha 抄错、或在别的分支 | 去仓库页面核对；tag 也行 |
| 退 3，HF 401 / 403 | 门控数据集要同意条款 | 让研究者登录 HF 同意条款，再把 `HF_TOKEN` 放进起服务的环境（不要贴进对话） |
| `uv` 报 offline / 找不到包 | 环境没预热 | 起服务的人跑 `make skills` |
