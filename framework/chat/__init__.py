"""协调 agent 的对话：起一轮、续接、落盘、给网页当后端（外层 #51）。

在四层的 chat 层（与 executor 同档：可 import memory / run / contracts，碰 `backends` 的
`Chat` 端口）。零模型调用——模型跑在适配器起的子进程里。这一层只做三件事：把协调层指南
塞进 system prompt、把每一轮的事件落盘、把同一套函数同时暴露给 CLI 与 HTTP。
"""
