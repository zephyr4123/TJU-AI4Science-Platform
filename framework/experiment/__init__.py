"""实验这一族能力私下的共享层（纲领 P-19）：设计、auto-research、分析、
验证四个能力之间约好的文件格式与算法。

    pack        设计留下的那包东西合不合约：scoring.yaml、harness/、code/、env/、baseline/
    env         env/ 怎么读、uv 怎么建任务级 venv、harness 保证拿到的环境变量
    headroom    预检：门高的唯一定义，值不值得跑
    layout      实验产出目录里东西该在哪
    context     一次实验的只读配置
    checkpoint  续跑唯一认的状态
    gitwork     work/ 的 git 仓：分支 tip 是 best
    ledger      账本  notebook 实验笔记  artifacts 结果索引  results 结果文件
    analysis    analysis.md 的形状  report verify 报告的形状
    prompting   给执行层的账本摘要

框架的契约层不认识这里的任何一样：换一族能力（综述、仿真）就是另起一个这样的包。
依赖：experiment → executor → workspace → contracts；能力包 import 它，它不 import 能力。
"""
