# 接一颗能力

给要往平台里加一颗能力（或想把一个 skill 变成流里一格）的人。读完照做，不用问人。验收标准：**换一个人、换一个阶段，照这份文档写出来的能力，`discover()` 放行、下游能读、页面能显示。** 卡在哪一步，就是这份文档的 bug，请开 issue。

为什么是这套规矩，见外层纲领 P-18、P-19、P-20（`docs/architecture/README.md`）。这里只讲怎么做。

## 一颗能力是什么

一个阶段里的一件活。对研究助理就是一条命令 `ai4sci cap <name>`，跑一次，工作区里多一个文件夹 `<stage>/<n>/`。

```
 头（只有这三样能进）                            尾（只有这一处能出）
 ───────────────────                            ───────────────────
 requirement.md  已确认的需求                    <stage>/<n>/
 materials/      原件，只读                        ├ meta.yaml    框架写：谁产的、from（带 hash）、按哪版需求、result
 --from STAGE/N  点名的上游产出，冻结             ├ 主文件       本阶段钉死的名字（见下表）
        │                                         ├ 族文件       同族能力私下的约定
        ▼                                         ├ 其它文件     私有，谁都不许依赖
 run(output_dir, inputs, ports, **params)         └ signed.json  人签，框架写
        ▲              ▲
     params          ports                       返回一行结论 → meta.result
   （只认标量）   （runner / compute）             失败 raise CapabilityFailed
```

对所有能力一样的只有这个形状。要哪几个文件、留哪几个文件，是你这颗能力自己的事，写在描述符里。

## 先回答四个问题

写代码之前，把这四句写下来，它们就是描述符的骨架：

1. **进哪个阶段。** 七个里选一个：文献、假设、设计、实验、分析、写作、验证。一颗能力只属于一个阶段；同一段代码想在两个阶段用，就是两颗能力。
2. **非要上游的哪几个文件。** 按阶段说（「分析阶段的 `analysis.md`」），不按能力说。这些文件不在，你开工就报错。
3. **留下哪几个文件。** 必须包含本阶段的主文件；其它按需要。
4. **那句结论怎么说。** 助理和页面只看这一句决定下一步，所以要说清「留下了什么、下一步能拿它干什么」：「初稿 4 节 2300 字，图 3 张，引用 12 条」，不是「done」。

## 文件名按阶段定，不按能力定

每个阶段钉一个主文件。进这个阶段的任何能力都必须留下它，名字不许自创；下游只认阶段主文件，不认是哪颗能力产的——换一颗同阶段的能力，下游一行不改。

| 阶段 | 主文件 | 状态 |
|---|---|---|
| 文献 | — | 待第一颗能力定 |
| 假设 | — | 待第一颗能力定 |
| 设计 | `scoring.yaml` | 已定（`design`） |
| 实验 | `ledger.tsv` + `iters/iter_N/results.json` | 已定（`auto-research`） |
| 分析 | `analysis.md` | 已定（`analysis`） |
| 写作 | — | 待第一颗能力定 |
| 验证 | `report.json` | 已定（`verify`） |

表在 `framework/capabilities/__init__.py` 的 `MAIN_FILES`，`discover()` 查你描述符的「留下什么」有没有写到它，没写不让注册。

- **你是这个阶段第一颗能力**：主文件名由你定，同时写进 `MAIN_FILES`。定名照 P-13：角色名词（`draft.md`、`hypothesis.md`），不带能力名、模型名、日期、版本号。定了就锁死，之后谁想改是一次决策。
- **阶段已有主文件**：照用。你的产出可以另外多留文件，但那些是私有的——没有别的能力可以依赖它们。下游真要用，把它提成族文件。

产出目录里的文件分三层：

| 层 | 谁定名 | 谁能读 | 放哪 |
|---|---|---|---|
| 主文件 | 阶段（第一颗能力） | 任何下游 | `MAIN_FILES` |
| 族文件 | 族（`framework/<族>/`，实验族已有 `experiment/`） | 同族能力 | 族包里的读写函数与 schema |
| 私有文件 | 你 | 只有你自己 | 不登记 |

开一个新族（比如文献族、写作族）就是建 `framework/<族>/`，把这族共用的文件名、读写函数、机器要读的 schema 放那儿。能力互不 import，同族共用的只经族包。

## 谁产的记在 meta，不记在文件名

两颗写作能力各跑一次：

```
writing/1/draft.md     meta: by: paper-draft    from: [analysis/2, verification/1]
writing/2/draft.md     meta: by: report-draft   from: [analysis/2]
```

文件名一样，文件夹编号和 `meta.yaml` 不同。「谁产的、读了谁、按哪版需求」都在 meta 里，页面的「来源 / 输入」、`ai4sci show output writing/1`、冻结的 hash 核对读的都是它。不要把能力名写进文件名——一写进去，下游就得认识每一颗能力。

## 写代码

一个能力一个子包 `framework/capabilities/<name>/`（包名下划线，命令名连字符：`paper_draft/` → `ai4sci cap paper-draft`）。`__init__.py` 导出两样：

```python
from framework.contracts.capability import Capability, CapabilityFailed, Inputs, Param, Ports

DESCRIPTOR = Capability(
    name="paper-draft",
    stage="写作",
    title="论文初稿",                       # 名词短语，给研究者看
    does="...",                             # 干什么：讲机制，带专业术语
    does_not="...",                         # 不干什么
    brings="...",                           # 要带什么进来：按阶段说文件名
    leaves="draft.md、figures/、refs.bib",   # 留下什么：必须写到本阶段主文件
    stops="...",                            # 什么时候停：成功停在哪、失败怎么报
    params=(Param("sections", "int", 4, "写几节"),),
    needs_executor=True,                    # 要起执行层（模型）就 True；零模型的能力 False
)


def run(output_dir: Path, inputs: Inputs, ports: Ports, *, sections: int = 4) -> str:
    analysis_dir = inputs.one_of("analysis", "论文初稿")       # 恰好要一个分析产出，少了多了都报错
    verification = inputs.one_of("verification", "论文初稿")
    ...                                                        # 只往 output_dir 写
    return f"初稿 {sections} 节 …"                              # 一行结论
```

规矩，每条都有机器守着：

- `run` 前三个参数固定是 `output_dir, inputs, ports`，后面只许关键字参数，且与 `params` 一一对应（`discover()` 断言）。
- 参数只认 `int` / `float` / `str` / `bool`。要更复杂的输入，那是文件——放 `materials/` 或上游产出。每次调用才定的参数（接不接着跑、修改意见）标 `in_flow=False`，流里写不了。
- 读输入只经 `inputs`：`inputs.workspace` 下的 `requirement.md` 与 `materials/`、`inputs.of_stage(slug)` / `inputs.one_of(slug, label)` 点名的产出。没有「读最新」。
- 只往 `output_dir` 写。`meta.yaml` 与 `signed.json` 是框架写的，不要碰。
- 缺东西开工就报错：`raise CapabilityFailed("论文初稿要分析阶段的 analysis.md：--from analysis/<n>")`。说清缺哪个阶段的哪个文件，助理读了报错去补。
- 失败 `raise CapabilityFailed`，不降级不兜底；产出目录留着，meta 记 `status: failed`。
- 起执行层的能力：提示模板放子包里的 `prompt.md`；领域包给这一族的补充在 `domains/<包>/prompts/<族>.md`，skill 在 `domains/<包>/skills/*/SKILL.md`，由你这颗能力快照进产出目录再进提示（看 `auto_research/open.py::_snapshot_domain`）。
- 能力互不 import。同族共用的读写放 `framework/<族>/`，`tests/test_layering.py` 查。

不用写的：CLI 子命令、`--from` / `--flow` / `--continue` / `--detach`、页面上的节点与能力小片、`show caps`——都从描述符生成。

## skill 呢

skill 不是一格。它是随某颗执行层能力进去的一篇说明书，自己不写盘、不出现在流里。想让一个 skill 变成流里的一格，把它包成能力：描述符 + `run` 起执行层 + 留下本阶段主文件。「只写说明书不写代码的能力」还没有，见外层 open-questions Q-14。

## 测试

- `tests/test_contracts_capability.py` 的 `discover()` 用例自动覆盖新子包：描述符、入口签名、主文件。
- 自己的用例照 `tests/test_capability_<name>.py`：给一个假工作区与假上游产出（`tests/fixtures/packs_factory.py` `runs_factory.py`），跑 `run`，断言只在 `output_dir` 写了东西、主文件在、返回了一行；再跑一次缺输入的，断言 `CapabilityFailed` 的信息说到了阶段与文件名。
- 执行层用 `tests/fixtures/scripted_backend.py` 的脚本化 Runner，不连真模型。

## 例子：写作阶段的「论文初稿」

| 问题 | 答案 |
|---|---|
| 进哪个阶段 | 写作 |
| 非要上游什么 | 确认过的需求；`--from analysis/N` 的 `analysis.md`；`--from verification/N` 的 `report.json` 且 `status` 是 PASS |
| 留下什么 | `draft.md`（写作阶段的主文件，由它定名）、`figures/`、`refs.bib` |
| 一句结论 | 「初稿 4 节 2300 字，图 3 张，引用 12 条」 |
| 什么时候停 | 初稿写完就停；`analysis.md` 不在或验证没过，开工就报错 |
| 谁用 | 人看初稿签字；以后的「审稿」`--from writing/N` 读 `draft.md`，不管是谁写的 |

## 交付前

- `make check` 绿（changelog + ruff + pytest + 页面）。
- `CHANGELOG.md` Unreleased 一条，外层 issue 为锚。
- 描述符五栏是给研究者、助理、工程师读同一份的：讲机制、带专业术语、不写路径表、不用「按钮」「键」这类比喻。
