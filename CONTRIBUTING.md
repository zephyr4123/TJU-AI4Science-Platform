# 怎么协作（内仓）

流程只有一份，在外层仓的 [`CONTRIBUTING.md`](https://github.com/zephyr4123/TJU-AI4Science/blob/main/CONTRIBUTING.md)：分支模型（`main` ← `release/X.Y` ← `feat/<issue 号>-<slug>`）、一件事的生命周期、版本与发布、CHANGELOG 怎么写。issue 开在外层仓，本仓的 commit 与 PR 引它。这里只放本仓 PR 合并前的清单：

- [ ] 分支从当前的 `release/X.Y` 切出，PR 回到它；一条 issue 一个分支
- [ ] `make check` 绿（changelog + ruff + skills + pytest + ui-check，与 CI 完全相同；别接 `| tail`）
- [ ] 改了行为先有一条会失败的测试（`tests/README.md`）；改了检查器带反例
- [ ] 改了页面看得见的东西过了浏览器（`ui/README.md` §5）
- [ ] 改了行为的地方文档同步改了：分层与约定在 `framework/README.md`，前端在 `ui/README.md`，手册在 `docs/`，产品说法回写外层纲领
- [ ] 改了 `coordinator/*.md` 或能力的 `prompt.md` 知道那是线上 prompt，`test_chat_guide` 与对应能力的测试过了
- [ ] 加了端点三处登记（`server.py` 清单与 `API_ROOTS`、`vite.config.ts`、`api/`）；加了子命令 `cli/__init__.py` 加一行
- [ ] `CHANGELOG.md` Unreleased 加了一行，带 `#issue`；不兼容的写了迁移办法（1.x 冻结的契约见外层 CONTRIBUTING「版本与发布」）
- [ ] commit message 中文、末尾 `（#n）`，没有 AI 署名

发版（发版人）：在 `main` 上 `make release VERSION=X.Y.Z`，推 tag 出 wheel；`release/X.Y` 上 `make release VERSION=X.Y.0-rc.N` 出预发布。
