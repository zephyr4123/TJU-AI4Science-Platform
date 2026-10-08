//! 外壳与后端的约定（spec desktop.md §3，外层 #282）：外壳认的后端只有这一个文件里的东西，
//! 不认识框架内部。
//!
//! 这张表冻结、只加不改，不适用内测期例外：已装的外壳跟不上 wheel，要改走弃用周期并抬 `min_desktop`。
//! 内仓 `tests/test_desktop_contract.py`（在 `make check` 里，不要 Rust）用正则读这个文件，与
//! `framework/paths.py`、两份安装脚本、`.github/scripts/cdn.py` 对账，所以常量一律写成
//! `pub const 名字: 类型 = 字面量;`，字符串数组可以折行。

// ── 平台发在哪：CDN 上的签名清单与带版本号的安装脚本 ──
/// 换发布目录（测试指到自己的目录）；release 构建只认 https
pub const DIST_ENV: &str = "AI4SCI_DIST";
pub const DIST_DEFAULT: &str = "https://media.zephyrxiang.com/ai4science/dist";
/// `{"version", "min_desktop", "sha256": {"install.sh", "install.ps1", "wheel"}}`，用更新器那把 key 签
pub const MANIFEST_NAME: &str = "platform.json";
pub const MANIFEST_SIG_NAME: &str = "platform.json.sig";
/// `<DIST>/<版本>/` 下的两份安装脚本；名字也是清单里 sha256 的键
pub const INSTALL_SH: &str = "install.sh";
pub const INSTALL_PS1: &str = "install.ps1";
pub const WHEEL_KEY: &str = "wheel";

// ── 平台的家与用哪个 ai4sci ──
pub const HOME_ENV: &str = "AI4SCI_HOME";
pub const HOME_DIRNAME: &str = ".ai4sci";
pub const BIN_DIRNAME: &str = "bin";
pub const CLI_NAME: &str = "ai4sci";
/// 安装脚本自己的日志，「打开日志」时一起给人看
pub const INSTALL_LOG_NAME: &str = "install.log";
/// 源码桌面：用仓里 `.venv` 的 `ai4sci`，不装不升级
pub const DESKTOP_CLI_ENV: &str = "AI4SCI_DESKTOP_CLI";

// ── 装与升级 ──
/// 安装脚本装完不交给 setup（setup 由外壳另起）
pub const NO_SETUP_ENV: &str = "AI4SCI_NO_SETUP";
/// 签名清单里的 wheel sha256：脚本拿它核 wheel，不再信 CDN 上的 `.sha256`
pub const WHEEL_SHA256_ENV: &str = "AI4SCI_WHEEL_SHA256";
/// 平台还开着（网页版服务或后台实验在用家里的平台），脚本什么都没动
pub const EXIT_BUSY: i32 = 75;
/// Windows 上起 install.ps1：`powershell.exe -NoProfile -NonInteractive -Command <这一句>`，脚本的路径在
/// `AI4SCI_INSTALL_SCRIPT` 里。读成字符串交给脚本块，与 `irm | iex` 一样不受执行策略管（组策略设了
/// AllSigned 的机器上 `-File` 起不来）；按 UTF-8 读，不靠 BOM；脚本自己 exit，没 exit 就是没装好
pub const INSTALL_SCRIPT_ENV: &str = "AI4SCI_INSTALL_SCRIPT";
pub const PS1_COMMAND: &str = "& ([ScriptBlock]::Create([IO.File]::ReadAllText($env:AI4SCI_INSTALL_SCRIPT, [Text.Encoding]::UTF8))); exit 1";

// ── 版本 ──
/// 外壳能驱动的最低平台：`--until-stdin-closes`、`--no-input`、`AI4SCI_NO_SETUP` 都是 1.9.0 才有
pub const MIN_PLATFORM: &str = "1.9.0";
/// `ai4sci --version` 打 `ai4sci <PEP 440 版本>`
pub const VERSION_PREFIX: &str = "ai4sci ";
pub const VERSION_ARGS: [&str; 1] = ["--version"];

// ── setup：不问 key、不探模型、不开浏览器、不起服务 ──
pub const SETUP_ARGS: [&str; 3] = ["setup", "--no-serve", "--no-input"];

// ── serve ──
pub const SERVE_HOST: &str = "127.0.0.1";
/// listen 之后 stdout 打且只打这一行开头的一行，Tab 分隔的字段只加不改
pub const SERVE_OK_PREFIX: &str = "ok http://";
/// 端口用不了（被占、Windows 的保留端口段）
pub const EXIT_PORT: i32 = 3;
pub const HEALTH_PATH: &str = "/health";
/// `/health` 里此刻在跑的对话轮数
pub const TURNS_FIELD: &str = "turns";

/// `ai4sci serve` 的参数：只听本机，标准输入关了就收拾在跑的轮次后退出
pub fn serve_args(port: u16) -> Vec<String> {
    let port = port.to_string();
    [
        "serve",
        "--host",
        SERVE_HOST,
        "--port",
        &port,
        "--until-stdin-closes",
    ]
    .map(String::from)
    .to_vec()
}

// ── 进度行：`  <标记> <标签> <说明>` ──
/// 装好、没装好、要注意但不算失败、开始下载、下载中（同一标签就地更新）
pub const MARKS: [&str; 5] = ["✓", "✗", "!", "…", "↓"];

// ── 外壳给子进程的环境：在继承的环境上叠加，从不清空 ──
pub const SET_ENV: [(&str, &str); 4] = [
    ("PYTHONUTF8", "1"),
    ("PYTHONUNBUFFERED", "1"),
    ("NO_COLOR", "1"),
    ("UV_NO_PROGRESS", "1"),
];
/// 漏进子进程会让它落错地方：作业号让 `--detach` 被拒、对话号让人的确认被当成助理在调、
/// 项目让助理落到错的项目上；Python 的这几个会弄坏平台自己的解释器
pub const STRIPPED_ENV: [&str; 7] = [
    "AI4SCI_JOB_ID",
    "AI4SCI_CHAT_ID",
    "AI4SCI_PROJECT",
    "PYTHONHOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
];
/// Mac 上从访达、Dock 起的 App 没有 `LANG`
pub const MAC_LANG: &str = "en_US.UTF-8";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serve_listens_only_on_loopback_and_stops_with_its_stdin() {
        assert_eq!(
            serve_args(51234),
            [
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "51234",
                "--until-stdin-closes"
            ]
        );
    }

    #[test]
    fn the_powershell_command_reads_the_script_from_its_own_variable() {
        assert!(PS1_COMMAND.contains(&format!("$env:{INSTALL_SCRIPT_ENV}")));
    }

    #[test]
    fn the_home_is_handed_down_untouched() {
        assert!(!STRIPPED_ENV.contains(&HOME_ENV));
        assert!(!STRIPPED_ENV.contains(&DIST_ENV));
    }
}
