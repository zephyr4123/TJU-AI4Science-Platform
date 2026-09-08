<h1 align="center">tju-ai4science-platform</h1>

<p align="center">TJU AI for Science · 生产代码仓</p>

## 这是什么

科研全自动化平台的生产代码，一个 monorepo 装下前端、后端、不分端的核心库、执行端、数据库与部署配置。项目文档、调研与决策记录在外层协作仓 [`tju-ai4science`](https://github.com/zephyr4123/tju-ai4science)，本仓由它的 `./repos clone all` 拉到 `platform/` 目录下。

## 目录

```
platform/
├── apps/
│   ├── web/          前端
│   └── api/          后端：HTTP 入口、任务编排
├── packages/
│   └── core/         不分端：agent 流水线、领域模型、共享工具
├── workers/          实验执行端：GPU / 集群作业
├── db/               schema、migrations、seed
├── infra/            docker-compose、k8s、部署配置
├── tests/            跨模块的集成与端到端测试
├── Makefile          check / package / release 入口，本地与 CI 共用
└── CHANGELOG.md      变更日志
```

技术栈尚未确定，目录只是位置约定；定栈后 `Makefile` 里的 lint / test / package 接上真实命令即可，CI 不用改。

## 怎么跑

技术栈确定后补充。当前可用的：

```bash
make check                       # 门禁：CHANGELOG 校验 + lint + test（后两项占位）
make package VERSION=0.1.0       # 出包到 dist/
```

## 版本与发布

1. 改动合并时把条目写进 `CHANGELOG.md` 的 Unreleased。
2. `make release VERSION=0.2.0`：轮转 CHANGELOG、提交、打 tag，不 push。
3. `git push origin main --follow-tags`：tag 触发流水线，对账 CHANGELOG、`make check`、`make package`、建 GitHub Release 并附上 `dist/` 里的包。

从 0.1.0 起步，0.x 自动标 pre-release；正式发布才进入 1.0.0。

## 约定

规矩集中在 [`CLAUDE.md`](CLAUDE.md)。架构决策记录在外层仓 `docs/adr/`。
