"""契约层：框架认的东西的形状——七个研究阶段、需求与确认、产出与签字、流程文件、能力描述符。

分层链的最底层（cli → capabilities → chat → experiment → executor → workspace → skills →
contracts）：它回答的是"这份东西合不合约"，而不是"现在走到哪一步了"。所以本包不 import
framework 的任何其它包——契约要能被任何一层直接调用，反过来依赖会让"校验"跟着"状态"
一起被拖进循环。族内的约定（实验族的 scoring / results / report）不在这里，在 `experiment/`
（纲领 P-19）。
"""
