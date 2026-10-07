//! 外壳这一次运行的全部状态：交给 Tauri 管（`app.state::<Shell>()`），启动、退出、窗口的钩子都从这里拿。

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{AppHandle, Manager, Runtime};
use url::Url;

use crate::nav::Gate;
use crate::places::{self, Cli};
use crate::splash::Splash;
use crate::state::Store;
use crate::supervise::{Handle, Supervisor};
use crate::version::Version;
use crate::{http, logfile};

/// 退出前等 serve 自己收拾在跑的轮次多久（spec §4「退出」第 3 步）
pub const GRACE: std::time::Duration = std::time::Duration::from_secs(5);

pub struct Shell {
    pub sup: Supervisor,
    pub splash: Splash,
    pub gate: Gate,
    pub store: Store,
    /// 窗口回启动页时去的地址
    pub splash_url: Url,
    pub log_path: PathBuf,
    pub home: PathBuf,
    pub cli: Cli,
    /// 取不到（`AI4SCI_DIST` 写错、正式包给了 http）时是那句为什么
    pub dist: Result<Url, String>,
    /// 子进程的工作目录：外壳的临时目录（`uv python find` 会读当前目录的 `.venv`）
    pub tmp: PathBuf,
    pub internet: reqwest::Client,
    pub loopback: reqwest::Client,
    /// 在跑的 serve
    pub serve: Mutex<Option<(Url, Handle)>>,
    /// 装着的平台版本（这次启动时读到的）
    pub installed: Mutex<Option<Version>>,
    /// 接在 PATH 后面的那一段（Mac 上登录 shell 的），一次运行只取一次
    pub base_path: tokio::sync::OnceCell<Option<OsString>>,
    pub starting: AtomicBool,
    pub quitting: AtomicBool,
}

impl Shell {
    pub fn new<R: Runtime>(
        app: &AppHandle<R>,
        log_path: PathBuf,
        splash_url: Url,
    ) -> tauri::Result<Self> {
        let user_home = app.path().home_dir()?;
        let var = |name: &str| std::env::var_os(name);
        let home = places::home(var, &user_home);
        let cli = places::cli(var, &home);
        let dist = places::dist(var, !tauri::is_dev());
        let tmp = app.path().temp_dir()?.join(&app.config().identifier);
        std::fs::create_dir_all(&tmp)?;
        let version = app.package_info().version.to_string();
        let internet = http::internet(&version).map_err(std::io::Error::other)?;
        let loopback = http::loopback().map_err(std::io::Error::other)?;
        log::info!(
            "shell.start version={version} cli={} from_source={} home={} dist={}",
            cli.path.display(),
            cli.from_source,
            home.display(),
            dist.as_ref().map_or_else(|e| e.clone(), Url::to_string),
        );
        Ok(Self {
            sup: Supervisor::default(),
            splash: Splash::default(),
            gate: Gate::new(&splash_url),
            store: Store::new(&app.path().app_config_dir()?),
            splash_url,
            log_path,
            home,
            cli,
            dist,
            tmp,
            internet,
            loopback,
            serve: Mutex::new(None),
            installed: Mutex::new(None),
            base_path: tokio::sync::OnceCell::new(),
            starting: AtomicBool::new(false),
            quitting: AtomicBool::new(false),
        })
    }

    pub fn serve(&self) -> Option<(Url, Handle)> {
        self.serve.lock().unwrap_or_else(|p| p.into_inner()).clone()
    }

    pub fn quitting(&self) -> bool {
        self.quitting.load(Ordering::SeqCst)
    }

    /// 「打开日志」给人看的两份：外壳的，安装脚本的
    pub fn logs(&self) -> Vec<PathBuf> {
        let install_log = places::install_log(&self.home);
        [self.log_path.clone(), install_log]
            .into_iter()
            .filter(|p| p.exists())
            .collect()
    }
}

/// 外壳自己的版本；占位版本（源码桌面、没注入版本的构建）是 None：它从不更新自己，也不拿它挑平台版本
pub fn own_version<R: Runtime>(app: &AppHandle<R>) -> Option<Version> {
    let raw = app.package_info().version.to_string();
    (raw != "0.0.0")
        .then(|| Version::parse(&raw).ok())
        .flatten()
}

/// 启动页在哪：正式包是 Tauri 的本地协议，源码桌面是 `tauri dev` 起的开发服务器
pub fn splash_url<R: Runtime>(app: &AppHandle<R>) -> Url {
    let base = match (&app.config().build.dev_url, tauri::is_dev()) {
        (Some(dev), true) => dev.clone(),
        _ => Url::parse(if cfg!(windows) {
            "http://tauri.localhost"
        } else {
            "tauri://localhost"
        })
        .expect("写死的地址"),
    };
    base.join("index.html").expect("写死的路径")
}

pub fn log_dir<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<PathBuf> {
    app.path().app_log_dir()
}

pub fn init_log(dir: &Path) -> PathBuf {
    match logfile::init(dir) {
        Ok(path) => path,
        Err(error) => {
            eprintln!("aaai4s: 日志开不了 {}：{error}", dir.display());
            dir.join(logfile::FILE_NAME)
        }
    }
}
