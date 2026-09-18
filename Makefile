# 本地与 CI 共用的入口：CI 跑的就是 `make check`，发版流水线跑的就是 `make package`。
# 技术栈：Python，venv 隔离（红线：依赖不装全局）。依赖钉在 requirements.lock，改依赖走 `make lock`。
# 页面是 ui/web 的 Node 项目，依赖钉在 package-lock.json，只装在 ui/web/node_modules。
.PHONY: check changelog lint test venv lock package release ui ui-check

VENV := .venv
PY   := $(VENV)/bin/python

check: changelog lint test ui-check ## 全部门禁（页面的门禁也在里面）

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

# ── 页面（ui/web，React + Tailwind）：依赖装在 ui/web/node_modules，不进全局 ──
UI := ui/web

ui: $(UI)/node_modules/.stamp          ## 构建页面到 ui/web/dist，ai4sci serve 缺省端它
	cd $(UI) && npm run build

ui-check: $(UI)/node_modules/.stamp    ## 页面门禁：素材不进仓（P-17）、类型、lint、单测、构建
	@bad=$$(git ls-files ui | grep -E '\.(png|jpe?g|gif|webp|avif|mp4|webm|mov|ico)$$' || true); \
	if [ -n "$$bad" ]; then echo "二进制素材不进仓（纲领 P-17），上 CDN 再在 ui/web/src/assets.ts 写 URL："; echo "$$bad"; exit 1; fi
	cd $(UI) && npm run check

$(UI)/node_modules/.stamp: $(UI)/package.json $(UI)/package-lock.json
	cd $(UI) && npm ci --no-audit --no-fund
	touch $@
