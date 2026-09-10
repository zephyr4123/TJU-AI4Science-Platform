"""run 实体：一个 run 在磁盘上的布局、checkpoint、只读上下文、生命周期与 work/ 的 git。

四层里在 contracts 之上、memory 之下：这里的东西是**状态**（跑到哪一轮、best 是谁、
路径在哪），只依赖 contracts 与端口（backends / compute），不知道账本与能力的存在。
"""
