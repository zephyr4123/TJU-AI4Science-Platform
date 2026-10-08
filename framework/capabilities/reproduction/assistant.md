# 原码复现基线：给研究助理的说明

什么时候用：复现一篇论文，拿论文自己的代码原样跑一遍、算出论文报的那几个数，与论文值并排给人看。要自己写代码改进一个方法，用设计阶段的另一个步骤。

前提：需求确认了（复现要问清的四样在需求里：哪篇、哪几个数、复现到第几级、差多少算对上）；论文的代码已经拉进**那个工作区**的 `materials/<代码目录>/`（拉的时候带 `--ws`，原码复现只在那里找）；文献阶段有一次写了材料来源的产出（`sources.md`）。

怎么跑：`ai4sci cap reproduction --from literature/<n> --code <代码目录名> --compute <机器> --ws <名字> --detach`。框架把代码搬进 `code/`，执行层只写起它的 launcher、算论文那几个数的 evaluate、目标就是论文值的 scoring；跑一次就是复现结果。

结局：
- 成了：结论行里 `attainable=` 是论文值、`baseline=` 是我们的值、`upstream_changed=` 是改了几个上游文件（改动在 `upstream.diff`）。**对没对上你不判**：把两列数、σ、改了什么念给研究者，按需求里的标准由他说，签在页面上。
- 草稿有问题（执行层说缺数据、缺 key、跑不起来）：`--continue design/<n> --feedback @<文件>` 喂回去；缺的东西该补就补（拉数据、让研究者给 key 的名字）。
- 跑起来报 `ModuleNotFoundError`：多半是租来的机器上现成的环境缺包。`ai4sci env add --compute <机器> --from materials/<代码目录>/requirements.txt --ws <名字>` 补进去（或直接列包名），再 `--continue design/<n>` 接着跑，壳不用重写。
- 换了机器、环境变了：`--continue` 会拒，重开一次。
