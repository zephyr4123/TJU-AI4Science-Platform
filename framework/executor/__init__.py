"""执行层调用面：组 prompt、调 `Runner` 端口、把取证日志按轮留档。

在 memory 之上：组 prompt 要读账本摘要与笔记，所以它 import memory 与 run。
本层零模型调用——模型在 `backends/` 那一侧的子进程里，这里只负责喂进去、收回来。
"""
