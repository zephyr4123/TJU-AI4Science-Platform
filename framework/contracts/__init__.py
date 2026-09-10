"""契约层：schema 文件、任务包的发现与校验、results.json 的读取。

四层里的最底层（cli → capabilities → executor → memory → run → contracts）：
它回答的是"这份产物合不合约"，而不是"这个 run 现在到哪一步了"。所以本包不 import
framework 的任何其它包——契约要能被任何一层直接调用，反过来依赖会让"校验"跟着"状态"
一起被拖进循环。
"""
