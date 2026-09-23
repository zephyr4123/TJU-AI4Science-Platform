# 本地与 CI 共用的入口：CI 跑的就是 `make check`，发版流水线跑的就是 `make package`。
# 技术栈：Python，uv 管一切（红线：依赖不装全局）——.venv 按 uv.lock 同步，改依赖走 `make lock`；
# skill 的脚本各自带依赖（PEP 723 + 锁文件），环境在 uv 的全机缓存里，`make skills` 预热（纲领 P-22）。
# 页面是 ui/web 的 Node 项目，依赖钉在 package-lock.json，只装在 ui/web/node_modules。
# 两种人（外层 #138）：改代码的 clone 仓库 `make up`；只用的装 Release 里的 wheel，`ai4sci serve`。
.PHONY: up check changelog lint test venv lock package release ui ui-auto ui-check skills clean purge

VENV := .venv
PY   := $(VENV)/bin/python
# uv 是唯一的前提：官方一行装到 ~/.local/bin（curl -LsSf https://astral.sh/uv/install.sh | sh）
UV   := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
PORT ?= 8765

up: venv ui-auto skills             ## 一行起服务：环境、页面、skill 预热、自检，然后 ai4sci serve
	-$(PY) -m framework.cli check
	$(PY) -m framework.cli serve --port $(PORT)

check: changelog lint skills test ui-check ## 全部门禁（skill 预热与页面的门禁也在里面）

changelog:                         ## CHANGELOG.md 格式校验
	.github/scripts/changelog.sh check

venv: $(VENV)/.stamp               ## 建 .venv 并按 uv.lock 同步依赖（幂等；lock 过期就报错，先 make lock）

$(VENV)/.stamp: pyproject.toml uv.lock
	@test -x "$(UV)" || { echo "缺 uv：curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	$(UV) sync --locked
	touch $@

lock:                              ## 改了 pyproject 的依赖后重新钉版本（uv.lock）
	$(UV) lock

lint: venv                         ## 静态检查：ruff（含裸 except 门禁）
	$(VENV)/bin/ruff check .

skills: venv                       ## skill 门禁与预热：SKILL.md 合规范、每个脚本锁文件对得上、环境建好（唯一联网的一步）
	$(PY) -m framework.skills

test: venv                         ## 框架测试；真 CLI 冒烟测试要 AI4SCI_LIVE=1
	$(PY) -m pytest

package: venv                      ## make package VERSION=0.2.0 → dist/ai4sci-<ver>-py3-none-any.whl（含页面与出厂件）+ sdist + sha256
	.github/scripts/package.sh $(VERSION)

release:                           ## make release VERSION=0.2.0 → 轮转 CHANGELOG、提交、打 tag（不 push）
	.github/scripts/release.sh $(VERSION)

clean:                             ## 删仓里装出来的东西：.venv、node_modules、页面构建、打包暂存；不碰配置、登录、数据
	rm -rf $(VENV) $(UI)/node_modules $(UI)/dist framework/shipped dist build

purge: clean                       ## 再把 uv 的缓存清掉（skill 的环境下次要重建）
	-$(UV) cache clean

# ── 页面（ui/web，React + Tailwind）：依赖装在 ui/web/node_modules，不进全局 ──
UI := ui/web

ui: $(UI)/node_modules/.stamp          ## 构建页面到 ui/web/dist，ai4sci serve 缺省端它
	cd $(UI) && npm run build

ui-auto:                               ## 有 node 就构建页面；没有就用已有的构建，两样都没有才报错
	@if command -v npm >/dev/null 2>&1; then $(MAKE) ui; \
	elif [ -f $(UI)/dist/index.html ]; then echo "没有 node，用已有的页面构建 $(UI)/dist"; \
	else echo "没有 node 也没有页面构建：装 node 22 再 make up，或从 Release 装 wheel 直接 ai4sci serve"; exit 1; fi

ui-check: $(UI)/node_modules/.stamp    ## 页面门禁：素材不进仓（P-17）、类型、lint、单测、构建
	@bad=$$(git ls-files ui | grep -E '\.(png|jpe?g|gif|webp|avif|mp4|webm|mov|ico)$$' || true); \
	if [ -n "$$bad" ]; then echo "二进制素材不进仓（纲领 P-17），上 CDN 再在 ui/web/src/assets.ts 写 URL："; echo "$$bad"; exit 1; fi
	cd $(UI) && npm run check

$(UI)/node_modules/.stamp: $(UI)/package.json $(UI)/package-lock.json
	cd $(UI) && npm ci --no-audit --no-fund
	touch $@
