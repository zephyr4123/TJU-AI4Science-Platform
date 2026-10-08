//! 平台装了哪一版、装与升级、setup（spec §3「装与升级」「setup」、§4 第 5–6 步）。
//!
//! 装与升级跑的是带版本号的 `<DIST>/<版本>/install.sh`（Windows `install.ps1`，版本是 PEP 440 写法），先按
//! 签名清单核 sha256，环境带 `AI4SCI_NO_SETUP=1`（setup 由外壳另起）与 `AI4SCI_WHEEL_SHA256`（脚本拿它
//! 核 wheel），包里 uv 所在的目录排在 PATH 最前（够新就不再从 CDN 下一份 uv）。Windows 上用 5.1 的
//! PowerShell 把脚本按 UTF-8 读成字符串交给脚本块跑（`contract::PS1_COMMAND`），不走 `-File`：组策略的
//! 执行策略压得过命令行的 `-ExecutionPolicy`。

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use sha2::{Digest, Sha256};
use url::Url;

use crate::contract::{
    EXIT_BUSY, INSTALL_PS1, INSTALL_SCRIPT_ENV, INSTALL_SH, NO_SETUP_ENV, PS1_COMMAND, SETUP_ARGS,
    VERSION_ARGS, VERSION_PREFIX, WHEEL_SHA256_ENV,
};
use crate::env::Overlay;
use crate::manifest::Manifest;
use crate::progress;
use crate::supervise::{Kind, Launch, Sink, Stream, Supervisor};
use crate::version::Version;

const VERSION_TIMEOUT: Duration = Duration::from_secs(30);
const SCRIPT_TIMEOUT: Duration = Duration::from_secs(60);
/// 安装脚本、setup 这么久一行都不说就当卡住了（连接还在、数据不来）：收掉，启动页给「重试」。两边下载
/// 时都按时报进度，正常的慢不会这么久不出声
pub const SILENT_LIMIT: Duration = Duration::from_secs(5 * 60);

#[derive(Debug, PartialEq, Eq)]
pub enum Installed {
    Done,
    /// 退出码 75：平台还开着（网页版服务或后台实验），脚本什么都没动
    Busy,
    /// 没装好；带一句为什么（脚本最后一行 ✗ 的说明，或退出码）
    Failed(String),
}

/// 装哪一版、对哪个 sha256：都取自签过的清单（最新的那份，或这一版自己那份），不跑没核过的脚本
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Target {
    pub version: Version,
    pub script_sha256: String,
    pub wheel_sha256: String,
}

impl Target {
    pub fn signed(manifest: &Manifest) -> Self {
        Self {
            version: manifest.version.clone(),
            script_sha256: manifest.script_sha256().to_string(),
            wheel_sha256: manifest.wheel.clone(),
        }
    }
}

pub fn script_name() -> &'static str {
    if cfg!(windows) {
        INSTALL_PS1
    } else {
        INSTALL_SH
    }
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// 怎么起这份脚本：程序、参数、额外的环境变量
pub fn script_command(script: &Path) -> (PathBuf, Vec<OsString>, Vec<(String, OsString)>) {
    if cfg!(windows) {
        let root = std::env::var_os("SystemRoot").unwrap_or_else(|| OsString::from(r"C:\Windows"));
        let ps = PathBuf::from(root).join(r"System32\WindowsPowerShell\v1.0\powershell.exe");
        let args = ["-NoProfile", "-NonInteractive", "-Command", PS1_COMMAND].map(OsString::from);
        let env = vec![(
            INSTALL_SCRIPT_ENV.to_string(),
            script.as_os_str().to_os_string(),
        )];
        (ps, args.to_vec(), env)
    } else {
        (
            PathBuf::from("/bin/sh"),
            vec![script.as_os_str().to_os_string()],
            Vec::new(),
        )
    }
}

async fn fetch_script(
    client: &reqwest::Client,
    dist: &Url,
    target: &Target,
) -> Result<Vec<u8>, String> {
    let url = dist
        .join(&format!("{}/{}", target.version.pep440(), script_name()))
        .map_err(|error| error.to_string())?;
    let get = async {
        let resp = client.get(url.clone()).send().await?.error_for_status()?;
        resp.bytes().await
    };
    let bytes = tokio::time::timeout(SCRIPT_TIMEOUT, get)
        .await
        .map_err(|_| format!("{} 秒内没取到 {url}", SCRIPT_TIMEOUT.as_secs()))?
        .map_err(|error| format!("取不到 {url}：{}", error.without_url()))?;
    if sha256_hex(&bytes) != target.script_sha256 {
        return Err(format!("{url} 的 sha256 与签名清单对不上，没跑"));
    }
    Ok(bytes.to_vec())
}

/// 装或升级到 `target`：取脚本、核对、照跑；退 0 装好、75 平台还开着，其余是没装好
#[allow(clippy::too_many_arguments)]
pub async fn platform(
    sup: &Supervisor,
    client: &reqwest::Client,
    dist: &Url,
    target: &Target,
    overlay: &Overlay,
    sidecar: Option<&Path>,
    cwd: &Path,
    sink: Sink,
) -> Installed {
    let bytes = match fetch_script(client, dist, target).await {
        Ok(bytes) => bytes,
        Err(reason) => {
            log::warn!("install.fetch_failed reason={reason}");
            return Installed::Failed(reason);
        }
    };
    let ext = if cfg!(windows) { "ps1" } else { "sh" };
    let script = cwd.join(format!("install-{}.{ext}", target.version));
    if let Err(error) = std::fs::write(&script, &bytes) {
        return Installed::Failed(format!("安装脚本写不下：{} {error}", script.display()));
    }
    let (program, args, mut extra) = script_command(&script);
    extra.extend([
        (NO_SETUP_ENV.to_string(), OsString::from("1")),
        (
            WHEEL_SHA256_ENV.to_string(),
            OsString::from(&target.wheel_sha256),
        ),
    ]);
    let overlay = match sidecar {
        Some(dir) => overlay.with_front(dir),
        None => overlay.clone(),
    };
    // 为什么没装好：最后一行 ✗ 的说明；一行 ✗ 都没有（脚本没跑起来）用 stderr 的最后一行
    let last_failure = Arc::new(Mutex::new(None::<String>));
    let last_error = Arc::new(Mutex::new(None::<String>));
    let (seen, said) = (last_failure.clone(), last_error.clone());
    let sink: Sink = Arc::new(move |kind, stream, line| {
        if let Some(row) = progress::parse(line)
            && row.mark == "✗"
        {
            *seen.lock().unwrap_or_else(|p| p.into_inner()) =
                Some(format!("{} {}", row.label, row.note));
        } else if stream == Stream::Err && !line.trim().is_empty() {
            *said.lock().unwrap_or_else(|p| p.into_inner()) =
                Some(line.trim().chars().take(200).collect());
        }
        sink(kind, stream, line);
    });
    log::info!("install.start version={}", target.version);
    let launch = Launch {
        kind: Kind::Install,
        program,
        args,
        overlay,
        extra,
        cwd: cwd.to_path_buf(),
    };
    let exit = match sup.spawn(launch, sink) {
        Ok(child) => child.finish_unless_silent(SILENT_LIMIT).await,
        Err(error) => return Installed::Failed(format!("安装脚本起不来：{error}")),
    };
    let _ = std::fs::remove_file(&script);
    let Some(exit) = exit else {
        return Installed::Failed(format!(
            "{} 分钟没有动静，可能是网络卡住了",
            SILENT_LIMIT.as_secs() / 60
        ));
    };
    log::info!(
        "install.exit version={} code={:?}",
        target.version,
        exit.code
    );
    match exit.code {
        Some(0) => Installed::Done,
        Some(EXIT_BUSY) => Installed::Busy,
        code => {
            let why = last_failure
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .take();
            let said = last_error.lock().unwrap_or_else(|p| p.into_inner()).take();
            Installed::Failed(why.unwrap_or_else(|| failure_without_mark(code, said)))
        }
    }
}

/// 脚本没留下 ✗ 那一行时的说法：退出码，再带上它往 stderr 说的最后一句
pub fn failure_without_mark(code: Option<i32>, said: Option<String>) -> String {
    let base = match code {
        Some(code) => format!("安装脚本退出码 {code}"),
        None => "安装脚本被停了".to_string(),
    };
    match said {
        Some(said) => format!("{base}：{said}"),
        None => base,
    }
}

/// 装着的是哪一版：`ai4sci --version` 跑不通、看不懂都是 None（当作没有能跑的平台）
pub async fn installed_version(
    sup: &Supervisor,
    cli: &Path,
    overlay: &Overlay,
    cwd: &Path,
) -> Option<Version> {
    if !cli.is_file() {
        log::info!("version.missing cli={}", cli.display());
        return None;
    }
    let said = Arc::new(Mutex::new(Vec::<String>::new()));
    let lines = said.clone();
    let sink: Sink = Arc::new(move |_, stream, line| {
        if stream == Stream::Out {
            lines
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .push(line.to_string());
        }
    });
    let launch = Launch {
        kind: Kind::Version,
        program: cli.to_path_buf(),
        args: VERSION_ARGS.map(OsString::from).to_vec(),
        overlay: overlay.clone(),
        extra: Vec::new(),
        cwd: cwd.to_path_buf(),
    };
    let child = sup.spawn(launch, sink).ok()?;
    let exit = match tokio::time::timeout(VERSION_TIMEOUT, child.wait()).await {
        Ok(exit) => exit,
        Err(_) => {
            log::warn!("version.timeout cli={}", cli.display());
            child.kill();
            return None;
        }
    };
    child.finish().await;
    let lines = said.lock().unwrap_or_else(|p| p.into_inner()).clone();
    let version = lines
        .iter()
        .find_map(|line| line.strip_prefix(VERSION_PREFIX))
        .and_then(|v| Version::parse(v).ok());
    log::info!(
        "version.read code={:?} version={}",
        exit.code,
        version.as_ref().map_or("-".to_string(), |v| v.to_string())
    );
    version.filter(|_| exit.code == Some(0))
}

/// 跑一次 setup（git、两家 CLI 装进家里；不问 key、不起服务）；全过才是 true
pub async fn setup(
    sup: &Supervisor,
    cli: &Path,
    overlay: &Overlay,
    cwd: &Path,
    sink: Sink,
) -> bool {
    let launch = Launch {
        kind: Kind::Setup,
        program: cli.to_path_buf(),
        args: SETUP_ARGS.map(OsString::from).to_vec(),
        overlay: overlay.clone(),
        extra: Vec::new(),
        cwd: cwd.to_path_buf(),
    };
    match sup.spawn(launch, sink) {
        Ok(child) => match child.finish_unless_silent(SILENT_LIMIT).await {
            Some(exit) => exit.code == Some(0),
            None => false,
        },
        Err(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn windows_runs_the_script_as_a_string_through_powershell_5() {
        let (program, args, env) = script_command(Path::new("install-1.9.0.ps1"));
        let args: Vec<_> = args
            .iter()
            .map(|a| a.to_string_lossy().into_owned())
            .collect();
        if cfg!(windows) {
            assert!(program.ends_with(r"System32\WindowsPowerShell\v1.0\powershell.exe"));
            assert_eq!(
                args,
                ["-NoProfile", "-NonInteractive", "-Command", PS1_COMMAND]
            );
            assert_eq!(
                env,
                [(
                    INSTALL_SCRIPT_ENV.to_string(),
                    OsString::from("install-1.9.0.ps1")
                )]
            );
        } else {
            assert_eq!(program, PathBuf::from("/bin/sh"));
            assert_eq!(args, ["install-1.9.0.ps1"]);
            assert!(env.is_empty());
        }
    }

    #[test]
    fn a_script_that_never_got_going_says_why_from_its_stderr() {
        assert_eq!(failure_without_mark(Some(1), None), "安装脚本退出码 1");
        assert_eq!(
            failure_without_mark(Some(1), Some("无法加载文件".into())),
            "安装脚本退出码 1：无法加载文件"
        );
        assert_eq!(failure_without_mark(None, None), "安装脚本被停了");
    }

    #[test]
    fn the_hash_is_lowercase_hex() {
        assert_eq!(
            sha256_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }
}
