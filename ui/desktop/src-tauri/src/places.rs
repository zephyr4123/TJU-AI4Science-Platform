//! 东西在哪（spec §3）：平台的家、外壳起的是哪个 `ai4sci`、平台发在哪、包里的 uv。
//! 环境变量只在这里读；读法写成收一个查找函数的纯函数，测试不用改进程的环境。

use std::ffi::OsString;
use std::path::{Path, PathBuf};

use url::Url;

use crate::contract::{
    BIN_DIRNAME, CLI_NAME, DESKTOP_CLI_ENV, DIST_DEFAULT, DIST_ENV, HOME_DIRNAME, HOME_ENV,
    INSTALL_LOG_NAME,
};

/// 外壳起的那个 `ai4sci`
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Cli {
    pub path: PathBuf,
    /// 源码桌面（`AI4SCI_DESKTOP_CLI`）：用仓里 `.venv` 的，不装不升级、不跑 setup
    pub from_source: bool,
}

/// 平台的家：`AI4SCI_HOME`，缺省 `~/.ai4sci`
pub fn home(var: impl Fn(&str) -> Option<OsString>, user_home: &Path) -> PathBuf {
    var(HOME_ENV)
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| user_home.join(HOME_DIRNAME))
}

pub fn cli(var: impl Fn(&str) -> Option<OsString>, home: &Path) -> Cli {
    match var(DESKTOP_CLI_ENV).filter(|v| !v.is_empty()) {
        Some(path) => Cli {
            path: PathBuf::from(path),
            from_source: true,
        },
        None => {
            let name = if cfg!(windows) {
                format!("{CLI_NAME}.exe")
            } else {
                CLI_NAME.to_string()
            };
            Cli {
                path: home.join(BIN_DIRNAME).join(name),
                from_source: false,
            }
        }
    }
}

pub fn install_log(home: &Path) -> PathBuf {
    home.join(INSTALL_LOG_NAME)
}

/// 平台发在哪：`AI4SCI_DIST`，缺省 CDN；正式包只认 https（取到的脚本会无人值守地跑）
pub fn dist(var: impl Fn(&str) -> Option<OsString>, release: bool) -> Result<Url, String> {
    let raw = var(DIST_ENV)
        .filter(|v| !v.is_empty())
        .map(|v| v.to_string_lossy().into_owned());
    let raw = raw.as_deref().unwrap_or(DIST_DEFAULT).trim_end_matches('/');
    // 末尾补 `/`：`join("1.9.0/install.sh")` 才接在后面而不是换掉最后一段
    let url = Url::parse(&format!("{raw}/"))
        .map_err(|error| format!("{DIST_ENV} 不是地址：{raw}（{error}）"))?;
    match url.scheme() {
        "https" => Ok(url),
        "http" | "file" if !release => Ok(url),
        other => Err(format!("{DIST_ENV} 只认 https，这里是 {other}：{raw}")),
    }
}

/// 包里的 uv 在主程序旁边（tauri 打包时把 `binaries/uv-<三元组>` 去掉后缀拷过去）
pub fn sidecar_dir() -> Option<PathBuf> {
    tauri::utils::platform::current_exe()
        .ok()?
        .parent()
        .map(Path::to_path_buf)
}

/// Mac 上从 DMG 里或隔离的只读路径跑（spec §4 第 1 步）：更新器换不了它，推出 DMG 后 App 就不见了
pub fn translocated(exe: &Path) -> bool {
    let text = exe.to_string_lossy();
    text.starts_with("/Volumes/") || text.contains("/AppTranslocation/")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn env<'a>(pairs: &'a [(&'a str, &'a str)]) -> impl Fn(&str) -> Option<OsString> + 'a {
        move |name| {
            pairs
                .iter()
                .find(|(k, _)| *k == name)
                .map(|(_, v)| OsString::from(v))
        }
    }

    #[test]
    fn the_home_and_the_cli_follow_the_environment() {
        let user = Path::new("/Users/r");
        assert_eq!(home(env(&[]), user), user.join(".ai4sci"));
        assert_eq!(
            home(env(&[("AI4SCI_HOME", "/tmp/h")]), user),
            PathBuf::from("/tmp/h")
        );
        let installed = cli(env(&[]), Path::new("/h"));
        assert!(!installed.from_source);
        assert_eq!(installed.path.parent(), Some(Path::new("/h/bin")));
        let source = cli(
            env(&[("AI4SCI_DESKTOP_CLI", "/repo/.venv/bin/ai4sci")]),
            Path::new("/h"),
        );
        assert_eq!(
            source,
            Cli {
                path: "/repo/.venv/bin/ai4sci".into(),
                from_source: true
            }
        );
    }

    #[test]
    fn a_release_build_takes_the_platform_only_over_https() {
        let default = dist(env(&[]), true).unwrap();
        assert_eq!(
            default.as_str(),
            "https://media.zephyrxiang.com/ai4science/dist/"
        );
        assert_eq!(
            default.join("1.9.0/install.sh").unwrap().path(),
            "/ai4science/dist/1.9.0/install.sh"
        );
        let local = [("AI4SCI_DIST", "http://127.0.0.1:9/dist/")];
        assert!(dist(env(&local), true).is_err());
        assert!(dist(env(&local), false).is_ok());
        assert!(dist(env(&[("AI4SCI_DIST", "ftp://x/dist")]), false).is_err());
    }

    #[test]
    fn a_disk_image_or_a_translocated_copy_is_not_where_the_app_should_run() {
        assert!(translocated(Path::new(
            "/Volumes/AAAI4S/AAAI4S.app/Contents/MacOS/aaai4s"
        )));
        assert!(translocated(Path::new(
            "/private/var/folders/x/AppTranslocation/ABC/d/AAAI4S.app/Contents/MacOS/aaai4s"
        )));
        assert!(!translocated(Path::new(
            "/Applications/AAAI4S.app/Contents/MacOS/aaai4s"
        )));
    }
}
