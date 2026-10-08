//! 那一个窗口（spec §1、§4）：先显示启动页，serve 起来后导航到它的地址；外链交给系统、下载落「下载」目录。
//!
//! 窗口不在配置里自动建（`create: false`）：这里照配置建，才挂得上导航、新窗口、下载的钩子（页面载入只记日志）。
//! Mac 上关窗口只是收起（App 还在 Dock 里、服务照开），点 Dock 回来；Windows 上关窗口就是退出。

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use tauri::webview::{DownloadEvent, NewWindowResponse};
use tauri::{
    AppHandle, Manager, Runtime, WebviewWindow, WebviewWindowBuilder, Window, WindowEvent,
};
use url::Url;

use crate::nav::{self, Verdict};
use crate::quit;
use crate::shell::Shell;

pub const MAIN: &str = "main";

pub fn create<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<WebviewWindow<R>> {
    let config = app
        .config()
        .app
        .windows
        .iter()
        .find(|w| w.label == MAIN)
        .cloned();
    let config = config.ok_or_else(|| std::io::Error::other("tauri.conf.json 里没有 main 窗口"))?;
    let (nav_app, popup_app, download_app) = (app.clone(), app.clone(), app.clone());
    let pending = Arc::new(Mutex::new(HashMap::<String, PathBuf>::new()));
    let window = WebviewWindowBuilder::from_config(app, &config)?
        .on_navigation(move |url| judge(&nav_app, url, false))
        .on_new_window(move |url, _| {
            judge(&popup_app, &url, true);
            NewWindowResponse::Deny
        })
        .on_download(move |_, event| download(&download_app, &pending, event))
        .on_page_load(|_, payload| {
            let url = payload.url();
            log::info!(
                "window.page_load event={:?} origin={}://{}",
                payload.event(),
                url.scheme(),
                url.host_str().unwrap_or("-")
            );
        })
        .build()?;
    window.show()?;
    Ok(window)
}

fn judge<R: Runtime>(app: &AppHandle<R>, url: &Url, new_window: bool) -> bool {
    let gate = &app.state::<Shell>().gate;
    let verdict = if new_window {
        gate.new_window(url)
    } else {
        gate.navigation(url)
    };
    match verdict {
        Verdict::Allow => {
            log::info!(
                "nav.allow scheme={} host={}",
                url.scheme(),
                url.host_str().unwrap_or("-")
            );
            true
        }
        Verdict::External => {
            log::info!("nav.external scheme={}", url.scheme());
            if let Err(error) = tauri_plugin_opener::open_url(url.as_str(), None::<&str>) {
                log::warn!("nav.open_failed scheme={} error={error}", url.scheme());
            }
            false
        }
        Verdict::Deny => {
            log::warn!("nav.denied scheme={}", url.scheme());
            false
        }
    }
}

/// 下载：开始时定好「下载」目录里不重名的位置（Mac 上下完的事件里没有路径，只能自己记着），下完在访达 /
/// 资源管理器里显示
fn download<R: Runtime>(
    app: &AppHandle<R>,
    pending: &Mutex<HashMap<String, PathBuf>>,
    event: DownloadEvent<'_>,
) -> bool {
    let mut pending = pending.lock().unwrap_or_else(|p| p.into_inner());
    match event {
        DownloadEvent::Requested { url, destination } => {
            let Ok(dir) = app.path().download_dir() else {
                log::warn!("download.no_folder");
                return false;
            };
            let suggested = destination
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            let target = nav::download_target(&dir, &suggested);
            log::info!(
                "download.start file={}",
                target.file_name().unwrap_or_default().to_string_lossy()
            );
            *destination = target.clone();
            pending.insert(url.to_string(), target);
            true
        }
        DownloadEvent::Finished { url, path, success } => {
            let target = pending.remove(url.as_str()).or(path);
            match (success, target) {
                (true, Some(target)) => {
                    if let Err(error) = tauri_plugin_opener::reveal_item_in_dir(&target) {
                        log::warn!("download.reveal_failed error={error}");
                    }
                }
                (success, _) => log::warn!("download.finished success={success}"),
            }
            true
        }
        _ => true,
    }
}

pub fn main_window<R: Runtime>(app: &AppHandle<R>) -> Option<WebviewWindow<R>> {
    app.get_webview_window(MAIN)
}

/// serve 起来了：窗口过去，启动页不再收进度
pub fn show_backend<R: Runtime>(app: &AppHandle<R>, url: &Url) {
    let shell = app.state::<Shell>();
    shell.gate.open_backend(url);
    shell.splash.detach();
    if let Some(window) = main_window(app)
        && let Err(error) = window.navigate(url.clone())
    {
        log::warn!("window.navigate_failed error={error}");
    }
}

/// 回启动页：只放行外壳自己发起的这一次
pub fn show_splash<R: Runtime>(app: &AppHandle<R>) {
    let shell = app.state::<Shell>();
    shell.gate.back_to_splash();
    if let Some(window) = main_window(app)
        && let Err(error) = window.navigate(shell.splash_url.clone())
    {
        log::warn!("window.navigate_failed error={error}");
    }
}

/// 第二次打开、点 Dock：把已有的窗口拉到前面
pub fn bring_back<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = main_window(app) {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

pub fn on_event<R: Runtime>(window: &Window<R>, event: &WindowEvent) {
    if let WindowEvent::CloseRequested { api, .. } = event {
        api.prevent_close();
        if cfg!(target_os = "macos") {
            let _ = window.hide();
        } else {
            quit::request(window.app_handle());
        }
    }
}

/// Mac 上收起后点 Dock、在「应用程序」里再双击：系统不起第二个进程，只发 Reopen
#[cfg(target_os = "macos")]
pub fn reopen<R: Runtime>(app: &AppHandle<R>) {
    bring_back(app);
    let app = app.clone();
    tauri::async_runtime::spawn(async move { crate::startup::recheck(&app).await });
}

/// Mac 的菜单：系统的「编辑」得留着（不然 Cmd+V 粘贴不了 key）；「退出」换成自己的那一项、保留 Cmd+Q，
/// 退出前才问得了那一句
#[cfg(target_os = "macos")]
pub fn mac_menu<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<tauri::menu::Menu<R>> {
    use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu, WINDOW_SUBMENU_ID};

    let name = app.package_info().name.clone();
    let quit = MenuItem::with_id(
        app,
        QUIT_ID,
        format!("退出 {name}"),
        true,
        Some("CmdOrCtrl+Q"),
    )?;
    let app_menu = Submenu::with_items(
        app,
        &name,
        true,
        &[
            &PredefinedMenuItem::about(app, Some(&format!("关于 {name}")), None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::hide(app, Some(&format!("隐藏 {name}")))?,
            &PredefinedMenuItem::hide_others(app, Some("隐藏其他"))?,
            &PredefinedMenuItem::show_all(app, Some("全部显示"))?,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;
    let edit = Submenu::with_items(
        app,
        "编辑",
        true,
        &[
            &PredefinedMenuItem::undo(app, Some("撤销"))?,
            &PredefinedMenuItem::redo(app, Some("重做"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, Some("剪切"))?,
            &PredefinedMenuItem::copy(app, Some("拷贝"))?,
            &PredefinedMenuItem::paste(app, Some("粘贴"))?,
            &PredefinedMenuItem::select_all(app, Some("全选"))?,
        ],
    )?;
    let window = Submenu::with_id_and_items(
        app,
        WINDOW_SUBMENU_ID,
        "窗口",
        true,
        &[
            &PredefinedMenuItem::minimize(app, Some("最小化"))?,
            &PredefinedMenuItem::maximize(app, Some("缩放"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::close_window(app, Some("关闭窗口"))?,
        ],
    )?;
    Menu::with_items(app, &[&app_menu, &edit, &window])
}

#[cfg(target_os = "macos")]
pub const QUIT_ID: &str = "quit";
