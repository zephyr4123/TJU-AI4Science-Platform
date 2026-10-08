# ui/desktop · 桌面 App 的外壳

双击就进页面的那个 App（外层 #282，spec 在外层 `docs/specs/desktop.md`）。它是界面层的又一个适配器：一个 Tauri 窗口套在 `ai4sci serve` 外面，**不另起后端**——第一次打开做一行命令安装同样的事，之后每次起服务、把窗口导航到它的地址。页面不打进外壳，随 wheel 升级。

## 1. 四种装法，一份后端

| 装法 | 后端从哪来 | 外壳 |
|---|---|---|
| 源码跑网页版 | 仓里 `.venv`（`make up`） | 没有，浏览器 |
| 一行命令装网页版 | 家里 `~/.ai4sci/bin/ai4sci`（`install/install.sh` / `install.ps1`） | 没有，浏览器 |
| 源码跑桌面 App | 仓里 `.venv`（`make desktop`，`AI4SCI_DESKTOP_CLI` 指过去，不装不升级） | 这里，`tauri dev` |
| 安装包装桌面 App | 家里，第一次打开时装（跑的就是那两份安装脚本） | 这里，`.dmg` / NSIS |

四种共用 `~/.ai4sci`。卸载 App 不碰它。

## 2. 这一层的规矩

- **外壳只认 `src-tauri/src/contract.rs`**：用哪个 `ai4sci`、版本写法、签名清单、安装脚本的变量与退出码、setup 与 serve 的参数、`ok` 那一行、`/health` 的 `turns`、给子进程的环境。这张表冻结、只加不改；内仓 `tests/test_desktop_contract.py`（`make check` 里，不要 Rust）把它与 Python 常量、安装脚本、`cdn.py` 对账。外壳不认识框架内部。
- **页面对外壳零权限**：页面是远程来源，不给它任何 capability（`capabilities/splash.json` 只给本地的启动页）；启动页的四条命令不收 JS 传来的路径、URL；窗口回启动页只认外壳自己发起的那一次；外链只有 http、https、mailto 交给系统，其余协议拒（`src/nav.rs`）。
- **守进程**：每个子进程经 `src/supervise.rs` 起。Windows 上放进外壳握着的 `KILL_ON_JOB_CLOSE` Job（外壳自己不进），Mac 上各自一个进程组、收拾时先杀后代再 killpg；标准输入一律接管道，serve 靠它退出；输出一直读进日志。不用 `tauri-plugin-shell`。
- **两层模块**：不认识 Tauri 的（`contract` `version` `manifest` `env` `places` `supervise` `serve` `install` `nav` `progress` `state` `logfile` `http`）各自能单独测；接 Tauri 的（`shell` `startup` `quit` `update` `window` `commands` `splash`）把它们串起来。新逻辑先问能不能放进前一层。
- **构建输入不进 git**（P-17）：图标从 `ui/web/public/favicon.svg` 生成，uv sidecar 从 `.venv` 或 uv 的发布取，都由 `scripts/prepare.mjs` 在 dev / check / build 第一步放好。
- 正式配置里不许出现调试端口、测试驱动，不开 devtools（`npm run check` 查）。

## 3. 命令

前提：Rust（stable，`rustup component add clippy rustfmt`）、Node 22、仓根 `make venv` 过。Windows 另要 VS 的 C++ 生成工具（MSVC），只承诺 dev，不承诺本机打 NSIS（打包工具要从 GitHub 下）。

| 命令 | 做什么 |
|---|---|
| `make desktop`（Windows：`npm --prefix ui/desktop run dev`） | 源码跑桌面 App：先 `venv ui-auto`，后端用 `.venv` 的 `ai4sci`（`AI4SCI_DESKTOP_CLI` 已设就用设的），`identifier` 换成 `….dev`，不与装好的 App 抢单实例与配置目录 |
| `make desktop-check`（`npm --prefix ui/desktop run check`） | 外壳的门禁：准备图标与 sidecar、配置里没有调试端口、`cargo fmt --check`、`cargo clippy --all-targets -D warnings`、`cargo test` |
| `make desktop-build`（`npm --prefix ui/desktop run build`） | 本机出 `.app` 与 `.dmg`（Mac 上设 `CI=true`，不然打 DMG 时卡在 Finder 的自动化授权）；没有 `TAURI_SIGNING_PRIVATE_KEY` 时不出外壳更新包。多给的参数交给 `tauri build` |
| `node scripts/prepare.mjs --uv-version <v> --target <三元组 \| universal-apple-darwin>` | 发版用：从 uv 的 GitHub 发布取这个三元组的 uv（universal 取两种架构、`lipo` 合成）、核 `.sha256`、放成 sidecar；之后 `tauri build --target … --config '{"version":"X.Y.Z"}'` |

版本号只在发版时由 tag 注入，`tauri.conf.json` 与 `Cargo.toml` 里的 `0.0.0` 是占位；占位版本的外壳从不更新自己。

外壳自己的东西在系统给 App 的目录里（标识 `com.zephyrxiang.aaai4s`，源码桌面是 `….dev`）：Mac 上日志 `~/Library/Logs/<标识>/shell.log`、状态 `~/Library/Application Support/<标识>/shell.json`（上次的端口、跑通过 setup 的版本与家、登录 shell 的 PATH、上次查到版本的时刻、这个发布地址上见过的最新清单）；Windows 在 `%LOCALAPPDATA%\<标识>\` 与 `%APPDATA%\<标识>\` 下。

## 4. 国内镜像（写在自己机器上，不进仓库：CI 在国外）

- rustup：`export RUSTUP_DIST_SERVER=https://rsproxy.cn RUSTUP_UPDATE_ROOT=https://rsproxy.cn/rustup`，装：`curl --proto '=https' --tlsv1.2 -sSf https://rsproxy.cn/rustup-init.sh | sh`；也可以用中科大 `https://mirrors.ustc.edu.cn/rust-static`（PowerShell 写 `$env:RUSTUP_DIST_SERVER=…`）。
- crates：只能写配置文件（`~/.cargo/config.toml`），环境变量设不了：

  ```toml
  [source.crates-io]
  replace-with = 'rsproxy-sparse'
  [source.rsproxy-sparse]
  registry = "sparse+https://rsproxy.cn/index/"
  ```

  中科大：`registry = "sparse+https://mirrors.ustc.edu.cn/crates.io-index/"`。
- npm：`npm config set registry https://registry.npmmirror.com`（用户级，别写进本目录的 `.npmrc`，不然 `package-lock.json` 里记的地址会变）。

## 5. 怎么测

- **`cargo test`**（`npm run check` 里）：纯逻辑的单测在各模块里；`tests/supervise.rs` 用假的 `ai4sci`（`src-tauri/examples/fake_ai4sci.rs`，`cargo test` 顺带编出来）真起进程：读版本、setup 的进度行、serve 的 `ok` 行与 `/health`、关掉标准输入后 serve 与它起的「对话轮次」都没了、不理标准输入的 serve 被整棵收拾、连着不说话的子进程被收掉、端口用不了退 3；`tests/splash.rs` 查启动页的标与 favicon 是同三条路径、只用 `textContent`、只用本地的东西。每个检查器带反例。
- **连真后端**：`npm run check` 里的 `tests/supervise.rs` 最后一条，在临时的家里真起仓里 `.venv` 的 `ai4sci serve`（先 `make venv`），读那一行、问 `/health`、关掉标准输入后 5 秒内退出、端口放出来；后端那边改了约定，这里先红。
- **手动走一遍**：像用户一样起（Mac 用 `open`，不要从开发的终端直接跑二进制，不然继承了终端的 PATH）。不装平台、只看外壳的话，让它起假的 `ai4sci`：

  ```sh
  cargo build --manifest-path ui/desktop/src-tauri/Cargo.toml --examples
  open -n --env AI4SCI_DESKTOP_CLI="$PWD/ui/desktop/src-tauri/target/debug/examples/fake_ai4sci" \
       ui/desktop/src-tauri/target/release/bundle/macos/AAAI4S.app
  ps -axo pid,ppid,pgid,command | grep -E 'AAAI4S|fake_ai4sci'   # 退出以后应当一个不剩
  ```

  假的 serve 端一个小页面，上面有外链、`file:` 链接、回启动页的链接与一个下载，用来看导航规矩；`FAKE_AI4SCI_TURNS=1` 让退出前那一问出来，`FAKE_AI4SCI_STUBBORN=1` 逼外壳走强制收拾（变量说明在那个文件头）。
- 发版前 Mac 本机与 Windows 测试机的端到端验收照 spec §9。
