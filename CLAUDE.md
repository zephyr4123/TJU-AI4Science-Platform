# TJU AI for Science · platform（生产代码仓）

给 agent 与新成员的约定。本仓是内仓：外层协作仓 `tju-ai4science` 把它 clone 到 `platform/` 目录下，外层对它的 git 完全不知情。

## 目录

| 目录 | 放什么 |
|---|---|
| `apps/web` | 前端 |
| `apps/api` | 后端：HTTP 入口、任务编排 |
| `packages/core` | 不分端：agent 流水线、领域模型、共享工具 |
| `workers/` | 实验执行端：GPU / 集群作业 |
| `db/` | schema、migrations、seed。数据库"代码"在这，数据不在 |
| `infra/` | docker-compose、k8s、部署配置 |
| `tests/` | 跨模块的集成与端到端测试；单测跟着各模块走 |

依赖只指向一个方向：`apps/*` 与 `workers/` 依赖 `packages/core`，反过来不行；任何目录都不依赖外层仓的路径。

## 红线

1. 技术栈尚未确定：目录只是位置约定，不要提前引入框架级抽象；有真实的第二个用例再抽象。
2. 密钥与敏感配置只进环境变量或 `.env`（已 gitignore），绝不进代码。
3. 每个改动合并时写进 `CHANGELOG.md` 的 Unreleased；发版只走 `make release VERSION=x.y.z`，不手工打 tag。
4. `make check` 是提交前门禁，与 CI 完全相同；定栈后 lint / test 接进 Makefile，不另起入口。
5. 跨仓变更（同时动外层文档 / 其它内仓）以外层仓的 GitHub issue 为锚，commit message 引用它。
6. `.claude/` 是本机会话产物，已 gitignore；不要读取或依赖其中内容。

## 版本与发布

- 从 0.1.0 起步，0.x 不承诺兼容；正式发布才进入 1.0.0。tag 形如 `vX.Y.Z`。
- 推送 tag 触发 `release.yml`：对账 CHANGELOG → `make check` → `make package` → 建 Release 并附包，0.x 自动标 pre-release。
- `make package` 目前产出源码快照包；定栈后把构建接进 `package.sh`，流水线不用改。
- commit message 用中文，技术名词保留英文；一个逻辑单元一个 commit。
