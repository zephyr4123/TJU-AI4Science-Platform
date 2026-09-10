"""实验内环：唯一有循环的能力（纲领 workflow.md §2）。

一个能力一个子包，跑完即退、互不 import（见 `capabilities/__init__.py`）。对外只露
这五个名字：跑、续跑，以及三种"停下来"的表达。内部怎么分模块（loop / judge / gate /
failures / prompt.md）是这个能力自己的事，别的层不该知道。
"""

from framework.capabilities.experiment.loop import (
    InflightPending,
    ResumeMismatch,
    StopReason,
    resume_loop,
    run_loop,
)

__all__ = ["InflightPending", "ResumeMismatch", "StopReason", "resume_loop", "run_loop"]
