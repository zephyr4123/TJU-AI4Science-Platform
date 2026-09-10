# 本地与 CI 共用的入口：CI 跑的就是 `make check`，发版流水线跑的就是 `make package`。
# 技术栈：Python，venv 隔离（红线：依赖不装全局）。依赖钉在 requirements.lock，改依赖走 `make lock`。
.PHONY: check changelog lint test venv lock package release

VENV := .venv
PY   := $(VENV)/bin/python

check: changelog lint test         ## 全部门禁

changelog:                         ## CHANGELOG.md 格式校验
	.github/scripts/changelog.sh check

venv: $(VENV)/.stamp               ## 建 venv 并按 lock 装依赖（幂等）

$(VENV)/.stamp: pyproject.toml requirements.lock
	test -x $(PY) || python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -r requirements.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@

lock: venv                         ## 改了 pyproject 的依赖后重新钉版本
	$(VENV)/bin/pip install -q -e ".[dev]"
	$(VENV)/bin/pip freeze --exclude-editable > requirements.lock

lint: venv                         ## 静态检查：ruff（含裸 except 门禁）
	$(VENV)/bin/ruff check .

test: venv                         ## 框架测试；真 CLI 冒烟测试要 AI4SCI_LIVE=1
	$(PY) -m pytest

package:                           ## make package VERSION=0.1.0 → dist/<name>-<ver>.tar.gz + sha256
	.github/scripts/package.sh $(VERSION)

release:                           ## make release VERSION=0.2.0 → 轮转 CHANGELOG、提交、打 tag（不 push）
	.github/scripts/release.sh $(VERSION)
