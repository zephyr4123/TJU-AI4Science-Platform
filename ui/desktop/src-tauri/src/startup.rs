//! 每次打开走一遍（spec §4「启动」）：查新版本 → 装或升级平台 → setup → 起 serve → 窗口过去 → 查外壳更新。
//!
//! 只有「没有能跑的平台」时才停在启动页（说一句为什么、给「重试」与「打开日志」）；可选的升级、setup
//! 没成都照样往下走，缺什么交给页面设置里的红点，下次打开再补。「重试」就是从头再走一遍：装过的、跑通过
//! setup 的那一版都会跳过，等于从失败的那一步接着来。

use std::ffi::OsString;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::Ordering;

use tauri::{AppHandle, Manager, Runtime};
use url::Url;

use crate::contract::MIN_PLATFORM;
use crate::env::Overlay;
use crate::install::{self, Installed, Target};
use crate::manifest::{self, Manifest};
use crate::places::{self, Cli};
use crate::serve::{self, ServeError};
use crate::shell::{Shell, own_version};
use crate::splash::Problem;
use crate::state::now_secs;
use crate::supervise::Sink;
use crate::update;
use crate::version::Version;

/// 页面要的 WebView2 下限（Tailwind v4 要 Chrome 111+）
pub const WEBVIEW2_MIN: u32 = 111;
/// Mac 上收起后点 Dock 回来，隔了多久才再查一次新版本
#[cfg(target_os = "macos")]
pub const RECHECK_AFTER: std::time::Duration = std::time::Duration::from_secs(24 * 3600);

const BUSY: &str =
    "平台在后台还开着（网页版服务或实验）：关掉网页版服务的窗口，或等实验跑完再点重试";

/// 平台这次怎么办
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Plan {
    Ready,
    /// 装或升级到这一版；`required`：没有能跑的平台或低于 `MIN_PLATFORM`，不装成就停在启动页
    Install {
        version: Version,
        required: bool,
    },
    /// 必须装、却不知道装哪一版（清单取不到，外壳也不是预发布）
    NoTarget,
}

/// spec §4 第 5 步。必须装时目标版本：外壳自己是预发布就装自己那一版（rc 期间清单不动），否则装清单
/// 的；可选的升级只升到清单的版本、只往高处升
pub fn plan(
    installed: Option<&Version>,
    latest: Option<&Version>,
    shell: Option<&Version>,
    floor: &Version,
) -> Plan {
    match installed.filter(|v| v.meets(floor)) {
        None => match shell.filter(|v| v.is_prerelease()).or(latest) {
            Some(version) => Plan::Install {
                version: version.clone(),
                required: true,
            },
            None => Plan::NoTarget,
        },
        Some(have) => match latest {
            Some(latest) if latest > have => Plan::Install {
                version: latest.clone(),
                required: false,
            },
            _ => Plan::Ready,
        },
    }
}

/// 外壳低于后端要的最低外壳版本（占位版本的外壳不算：它从不更新自己）
pub fn shell_too_old(shell: Option<&Version>, manifest: Option<&Manifest>) -> bool {
    matches!((shell, manifest), (Some(me), Some(m)) if !me.meets(&m.min_desktop))
}

/// Windows 上 WebView2 的大版本号低于下限
pub fn webview_too_old(version: &str) -> Option<u32> {
    let major = version.split('.').next()?.trim().parse::<u32>().ok()?;
    (major < WEBVIEW2_MIN).then_some(major)
}

/// 起一遍启动（已经在走就不再起）
pub fn kick<R: Runtime>(app: &AppHandle<R>) {
    let shell = app.state::<Shell>();
    if shell.quitting() || shell.starting.swap(true, Ordering::SeqCst) {
        return;
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let shell = app.state::<Shell>();
        shell.splash.begin("正在打开");
        if let Err(problem) = sequence(&app, &shell).await
            && !shell.quitting()
        {
            shell.splash.problem(problem);
        }
        shell.starting.store(false, Ordering::SeqCst);
    });
}

/// 打开之前就该停下的：从 DMG 里跑（Mac）、WebView2 太旧（Windows）
fn blocked() -> Option<Problem> {
    if cfg!(target_os = "macos")
        && let Ok(exe) = tauri::utils::platform::current_exe()
        && places::translocated(&exe)
    {
        return Some(Problem::fatal("先把 AAAI4S 拖进『应用程序』再打开"));
    }
    if cfg!(windows)
        && let Ok(version) = tauri::webview_version()
        && let Some(major) = webview_too_old(&version)
    {
        return Some(Problem {
            text: format!("WebView2 是 {major}，页面要 {WEBVIEW2_MIN} 以上：装上微软的新版再打开"),
            retry: false,
            webview2: true,
        });
    }
    None
}

async fn fetch_manifest(shell: &Shell, pubkey: &str) -> Option<Manifest> {
    let dist = shell.dist.as_ref().ok()?;
    let seen = seen_manifest(shell.store.load().newest_manifest.as_deref(), dist);
    let fetched = manifest::fetch(&shell.internet, dist, pubkey)
        .await
        .and_then(|m| manifest::latest_ok(&m, seen.as_ref()).map(|()| m));
    match fetched {
        Ok(manifest) => {
            if seen.as_ref() < Some(&manifest.version) {
                let mark = format!("{} {dist}", manifest.version);
                shell.store.update(|r| r.newest_manifest = Some(mark));
            }
            log::info!(
                "manifest.ok version={} min_desktop={}",
                manifest.version,
                manifest.min_desktop
            );
            Some(manifest)
        }
        Err(reason) => {
            log::warn!("manifest.unavailable reason={reason}");
            None
        }
    }
}

/// 这个发布地址上见过的最新清单的版本（换了 `AI4SCI_DIST` 不算）
pub fn seen_manifest(recorded: Option<&str>, dist: &Url) -> Option<Version> {
    let (version, at) = recorded?.split_once(' ')?;
    (at == dist.as_str())
        .then(|| Version::parse(version).ok())
        .flatten()
}

/// 更新器那把公钥：清单与外壳更新同一把，只在 tauri.conf.json 一处
pub fn updater_pubkey<R: Runtime>(app: &AppHandle<R>) -> String {
    let plugins = &app.config().plugins.0;
    plugins
        .get("updater")
        .and_then(|u| u.get("pubkey"))
        .and_then(|k| k.as_str())
        .unwrap_or_default()
        .to_string()
}

/// 接在 PATH 后面的那一段：Mac 上是用户登录 shell 的（这次 3 秒内没取到就用上次记下的），都没有用继承的
async fn base_path(shell: &Shell) -> Option<OsString> {
    shell
        .base_path
        .get_or_init(|| async {
            #[cfg(target_os = "macos")]
            {
                use crate::env::{LOGIN_SHELL_TIMEOUT, login_path};
                let login = std::env::var_os("SHELL")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| PathBuf::from("/bin/zsh"));
                if let Some(path) = login_path(&login, LOGIN_SHELL_TIMEOUT).await {
                    shell.store.update(|r| r.login_path = Some(path.clone()));
                    return Some(OsString::from(path));
                }
                if let Some(path) = shell.store.load().login_path {
                    log::info!("login_path.cached len={}", path.len());
                    return Some(OsString::from(path));
                }
            }
            std::env::var_os("PATH")
        })
        .await
        .clone()
}

/// 子进程的那一行行输出：写日志的是守进程那边，这里只把进度行交给启动页
fn to_splash<R: Runtime>(app: &AppHandle<R>) -> Sink {
    let app = app.clone();
    Arc::new(move |_, _, line| app.state::<Shell>().splash.line(line))
}

async fn sequence<R: Runtime>(app: &AppHandle<R>, shell: &Shell) -> Result<(), Problem> {
    if let Some(problem) = blocked() {
        return Err(problem);
    }
    // 3. 签名的清单（与取登录 shell 的 PATH 同时做）
    shell.splash.status("查新版本");
    let pubkey = updater_pubkey(app);
    let (manifest, rest) = tokio::join!(fetch_manifest(shell, &pubkey), base_path(shell));
    if manifest.is_some() {
        shell.store.update(|r| r.checked_at = Some(now_secs())); // 没取到不算查过
    }
    let me = own_version(app);
    let mut latest = manifest.as_ref();
    let too_old = shell_too_old(me.as_ref(), latest);
    if too_old {
        // 外壳低于后端要的：先更新外壳，后端不动；装上了就重启，不会回到这里
        shell.splash.status("先更新桌面 App");
        if let Err(reason) = update::install_now(app).await {
            log::warn!("update.required_failed reason={reason}");
        }
        latest = None;
    }
    let cli = shell.cli.clone();
    let (for_install, overlay) = overlays(&cli, rest, std::env::var_os("LANG").is_some());
    if !cli.from_source {
        let (installed, fresh) =
            prepare_platform(app, shell, &for_install, latest, me.as_ref(), too_old).await?;
        // 6. 这个家、这一版平台还没跑通过 setup，或者这次刚装过，就跑一次；没跑通照样往下走，下次再跑
        let mark = setup_mark(&installed, &shell.home);
        if needs_setup(shell.store.load().setup_ok.as_deref(), &mark, fresh) {
            shell.splash.status("准备 Git、Claude Code 与 Codex");
            if install::setup(&shell.sup, &cli.path, &overlay, &shell.tmp, to_splash(app)).await {
                shell.store.update(|r| r.setup_ok = Some(mark));
            } else {
                log::warn!("setup.incomplete version={installed}");
            }
        }
    }
    // 7. 起 serve，窗口过去
    shell.splash.status("正在启动");
    let url = start_serve(app, shell, &cli.path, overlay).await?;
    crate::window::show_backend(app, &url);
    // 8. serve 起来以后再查外壳更新；装、升级的过程中不弹
    if !too_old {
        let app = app.clone();
        tauri::async_runtime::spawn(async move { update::offer(&app).await });
    }
    Ok(())
}

/// 装平台那一次与其余（setup、serve、`--version`）的环境。装平台那次 PATH 里不放 `ai4sci` 所在的
/// 目录：install.sh 看 PATH 里已经有家里的 bin 就不往 shell 配置里写那一行，终端里就找不到 `ai4sci`
pub fn overlays(cli: &Cli, rest: Option<OsString>, has_lang: bool) -> (Overlay, Overlay) {
    let front: Vec<PathBuf> = cli
        .path
        .parent()
        .map(|d| vec![d.to_path_buf()])
        .unwrap_or_default();
    (
        Overlay::new(&[], rest.clone(), has_lang),
        Overlay::new(&front, rest, has_lang),
    )
}

/// 跑通过 setup 记的是「哪一版、哪个家」：换了家（`AI4SCI_HOME`）也要再跑
pub fn setup_mark(version: &Version, home: &std::path::Path) -> String {
    format!("{version} {}", home.display())
}

/// 这次刚装过平台就一律再跑：删掉家重装同一版，记下的还是那一版，可家里的 CLI 与 Git 已经没了
pub fn needs_setup(recorded: Option<&str>, mark: &str, fresh: bool) -> bool {
    fresh || recorded != Some(mark)
}

/// 第 5 步：装着的能跑就用，不能跑就装，有新版就升；返回这次用的平台版本、这次装过没有
async fn prepare_platform<R: Runtime>(
    app: &AppHandle<R>,
    shell: &Shell,
    overlay: &Overlay,
    latest: Option<&Manifest>,
    me: Option<&Version>,
    too_old: bool,
) -> Result<(Version, bool), Problem> {
    let floor = Version::parse(MIN_PLATFORM).expect("MIN_PLATFORM 是合法的版本");
    let installed =
        install::installed_version(&shell.sup, &shell.cli.path, overlay, &shell.tmp).await;
    let decided = plan(installed.as_ref(), latest.map(|m| &m.version), me, &floor);
    log::info!("platform.plan installed={installed:?} plan={decided:?}");
    let (version, required) = match decided {
        Plan::Ready => return kept(shell, installed),
        Plan::NoTarget if too_old => {
            return Err(Problem::retry(
                "桌面 App 要先更新到新版，更新没装上：连上网再点重试",
            ));
        }
        Plan::NoTarget => return Err(Problem::retry("取不到平台的最新版本：连上网再点重试")),
        Plan::Install { version, required } => (version, required),
    };
    let dist = match &shell.dist {
        Ok(dist) => dist,
        Err(reason) if required => return Err(Problem::retry(reason.clone())),
        Err(_) => return kept(shell, installed),
    };
    // 只跑签过的脚本：最新的那份就是这一版就用它，否则（预发布的外壳装自己那一版）取这一版自己那份
    let target = match latest {
        Some(m) if m.version == version => Target::signed(m),
        _ => match manifest::fetch_version(&shell.internet, dist, &version, &updater_pubkey(app))
            .await
        {
            Ok(m) => Target::signed(&m),
            Err(reason) if required => {
                return Err(Problem::retry(format!(
                    "取不到 {version} 的签名清单：{reason}"
                )));
            }
            Err(reason) => {
                log::warn!("platform.upgrade_skipped reason={reason}");
                return kept(shell, installed);
            }
        },
    };
    shell.splash.status(&match &installed {
        None => "第一次打开：装平台".to_string(),
        Some(_) => format!("升级平台到 {version}"),
    });
    let outcome = install::platform(
        &shell.sup,
        &shell.internet,
        dist,
        &target,
        overlay,
        places::sidecar_dir().as_deref(),
        &shell.tmp,
        to_splash(app),
    )
    .await;
    match (outcome, required) {
        (Installed::Done, _) => {
            let now =
                install::installed_version(&shell.sup, &shell.cli.path, overlay, &shell.tmp).await;
            let usable = match now.filter(|v| v.meets(&floor)) {
                Some(now) => remember(shell, Some(now)),
                None if required => Err(Problem::retry("装完还是跑不起来：点重试，或打开日志看看")),
                None => remember(shell, installed),
            };
            usable.map(|version| (version, true))
        }
        (Installed::Busy, true) => Err(Problem::retry(BUSY)),
        (Installed::Failed(why), true) => Err(Problem::retry(format!("平台没装上：{why}"))),
        // 可选的升级没成：这次照用旧版
        (outcome, false) => {
            log::warn!("platform.upgrade_skipped outcome={outcome:?}");
            kept(shell, installed)
        }
    }
}

/// 这次没装：照用装着的
fn kept(shell: &Shell, installed: Option<Version>) -> Result<(Version, bool), Problem> {
    remember(shell, installed).map(|version| (version, false))
}

fn remember(shell: &Shell, installed: Option<Version>) -> Result<Version, Problem> {
    let version = installed.ok_or_else(|| Problem::retry("没有能跑的平台：点重试"))?;
    *shell.installed.lock().unwrap_or_else(|p| p.into_inner()) = Some(version.clone());
    Ok(version)
}

/// 第 7 步：端口优先用上次记下的；第一次、或 serve 说端口用不了，让系统给一个空闲端口（`--port 0`）。
/// 换的端口只用这一次，记下的不改：页面的主题按端口存在 localStorage
async fn start_serve<R: Runtime>(
    app: &AppHandle<R>,
    shell: &Shell,
    cli: &std::path::Path,
    overlay: Overlay,
) -> Result<Url, Problem> {
    let preferred = shell.store.load().port;
    let first = serve::start(
        &shell.sup,
        cli,
        preferred.unwrap_or(0),
        overlay.clone(),
        &shell.tmp,
        to_splash(app),
    )
    .await;
    let running = match first {
        Err(ServeError::PortBusy) if preferred.is_some() => {
            log::warn!("serve.port_busy port={preferred:?} fallback=os");
            serve::start(&shell.sup, cli, 0, overlay, &shell.tmp, to_splash(app)).await
        }
        other => other,
    }
    .map_err(|error| Problem::retry(format!("服务没起来：{error}")))?;
    if preferred.is_none() {
        let port = running.url.port();
        shell.store.update(|r| r.port = port);
    }
    *shell.serve.lock().unwrap_or_else(|p| p.into_inner()) =
        Some((running.url.clone(), running.serve.clone()));
    watch_serve(app, running.url.clone(), running.serve);
    Ok(running.url)
}

/// 第 9 步：serve 中途退出，窗口回到启动页显示出错、给「重试」。它留下的：Windows 上随它的 Job 一起收掉
/// 了（守进程那边），Mac 上自成会话的轮次由下一个 serve 启动时按登记清掉（#285）
fn watch_serve<R: Runtime>(app: &AppHandle<R>, url: Url, serve: crate::supervise::Handle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let exit = serve.wait().await;
        let shell = app.state::<Shell>();
        let current = {
            let mut slot = shell.serve.lock().unwrap_or_else(|p| p.into_inner());
            let current = slot.as_ref().is_some_and(|(u, _)| *u == url);
            if current {
                *slot = None;
            }
            current
        };
        if !current || shell.quitting() {
            return;
        }
        log::warn!("serve.died url={url} code={:?}", exit.code);
        shell.splash.begin("服务停了");
        shell.splash.problem(Problem::retry("服务停了：点重试"));
        crate::window::show_splash(&app);
    });
}

/// Mac 上收起后点 Dock 回来（spec §4 第 10 步）：隔了一天、又没有在跑的轮次，再查一遍新版本；
/// 有要装的就回启动页、停掉 serve、从头走一遍
#[cfg(target_os = "macos")]
pub async fn recheck<R: Runtime>(app: &AppHandle<R>) {
    let shell = app.state::<Shell>();
    let last = shell.store.load().checked_at.unwrap_or(0);
    if now_secs().saturating_sub(last) < RECHECK_AFTER.as_secs()
        || shell.starting.load(Ordering::SeqCst)
    {
        return;
    }
    let Some((url, serve)) = shell.serve() else {
        return;
    };
    if serve::turns(&shell.loopback, &url).await != Some(0) {
        return; // 有在跑的轮次，或问不到：这次不动
    }
    let Some(manifest) = fetch_manifest(&shell, &updater_pubkey(app)).await else {
        return; // 没取到不算查过，下次点回来再查
    };
    shell.store.update(|r| r.checked_at = Some(now_secs()));
    let manifest = Some(manifest);
    let installed = shell
        .installed
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .clone();
    let me = own_version(app);
    let floor = Version::parse(MIN_PLATFORM).expect("MIN_PLATFORM 是合法的版本");
    let newer = !shell.cli.from_source
        && matches!(
            plan(
                installed.as_ref(),
                manifest.as_ref().map(|m| &m.version),
                me.as_ref(),
                &floor
            ),
            Plan::Install { .. }
        );
    if !newer && !shell_too_old(me.as_ref(), manifest.as_ref()) {
        return;
    }
    // 取清单的这几秒里可能又开了一轮：停 serve 前再问一次
    if serve::turns(&shell.loopback, &url).await != Some(0) {
        return;
    }
    log::info!("recheck.restart");
    *shell.serve.lock().unwrap_or_else(|p| p.into_inner()) = None;
    shell.splash.begin("正在更新");
    crate::window::show_splash(app);
    shell.sup.stop(&serve, crate::shell::GRACE).await;
    kick(app);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(raw: &str) -> Version {
        Version::parse(raw).unwrap()
    }

    #[test]
    fn nothing_runnable_installs_the_latest_or_the_shells_own_prerelease() {
        let floor = v("1.9.0");
        let latest = v("1.9.2");
        assert_eq!(
            plan(None, Some(&latest), Some(&v("1.9.1")), &floor),
            Plan::Install {
                version: v("1.9.2"),
                required: true
            }
        );
        assert_eq!(
            plan(None, Some(&latest), Some(&v("1.10.0-rc.1")), &floor),
            Plan::Install {
                version: v("1.10.0rc1"),
                required: true
            }
        );
        assert_eq!(
            plan(Some(&v("1.8.0")), Some(&latest), None, &floor),
            Plan::Install {
                version: v("1.9.2"),
                required: true
            }
        );
        assert_eq!(plan(None, None, Some(&v("1.9.1")), &floor), Plan::NoTarget);
        assert_eq!(plan(None, None, None, &floor), Plan::NoTarget);
    }

    #[test]
    fn a_runnable_platform_is_upgraded_only_upwards_and_only_if_it_can_be() {
        let floor = v("1.9.0");
        assert_eq!(
            plan(Some(&v("1.9.0")), Some(&v("1.9.2")), None, &floor),
            Plan::Install {
                version: v("1.9.2"),
                required: false
            }
        );
        assert_eq!(
            plan(Some(&v("1.9.2")), Some(&v("1.9.2")), None, &floor),
            Plan::Ready
        );
        assert_eq!(
            plan(Some(&v("1.9.3")), Some(&v("1.9.2")), None, &floor),
            Plan::Ready,
            "清单比装着的旧：不降"
        );
        assert_eq!(
            plan(Some(&v("1.9.0rc1")), None, None, &floor),
            Plan::Ready,
            "同号的 rc 满足下限"
        );
        assert_eq!(
            plan(Some(&v("1.9.0rc1")), Some(&v("1.9.0")), None, &floor),
            Plan::Install {
                version: v("1.9.0"),
                required: false
            }
        );
    }

    #[test]
    fn the_shell_updates_itself_first_only_when_the_backend_asks_for_it() {
        let manifest = |min: &str| Manifest {
            version: v("1.9.0"),
            min_desktop: v(min),
            install_sh: String::new(),
            install_ps1: String::new(),
            wheel: String::new(),
        };
        assert!(shell_too_old(Some(&v("1.9.0")), Some(&manifest("1.9.1"))));
        assert!(!shell_too_old(
            Some(&v("1.9.1-rc.1")),
            Some(&manifest("1.9.1"))
        ));
        assert!(
            !shell_too_old(None, Some(&manifest("9.9.9"))),
            "占位版本的外壳从不更新自己"
        );
        assert!(!shell_too_old(Some(&v("1.9.0")), None));
    }

    #[test]
    fn setup_runs_again_for_a_new_home_and_after_any_install() {
        let mark = setup_mark(&v("1.9.0"), std::path::Path::new("/h/.ai4sci"));
        assert!(needs_setup(None, &mark, false), "没跑通过");
        assert!(
            !needs_setup(Some(&mark), &mark, false),
            "这个家这一版跑通过"
        );
        assert!(
            needs_setup(Some(&mark), &mark, true),
            "删掉家重装同一版：记下的一样，可 CLI 已经没了"
        );
        let other = setup_mark(&v("1.9.0"), std::path::Path::new("/elsewhere"));
        assert!(needs_setup(Some(&mark), &other, false), "换了家");
        assert!(
            needs_setup(Some("1.9.0"), &mark, false),
            "旧格式（只有版本）当没跑过"
        );
    }

    #[test]
    fn installing_the_platform_does_not_see_the_cli_on_path() {
        let cli = Cli {
            path: PathBuf::from("/h/.ai4sci/bin/ai4sci"),
            from_source: false,
        };
        let path_of = |o: &Overlay| {
            let (_, path) = o.set.iter().find(|(k, _)| k == "PATH").unwrap();
            std::env::split_paths(path).collect::<Vec<_>>()
        };
        let (install, rest) = overlays(&cli, Some(OsString::from("/usr/bin")), true);
        assert_eq!(path_of(&install), vec![PathBuf::from("/usr/bin")]);
        assert_eq!(
            path_of(&rest),
            vec![PathBuf::from("/h/.ai4sci/bin"), PathBuf::from("/usr/bin")]
        );
    }

    #[test]
    fn the_newest_manifest_seen_is_kept_per_dist() {
        let dist = Url::parse("https://cdn.example/dist/").unwrap();
        let other = Url::parse("file:///tmp/dist/").unwrap();
        let mark = format!("1.9.2 {dist}");
        assert_eq!(seen_manifest(Some(&mark), &dist), Some(v("1.9.2")));
        assert_eq!(seen_manifest(Some(&mark), &other), None);
        assert_eq!(seen_manifest(None, &dist), None);
        assert_eq!(seen_manifest(Some("garbage"), &dist), None);
    }

    #[test]
    fn webview2_below_111_cannot_draw_the_page() {
        assert_eq!(webview_too_old("110.0.1587.69"), Some(110));
        assert_eq!(webview_too_old("154.0.4258.53"), None);
        assert_eq!(webview_too_old("not a version"), None);
    }
}
