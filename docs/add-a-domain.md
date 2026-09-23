# 接一个领域包

给要往平台里加一个领域包的人。读完照做，不用问人。验收标准：**新建一个目录、放一份 `profile.yaml`，`cap design --domain <id>` 认它、执行层的 skill 清单里出现它的 skill。** 卡在哪一步，就是这份文档的 bug，请开 issue。

为什么是这套规矩，见外层纲领 P-5、P-11、P-18、P-22（`docs/architecture/README.md`）。这里只讲怎么做。

## 领域包是什么、不是什么

流程通用，课题不通用。适配的形态是**写文件，不是改代码**：一个领域一个目录，框架按目录发现，没有注册表。领域包只是打包单位（纲领 P-18）：拆开各归各的能力——`prompts/` 归实验族的提示，`skills/` 归执行层的工具包。

按**工具链或任务类型**命名（`petab`、`ml`），不按学科：平台看到的是「九个参数最小化一个标量」这种形状，学科在需求文档里。

## 目录

```
domains/<id>/
├── profile.yaml            必有：id 与 display_name
├── prompts/experiment.md   可选：实验族的领域约定，随执行层提示的「领域约定」段注入
└── skills/<name>/          可选：领域 skill，格式同 skills/（docs/add-a-skill.md）
```

出厂两个：`generic/` 兜底（任何课题都能用）、`petab/` 参数估计（pyPESTO + petab + libroadrunner）。库的位置 `AI4SCI_DOMAINS_ROOT` 可指定（读取点只在 `framework/paths.py`）；装的包里在 `framework/shipped/domains/`。

## profile.yaml

只收有读取点的字段：

```yaml
id: petab                    # 等于目录名
display_name: PEtab 参数估计   # 给人看的名字
```

读取点在 `framework/experiment/pack.py::_check_domain`：`scoring.yaml` 的 `domain` 指向哪个领域，那个目录下就必须有 `profile.yaml`；`scoring.yaml` 不写 `domain` 落到 `generic`。除此之外框架不读它的任何字段——想加字段，先写读取点（纲领 P-8）。

## prompts/experiment.md

实验族的领域约定：这一族的执行层会话（`design`、`reproduction` 写草稿，`auto-research` 逐轮改代码）该知道的领域常识——库的 API 怎么调、哪些不能用、结果怎么读。`cap auto-research` 开实验时把它快照进产出目录（`experiment/<n>/prompts/experiment-domain.md`，`auto_research/open.py::_snapshot_domain`），之后不回头看领域包；设计阶段的两个能力直接读库里的。没有这个文件就不追加，也不回退到别的领域的（AutoResearchClaw 让 26 个领域静默用 ML 提示词，是反例）。

一个族一个文件，文件名是族名；现在只有实验族。

## skills/

领域 skill 与平台通用的 `skills/` 同一种格式（agentskills.io：`SKILL.md` + `scripts/` + `references/`，脚本 PEP 723 自带依赖并锁进仓），接法见 `docs/add-a-skill.md`。两处库合起来名字唯一。

只进**执行层**的清单：起执行层会话时框架把所选领域包的 skill 与通用 skill 一起拼成 `<available_skills>`（`framework/skills/library.py::for_executor`），执行层 `ai4sci skill show / run` 读与跑；研究助理只拿通用的（纲领 P-11 两层 skill 物理隔离）。不快照、不注入正文：清单里只有名字与一句话，执行层读的是库里的现版本，读了什么在那一轮的事件流里。

## 一步一步

1. `mkdir domains/<id>`，写 `profile.yaml`。
2. 要领域约定就写 `prompts/experiment.md`；要 skill 就照 `add-a-skill.md` 放进 `skills/<name>/`。
3. `make skills`（领域 skill 也过门禁）、`make check`。
4. 在一份需求里用：`scoring.yaml` 写 `domain: <id>`（设计阶段 `cap design --domain <id>` 会写进去）。
5. CHANGELOG 的 Unreleased 加一行，commit message 引外层 issue。

不改 `framework/`。删掉整个 `domains/` 框架测试照过（P-5，夹具自带领域包）。
