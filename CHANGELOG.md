# 变更日志

本仓库所有值得注意的变更都记录在这里。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

- 每个改动合并时，把条目写进 **Unreleased**；发布时 `make release VERSION=x.y.z` 把它轮转成版本小节并打 tag，推送 tag 即触发流水线出包并建 GitHub Release。
- 1.0.0 之前是开发期：0.x 不承诺兼容性，正式发布才进入 1.0.0。
- 条目分类用：新增 / 变更 / 修复 / 移除 / 安全。

## [Unreleased]

## [0.1.0] - 2026-09-08

### 新增
- 生产代码 monorepo 骨架：`apps/web`、`apps/api`、`packages/core`、`workers/`、`db/`、`infra/`、`tests/` 位置约定
- 变更日志与发布流水线：CHANGELOG 机器校验、`make release` 轮转、tag 触发 CI 出包并建 GitHub Release
- `make check` 门禁入口（lint / test 为占位，定栈后接入）

[Unreleased]: https://github.com/zephyr4123/tju-ai4science-platform/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/zephyr4123/tju-ai4science-platform/releases/tag/v0.1.0
