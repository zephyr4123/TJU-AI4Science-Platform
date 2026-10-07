//! 外壳给子进程的环境（spec §3）：在继承的环境上叠加，从不清空（Windows 要 `SystemRoot`、`ComSpec`）。
//!
//! PATH 最前是外壳实际起的那个 `ai4sci` 所在目录（装好的是家里的 `bin/`，源码桌面是仓里 `.venv` 的
//! bin），装平台时 uv 的 sidecar 目录再排到它前面；后面接 Mac 上用户登录 shell 的 PATH（从访达、Dock
//! 起的 App 只有系统缺省那几个目录）。外壳不记录传给子进程的环境。

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use crate::contract::{MAC_LANG, SET_ENV, STRIPPED_ENV};

/// 叠在继承的环境上的那一层：去掉哪些、设哪些
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Overlay {
    pub remove: Vec<&'static str>,
    pub set: Vec<(String, OsString)>,
}

impl Overlay {
    /// `front` 依次排在 PATH 最前；`rest` 是接在后面的 PATH（Mac 上登录 shell 的，取不到是继承的）
    pub fn new(front: &[PathBuf], rest: Option<OsString>, has_lang: bool) -> Self {
        let mut dirs: Vec<PathBuf> = front.to_vec();
        if let Some(rest) = rest {
            dirs.extend(std::env::split_paths(&rest).filter(|d| !d.as_os_str().is_empty()));
        }
        let mut set: Vec<(String, OsString)> = SET_ENV
            .iter()
            .map(|(k, v)| (k.to_string(), OsString::from(v)))
            .collect();
        // 目录名里不会有分隔符；万一有，退回只给前面那几个也比整个 PATH 丢掉强
        let path = std::env::join_paths(&dirs)
            .or_else(|_| std::env::join_paths(front))
            .unwrap_or_default();
        set.push(("PATH".to_string(), path));
        if cfg!(target_os = "macos") && !has_lang {
            set.push(("LANG".to_string(), OsString::from(MAC_LANG)));
        }
        Self {
            remove: STRIPPED_ENV.to_vec(),
            set,
        }
    }

    /// 在继承的环境上照这一层改（`Command` 的 env 在 Windows 上按不分大小写处理 `Path`）
    pub fn apply(&self, cmd: &mut tokio::process::Command) {
        for name in &self.remove {
            cmd.env_remove(name);
        }
        for (name, value) in &self.set {
            cmd.env(name, value);
        }
    }

    pub fn with_front(&self, dir: &Path) -> Self {
        let mut overlay = self.clone();
        if let Some((_, path)) = overlay.set.iter_mut().find(|(k, _)| k == "PATH") {
            let mut dirs = vec![dir.to_path_buf()];
            dirs.extend(std::env::split_paths(path));
            *path = std::env::join_paths(dirs).unwrap_or_else(|_| path.clone());
        }
        overlay
    }
}

// ── Mac：用户登录 shell 的 PATH ──
// `$SHELL -ilc` 只打印两个标记之间的 $PATH：rc 文件里的 echo、提示、报错都落在标记外面；原始输出永远
// 不写日志（rc 里常 export 各种 key），只记取到没有、多长。
const BEGIN: &str = "__AI4SCI_PATH_BEGIN__";
const END: &str = "__AI4SCI_PATH_END__";
pub const LOGIN_SHELL_TIMEOUT: Duration = Duration::from_secs(3);

pub fn login_shell_script() -> String {
    format!("printf '\\n{BEGIN}%s{END}\\n' \"$PATH\"")
}

/// 两个标记之间那一段；没有、空的、跨了行的都不算
pub fn between_markers(output: &str) -> Option<&str> {
    let start = output.find(BEGIN)? + BEGIN.len();
    let len = output[start..].find(END)?;
    let path = output[start..start + len].trim();
    (!path.is_empty() && !path.contains('\n')).then_some(path)
}

/// 起一次登录 shell 取 PATH：自成进程组，超时就整组杀掉（rc 里卡住的 nvm、conda 不拖住启动）
#[cfg(unix)]
pub async fn login_path(shell: &Path, timeout: Duration) -> Option<String> {
    use process_wrap::tokio::{CommandWrap, KillOnDrop, ProcessGroup};
    use tokio::io::AsyncReadExt;

    let mut cmd = tokio::process::Command::new(shell);
    cmd.arg("-ilc").arg(login_shell_script());
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    let mut wrapped = CommandWrap::from(cmd);
    wrapped.wrap(ProcessGroup::leader()).wrap(KillOnDrop);
    let mut child = match wrapped.spawn() {
        Ok(child) => child,
        Err(error) => {
            log::warn!(
                "login_path.spawn_failed shell={} error={error}",
                shell.display()
            );
            return None;
        }
    };
    let mut stdout = child.stdout().take()?;
    let read = async {
        let mut bytes = Vec::new();
        stdout.read_to_end(&mut bytes).await.map(|_| bytes)
    };
    let found = match tokio::time::timeout(timeout, read).await {
        Ok(Ok(bytes)) => between_markers(&String::from_utf8_lossy(&bytes)).map(str::to_string),
        Ok(Err(error)) => {
            log::warn!("login_path.read_failed error={error}");
            None
        }
        Err(_) => {
            log::warn!(
                "login_path.timeout shell={} after_ms={}",
                shell.display(),
                timeout.as_millis()
            );
            None
        }
    };
    let _ = child.start_kill(); // 整组 SIGKILL：rc 里起的东西一起走
    let _ = child.wait().await;
    log::info!(
        "login_path.done found={} len={}",
        found.is_some(),
        found.as_ref().map_or(0, String::len)
    );
    found
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_path_is_read_only_between_the_markers() {
        let noisy = format!(
            "Last login: today\nconda: activating\n\n{BEGIN}/opt/homebrew/bin:/usr/bin{END}\nbye\n"
        );
        assert_eq!(between_markers(&noisy), Some("/opt/homebrew/bin:/usr/bin"));
        assert_eq!(between_markers("ANTHROPIC_API_KEY=sk-x\n"), None);
        assert_eq!(between_markers(&format!("{BEGIN}{END}")), None);
        assert_eq!(between_markers(&format!("{BEGIN}/a\n/b{END}")), None);
        assert_eq!(between_markers(&format!("{BEGIN}/a")), None);
    }

    #[test]
    fn the_overlay_strips_what_would_misplace_a_child_and_never_clears() {
        let rest = std::env::join_paths(["/opt/homebrew/bin", "/usr/bin"]).unwrap();
        let overlay = Overlay::new(&[PathBuf::from("/h/bin")], Some(rest), false);
        for name in [
            "AI4SCI_JOB_ID",
            "AI4SCI_CHAT_ID",
            "AI4SCI_PROJECT",
            "PYTHONHOME",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "CONDA_PREFIX",
        ] {
            assert!(overlay.remove.contains(&name), "{name}");
        }
        assert!(!overlay.remove.contains(&"AI4SCI_HOME"));
        let get = |name: &str| {
            overlay
                .set
                .iter()
                .find(|(k, _)| k == name)
                .map(|(_, v)| v.clone())
        };
        for (name, value) in [
            ("PYTHONUTF8", "1"),
            ("PYTHONUNBUFFERED", "1"),
            ("NO_COLOR", "1"),
            ("UV_NO_PROGRESS", "1"),
        ] {
            assert_eq!(get(name), Some(OsString::from(value)), "{name}");
        }
        let path = get("PATH").unwrap();
        let dirs: Vec<PathBuf> = std::env::split_paths(&path).collect();
        assert_eq!(dirs[0], PathBuf::from("/h/bin"));
        assert_eq!(dirs.len(), 3);
        assert_eq!(get("LANG").is_some(), cfg!(target_os = "macos"));
        assert_eq!(
            Overlay::new(&[], None, true)
                .set
                .iter()
                .filter(|(k, _)| k == "LANG")
                .count(),
            0
        );
    }

    #[test]
    fn the_sidecar_goes_in_front_of_everything_while_installing() {
        let overlay = Overlay::new(
            &[PathBuf::from("/h/bin")],
            Some(OsString::from("/usr/bin")),
            true,
        );
        let installing = overlay.with_front(Path::new("/App/Contents/MacOS"));
        let path = installing
            .set
            .iter()
            .find(|(k, _)| k == "PATH")
            .unwrap()
            .1
            .clone();
        let dirs: Vec<PathBuf> = std::env::split_paths(&path).collect();
        assert_eq!(
            dirs,
            [
                PathBuf::from("/App/Contents/MacOS"),
                PathBuf::from("/h/bin"),
                PathBuf::from("/usr/bin")
            ]
        );
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn a_login_shell_hands_back_only_its_path() {
        let found = login_path(Path::new("/bin/sh"), LOGIN_SHELL_TIMEOUT).await;
        assert!(found.is_some_and(|p| p.contains("/bin")));
    }
}
