# 接一个 skill

给要往平台里加一个 skill（agent 的工具包）的人。读完照做，不用问人。验收标准：**换一个人写的 skill，`make skills` 放行、挂到流程实例上之后研究助理与执行层的 `<available_skills>` 清单里出现它、`ai4sci skill run` 跑得起来。** 卡在哪一步，就是这份文档的 bug，请开 issue。

为什么是这套规矩，见外层纲领 P-22（skill）、P-26（按项目装载）、P-27（一个 key 都不要）与 `workflow.md` §1「skill」。这里只讲怎么做。

## skill 是什么、不是什么

skill 是 agent 随时能拿起来用的一套东西：一份说明（什么时候用、怎么运行、留下哪几个文件、常见失败）加几个脚本与参考。研究助理与执行层的会话都能用，装的是同一套：平台自带的常驻，加本项目各工作区流程实例上挂的（P-26）。流程助理不跑东西，不给清单。

能力一个词、两种 tag（纲领 P-22，`framework/capabilities/abilities.py` 是出处）：

| | 步骤 | skill |
|---|---|---|
| 是什么 | 描述符 + `run`，框架开产出目录、起执行层 | 说明 + 脚本，agent 的工具 |
| 谁调 | 研究助理，`ai4sci cap <name>` | 研究助理或执行层，`ai4sci skill run <name>` |
| 写到哪 | 自己的 `<stage>/<n>/` | 调用方 `--out` 给的地方（助理带 `--ws` 落在那个工作区） |
| 挂到流程格子上 | 得属于那个阶段，参数按描述符核对 | 哪个阶段都能挂、不带参数；挂了才装载（平台自带的常驻） |
| 怎么进 prompt | 描述符五栏（`ai4sci show caps`） | `<available_skills>` 清单里一行，全文按需 `show` |

要产出目录、要被下游 `--from` 的做成步骤（`add-a-capability.md`）；只是读个文件、拉个仓库、教 agent 一套做法的做 skill 就够。

## 三处库

```
skills/<name>/                         平台自带：常驻，项目里的会话一直装载（现在是 pdf、download）
skills-curated/<架>/<name>/            收录的社区 skill：架是七个阶段的 slug（literature、hypothesis、design、
                                       experiment、analysis、writing、verification）或 general（通用：画图、
                                       格式转换这类）；挂到流程实例上才装载
skills-curated/provenance.yaml         收录台账：一个 skill 一行，来源、提交、许可证、改了什么；不收的也记
skills-curated/licenses/<上游>.txt      上游许可证原文
domains/<包>/skills/<name>/            领域包自带的：挂到流程实例上才装载（docs/add-a-domain.md）
```

名字 = 目录名，小写字母数字连字符；三处库合起来全局唯一。平台自己写的、每个项目都要的放 `skills/`；从开源整合包拿进来的放 `skills-curated/`（见下面「收录社区 skill」）；只给某个工具链用的放领域包。

一个 skill 的目录：

```
<name>/
├── SKILL.md                       必有：frontmatter + 正文
├── scripts/                       可选：`ai4sci skill run` 能起的工具，每个自带依赖声明与锁文件
│   ├── extract.py
│   └── extract.py.lock
├── references/                    可选：agent 按需读的长文档、示例代码
└── assets/                        可选：模板、样例
```

## SKILL.md

frontmatter 照 [agentskills.io](https://agentskills.io) 规范的字段写；规范外的字段（各家 agent 的 `allowed-tools`、`version`、`tags`……）不拦，只在 `make skills` 记一条提醒、不读：

```yaml
---
name: pdf                                   # 必填，等于目录名
description: 一句话：做什么、什么时候用。清单里只显示它，agent 靠它决定要不要读全文
compatibility: Python 3.12 以上；纯 CPU        # 可选：运行时要求，人读的
metadata:                                   # 可选：字符串到字符串；我们自己的键加 ai4sci- 前缀
  ai4sci-system-tools: pdftoppm tesseract   # uv 装不了的系统命令，make skills 会逐个 which
---
```

正文建议五百行以内，细节进 `references/`。写四件事：什么时候用（也写什么时候**别**用）、命令怎么敲（照 `ai4sci skill run <name> …` 的写法，agent 会原样抄）、留下哪几个文件（文件名与形状，文档即接口）、常见失败怎么办。有脚本的 skill，正文里必须出现 `ai4sci skill run`（测试守着）。目录里正文以外的文件，agent 用 `ai4sci skill show <name> <文件>` 读（执行层的读文件工具只放行工作目录），正文里提到它们时写相对路径就行。

拦下来、不装载的只有这几种（隔离出去带原因，不拖垮别的 skill；出厂的三处库在门禁里一个都不许有）：没有 `SKILL.md`、frontmatter 坏、缺 `name` / `description`、`name` 与目录名对不上、description 超过 1024 字、脚本没有 PEP 723 头或锁文件。

**零 key（P-27）**：skill 里不许出现第三方凭据——模型、检索、数据源、出图的 key 都不要，可选的也不要。门禁逐个文件查「api key」「access token」这类说法与 `*_TOKEN` `*_API_KEY` 这类环境变量名，查到就不过。

## 脚本

- `scripts/` 里只放 `ai4sci skill run` 起得来的 Python 工具；示例代码、别的语言的脚本放 `references/`。
- 非交互、有 `--help`；结果 JSON 一行到 stdout，诊断到 stderr；幂等；退出码 0 成、非 0 败且 stderr 说清。
- 输入用参数点名，输出目录由调用方 `--out` 给（本地文件不给就写在它旁边的同名目录）；不猜路径、不写别处。
- 依赖用 PEP 723 内联元数据，**不手写**：

  ```bash
  .venv/bin/python -m uv add --script skills/<name>/scripts/<x>.py <包>
  .venv/bin/python -m uv lock --script skills/<name>/scripts/<x>.py      # 出 <x>.py.lock，进仓
  ```

  只用标准库的脚本也要有头（`dependencies = []`）与锁。`requires-python` 由脚本自己定，与框架的 Python（≥ 3.12）、课题的 venv 都无关。
- 运行一律 `uv run --locked`（`ai4sci skill run` 就是这么起的）：环境在 uv 的全机缓存里，所有工作区共享一份；锁对不上就报错。**不建工作区级 venv。** 平台自带的由 `make skills` 预热；收录的与领域包的几百个不全量预热，第一次运行时按锁建环境（要联网一次，`ai4sci` 的命令在两家适配器里都在沙箱外跑）。
- 一个 skill 一个脚本时 `ai4sci skill run <name> …` 直接起它；几个脚本时调用方要 `--script <文件名>` 点名，SKILL.md 里写清。
- 脚本要过仓库的 ruff（`make lint` 扫 `skills/`；收录的保持上游原样，不扫）。

## 承接与门禁

- `make skills`：扫三处库，一个不合格都不行；零 key；收录台账与目录对账；平台自带的每个脚本 `uv lock --check` + `uv sync`（预热）并探测 `ai4sci-system-tools`。它在 `make check` 里，CI 也跑。
- `tests/test_skills.py`：出厂的三处库逐条过门禁；格式规则、宽进与隔离、零 key、台账用假 skill 验。`tests/test_workspace_loadout.py`：按项目装载。
- 起会话时框架拼 `<available_skills>`：研究助理每轮按项目现算（`framework/chat/guide.py`），执行层按产出目录所在的项目算（`framework/executor/prompting.py`），都从 `framework/workspace/loadout.py` 一处取。不靠任何 agent 的原生 skill 加载。

## 一步一步（自己写一个）

1. `mkdir skills/<name>`（平台自带）或 `domains/<包>/skills/<name>`，写 `SKILL.md`（上面的四件事）。
2. 要脚本就写 `scripts/<x>.py`，`uv add --script` 加依赖、`uv lock --script` 出锁。
3. `make skills` 过门禁。
4. 挂到一个工作区的流程实例上（`- 文献: [<name>]`），`ai4sci skill show <name>`、`ai4sci skill run <name> --help` 看一眼 agent 会看到什么。
5. `make check`。
6. CHANGELOG 的 Unreleased 加一行，commit message 引外层 issue。

## 收录社区 skill

社区的 skill 整合包（几十上百个一包）拿进来，按阶段分拣进 `skills-curated/<架>/`，一个 skill 一个目录、台账一行。原则是**照原样收、只改平台跑不了的地方、改了什么记下来**：上游更新时照台账重做一遍。

### 先判收不收

逐个 skill 看它的 `SKILL.md`、脚本、参考，一条不过就不收（台账 `rejected` 记一行原因）：

1. **许可证**能随开源平台再分发、不加使用限制：MIT、Apache-2.0、BSD、ISC。看整个仓库的许可证，也看 skill 目录里有没有自己的（有的包里个别 skill 是专有条款或非商用）。NC、专有、没有许可证的不收。
2. **零 key**：默认的用法就要 key（模型 API、付费检索、需要账号的服务）的不收；key 只是可选的，删掉那几句与对应的代码再收。
3. **能在平台里用**：两层 agent 面前只有 `ai4sci` 的命令与自带的联网搜索、网页读取，执行层还只有 `ai4sci skill`。核心做法离不开 MCP 服务、子代理、交互式的人回合、本机 GUI、Docker、装系统软件的不收；只是个别步骤这样的，删掉那几步再收。教 agent 写实验代码时怎么用某个库的（知识型），照收：代码片段是给执行层抄进实验代码的，不是让它在命令行里跑。

### 收进来要改的

- **目录**：拷到 `skills-curated/<架>/<name>/`。架按这个 skill 主要用在哪个研究阶段定：检索、读论文、综述、引用 → `literature`；出想法、查新、提假设 → `hypothesis`；实验设计、统计功效、评分 → `design`；写实验代码时用的领域库与框架 → `experiment`；统计分析、结果解读 → `analysis`；论文与基金写作、润色、排版、审稿回复 → `writing`；复现核对、事实核查 → `verification`；画图、格式转换、文档转换这类哪个阶段都用的 → `general`。
- **名字**：保留上游的名字；和平台自带的（`pdf` `download`）、领域包的（`petab`）、别的收录的重了，在后面加上游的短名（`-kdense`、`-nature`、`-airs`），台账记一笔。
- **`scripts/`**：只留 `ai4sci skill run` 起得来的 Python 工具，每个补 PEP 723 头（照它的 import 写依赖）与锁；示例、别的语言的脚本挪到 `references/`。正文里 `python scripts/x.py …` 这类起法改成 `ai4sci skill run <name> --script x.py …`，提到挪走的文件的地方跟着改路径。
- **删**：key 相关的段落与代码；让 agent 推广上游、往稿子里加某篇论文引用、上报使用情况、检查更新的段落；超过 1 MB 的文件、图片与二进制、没有授权的素材。
- **不改**：其余的正文、frontmatter 里规范外的字段（宽进，只提醒）。

### 台账

`skills-curated/provenance.yaml` 的形状在 `framework/skills/provenance.py` 文件头。收的一行：`name`、`shelf`、`upstream`、`path`（上游原路径）、`changes`（改了什么，一条一句）；不收的一行：`upstream`、`path`、`reason`。上游的提交号、许可证与原文在 `upstreams` 里。`make skills` 对账：目录与台账一一对得上、许可证在可收的里、原文在。

### 现在收了哪些

见 `skills-curated/provenance.yaml`。按架数：`ai4sci show skills --stage <阶段>`。

## 现在平台自带与领域包里的

| skill | 库 | 做什么 |
|---|---|---|
| `pdf` | 平台 | 论文 PDF → `paper.md` + `images/` + `structured.json`；后端 pymupdf4llm 版面模式，两家后端的实测在 `skills/pdf/references/backends.md` |
| `download` | 平台 | 把材料拉到工作区 `materials/`：git 仓库（可指定 commit）、单个文件（可校验 sha256）、Hugging Face 上公开的仓库；留收据 |
| `petab` | `domains/petab` | PEtab 参数估计工具链的 API 约定，只有说明没有脚本 |
