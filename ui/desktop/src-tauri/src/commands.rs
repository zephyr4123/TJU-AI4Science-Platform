//! 启动页能调的外壳命令：只有这四条，只给本地的启动页（`capabilities/splash.json`）。
//! 一条都不收 JS 传来的路径或 URL：要开哪个文件、哪个地址都在这边写死。

use tauri::ipc::Channel;
use tauri::{AppHandle, Runtime, State};

use crate::shell::Shell;
use crate::splash::Event;
use crate::startup;

/// 微软的 WebView2 常青版引导程序（国内能下，测试机实测）
const WEBVIEW2_BOOTSTRAPPER: &str = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";

/// 启动页载入：收这一屏的全貌，之后收增量
#[tauri::command]
pub fn attach(shell: State<'_, Shell>, on_event: Channel<Event>) {
    log::info!("splash.attach");
    shell.splash.attach(on_event);
}

/// 「重试」：出了能重试的错才从头走一遍
#[tauri::command]
pub fn retry<R: Runtime>(app: AppHandle<R>, shell: State<'_, Shell>) {
    if shell.splash.retryable() {
        log::info!("splash.retry");
        startup::kick(&app);
    }
}

/// 「打开日志」：在访达 / 资源管理器里显示外壳的日志与安装脚本的日志
#[tauri::command]
pub fn open_log(shell: State<'_, Shell>) {
    for path in shell.logs() {
        if let Err(error) = tauri_plugin_opener::reveal_item_in_dir(&path) {
            log::warn!("splash.open_log_failed error={error}");
        }
    }
}

/// 「下载 WebView2」
#[tauri::command]
pub fn open_webview2_download() {
    if let Err(error) = tauri_plugin_opener::open_url(WEBVIEW2_BOOTSTRAPPER, None::<&str>) {
        log::warn!("splash.open_webview2_failed error={error}");
    }
}
