# 本地与 CI 共用的入口：CI 跑的就是 `make check`，发版流水线跑的就是 `make package`。
# 技术栈未定：lint / test 目前是占位，定栈后把真实命令接进来，CI 与流水线不用改。
.PHONY: check changelog lint test package release

check: changelog lint test         ## 全部门禁

changelog:                         ## CHANGELOG.md 格式校验
	.github/scripts/changelog.sh check

lint:                              ## 静态检查（占位）
	@echo "lint：技术栈未定，暂无检查项 —— 定栈后在这里接 linter"

test:                              ## 测试（占位）
	@echo "test：技术栈未定，暂无测试 —— 定栈后在这里接测试"

package:                           ## make package VERSION=0.1.0 → dist/<name>-<ver>.tar.gz + sha256
	.github/scripts/package.sh $(VERSION)

release:                           ## make release VERSION=0.2.0 → 轮转 CHANGELOG、提交、打 tag（不 push）
	.github/scripts/release.sh $(VERSION)
