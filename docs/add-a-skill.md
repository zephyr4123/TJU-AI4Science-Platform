# 接一个 skill

给要往平台里加一个 skill（agent 的工具包）的人。读完照做，不用问人。验收标准：**换一个人写的 skill，`make skills` 放行、研究助理与执行层的 `<available_skills>` 清单里出现它、`ai4sci skill run` 跑得起来。** 卡在哪一步，就是这份文档的 bug，请开 issue。

为什么是这套规矩，见外层纲领 P-22（`docs/architecture/README.md`）与 `workflow.md` §1「skill」。这里只讲怎么做。

## skill 是什么、不是什么

skill 是 agent 随时能拿起来用的一套东西：一份说明（什么时候用、怎么运行、留下哪几个文件、常见失败）加几个脚本。研究助理与执行层的会话都能用（流程助理不跑东西，不给清单）。

能力一个词、两种 tag（纲领 P-22，`framework/capabilities/abilities.py` 是出处）：

| | 步骤 | skill |
|---|---|---|
| 是什么 | 描述符 + `run`，框架开产出目录、起执行层 | 说明 + 脚本，agent 的工具 |
| 谁调 | 研究助理，`ai4sci cap <name>` | 研究助理或执行层，`ai4sci skill run <name>`，随时 |
| 写到哪 | 自己的 `<stage>/<n>/` | 调用方 `--out` 给的地方（助理带 `--ws` 落在那个工作区） |
| 挂到流程格子上 | 得属于那个阶段，参数按描述符核对 | 哪个阶段都能挂、不带参数，意思是「这一步推荐用它」 |
| 怎么进 prompt | 描述符五栏（`ai4sci show caps`） | `<available_skills>` 清单里一行，全文按需 `show` |

要产出目录、要被下游 `--from` 的做成步骤（`add-a-capability.md`）；只是读个文件、拉个仓库的做 skill 就够。

## 目录

```
skills/<name>/                     平台通用的，放这里；只给某个领域用的放 domains/<包>/skills/<name>/
├── SKILL.md                       必有：frontmatter + 正文
├── scripts/                       可选：可执行脚本，每个自带依赖声明与锁文件
│   ├── extract.py
│   └── extract.py.lock
├── references/                    可选：agent 按需读的长文档
└── assets/                        可选：模板、样例
```

名字 = 目录名，小写字母数字连字符；两处库合起来全局唯一（重名起会话就报错）。

## SKILL.md

frontmatter 只用 [agentskills.io](https://agentskills.io) 规范的字段，不用任何一家 agent 的专有字段：

```yaml
---
name: pdf                                   # 必填，等于目录名
description: 一句话：做什么、什么时候用。清单里只显示它，agent 靠它决定要不要读全文
compatibility: Python 3.12 以上；纯 CPU        # 可选：运行时要求，人读的
metadata:                                   # 可选：字符串到字符串；我们自己的键加 ai4sci- 前缀
  ai4sci-system-tools: pdftoppm tesseract   # uv 装不了的系统命令，make skills 会逐个 which
---
```

正文五百行以内，细节进 `references/`。写四件事：什么时候用（也写什么时候**别**用）、命令怎么敲（照 `ai4sci skill run <name> …` 的写法，agent 会原样抄）、留下哪几个文件（文件名与形状，文档即接口）、常见失败怎么办。有脚本的 skill，正文里必须出现 `ai4sci skill run`（测试守着）。

## 脚本

- 非交互、有 `--help`；结果 JSON 一行到 stdout，诊断到 stderr；幂等；退出码 0 成、非 0 败且 stderr 说清。
- 输入用参数点名，输出目录由调用方 `--out` 给（本地文件不给就写在它旁边的同名目录）；不猜路径、不写别处。
- 依赖用 PEP 723 内联元数据，**不手写**：

  ```bash
  .venv/bin/python -m uv add --script skills/<name>/scripts/<x>.py <包>
  .venv/bin/python -m uv lock --script skills/<name>/scripts/<x>.py      # 出 <x>.py.lock，进仓
  ```

  `requires-python` 由脚本自己定，与框架的 Python（≥ 3.12）、课题的 venv 都无关。
- 运行一律 `uv run --locked --offline`（`ai4sci skill run` 就是这么起的）：环境在 uv 的全机缓存里，所有工作区共享一份；锁对不上就报错。**不建工作区级 venv。**
- 一个 skill 一个脚本时 `ai4sci skill run <name> …` 直接起它；几个脚本时调用方要 `--script <文件名>` 点名，SKILL.md 里写清。
- 脚本要过仓库的 ruff（`make lint` 扫 `skills/`）。

## 承接与门禁

- `make skills`：扫两处库、校验、每个脚本 `uv lock --check` + `uv sync`（预热，唯一联网的一步）、探测 `ai4sci-system-tools`。它在 `make check` 里，CI 也跑。
- `tests/test_skills.py`：出厂的库逐条过门禁；格式规则用假 skill 验。
- 起会话时框架扫库拼 `<available_skills>`：协调层拿通用库（`framework/chat/guide.py`），执行层拿通用 + 所选领域包的（`framework/executor/prompting.py`）。不靠任何 agent 的原生 skill 加载。

## 一步一步

1. `mkdir skills/<name>`，写 `SKILL.md`（上面的四件事）。
2. 要脚本就写 `scripts/<x>.py`，`uv add --script` 加依赖、`uv lock --script` 出锁。
3. `make skills` 过门禁并预热。
4. `ai4sci skill show <name>`、`ai4sci skill run <name> --help` 看一眼 agent 会看到什么。
5. `make check`。
6. CHANGELOG 的 Unreleased 加一行，commit message 引外层 issue。

## 现在有的

| skill | 库 | 做什么 |
|---|---|---|
| `pdf` | 通用 | 论文 PDF → `paper.md` + `images/` + `structured.json`；后端 pymupdf4llm 版面模式，两家后端的实测在 `skills/pdf/references/backends.md` |
| `download` | 通用 | 把材料拉到工作区 `materials/`：git 仓库（可指定 commit）、单个文件（可校验 sha256）、Hugging Face 仓库；留收据 |
| `petab` | `domains/petab` | PEtab 参数估计工具链的 API 约定，只有说明没有脚本 |
