# coordinator/ · 协调层 skill 包

协调层 = 人（PI）+ 协调 agent。这里放的是"怎么当科研助理、怎么驱动框架"的指南与 skill，注入到当协调层的那个 CLI（Claude Code 读项目 CLAUDE.md，Codex 读 AGENTS.md）。**执行层会话不许加载这里的任何东西**（纲领 P-11），执行层的 skill 跟领域包走，在 `domains/<id>/skills/`。

platform 0.2.0 只放一份入口指南（spec R-10），等真有第二条 skill 再建 `skills/` 目录。放哪、怎么注入见外层 issue #19。
