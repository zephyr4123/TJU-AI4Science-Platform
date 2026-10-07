//! 外壳自己的更新（spec §4 第 3、8 步，ADR-0005）：Tauri 的更新器读 `<DIST>/desktop/latest.json`，签名必须
//! 带版本号（`requireSignedVersion`），公钥只在 tauri.conf.json 一处。
//!
//! 两种时机：后端要的最低外壳版本比自己高（启动页上直接更新，后端不动）；serve 起来以后查到新版，弹系统
//! 对话框问一句。装新版前走退出那一套：有在跑的轮次先问、停 serve、收拾子进程；Windows 上更新器装完就
//! `process::exit`，不发 `RunEvent::Exit`，所以它的 `on_before_exit` 里要自己收拾、自己 `cleanup_before_exit`。

use std::sync::atomic::Ordering;

use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::progress::Row;
use crate::quit;
use crate::shell::{GRACE, Shell, own_version};

async fn check<R: Runtime>(app: &AppHandle<R>) -> Result<Option<Update>, String> {
    if own_version(app).is_none() {
        return Ok(None); // 占位版本（源码桌面）从不更新自己
    }
    let handle = app.clone();
    let updater = app
        .updater_builder()
        .on_before_exit(move || {
            handle.state::<Shell>().sup.kill_all_now();
            handle.cleanup_before_exit();
        })
        .build()
        .map_err(|error| error.to_string())?;
    updater.check().await.map_err(|error| error.to_string())
}

/// 下载好的新版装上并重启（Windows 上装的时候外壳就退出了，不会回来）
async fn install<R: Runtime>(
    app: &AppHandle<R>,
    update: Update,
    bytes: Vec<u8>,
) -> Result<(), String> {
    let shell = app.state::<Shell>();
    shell.quitting.store(true, Ordering::SeqCst);
    shell.sup.shutdown(GRACE).await;
    log::info!("update.install version={}", update.version);
    if let Err(error) = update.install(bytes) {
        shell.sup.reopen();
        shell.quitting.store(false, Ordering::SeqCst);
        // Windows 上 on_before_exit 已经把窗口藏了，安装器却没起来（被杀毒软件拦下这类）：窗口拿回来
        crate::window::bring_back(app);
        return Err(error.to_string());
    }
    app.request_restart();
    Ok(())
}

/// 后端要求更新外壳：在启动页上下载、装、重启；没有新版或没成是 Err（后端不动，照用装着的）
pub async fn install_now<R: Runtime>(app: &AppHandle<R>) -> Result<(), String> {
    let update = check(app).await?.ok_or("没有可用的新版")?;
    let shell = app.state::<Shell>();
    let mut got = 0usize;
    let bytes = update
        .download(
            |chunk, total| {
                got += chunk;
                let note = match total {
                    Some(total) => format!("已下 {} MB / 共 {} MB", got >> 20, total >> 20),
                    None => format!("已下 {} MB", got >> 20),
                };
                shell.splash.row(Row {
                    mark: "↓".into(),
                    label: "AAAI4S".into(),
                    note,
                });
            },
            || {},
        )
        .await
        .map_err(|error| error.to_string())?;
    shell.splash.row(Row {
        mark: "✓".into(),
        label: "AAAI4S".into(),
        note: format!("{}，下载完成", update.version),
    });
    install(app, update, bytes).await
}

/// serve 起来以后：有新版就问「现在更新？」；点了就下载，装之前再过退出前那一问（下载的这几分钟里可能
/// 又开了一轮），点了「等它回完」就等这一轮回完再装
pub async fn offer<R: Runtime>(app: &AppHandle<R>) {
    let update = match check(app).await {
        Ok(Some(update)) => update,
        Ok(None) => return,
        Err(reason) => {
            log::warn!("update.check_failed reason={reason}");
            return;
        }
    };
    log::info!("update.available version={}", update.version);
    let text = format!("桌面 App 有新版本 {}：现在更新？", update.version);
    if !quit::ask(app, &text, "现在更新", "以后再说").await {
        return;
    }
    let bytes = match update.download(|_, _| {}, || {}).await {
        Ok(bytes) => bytes,
        Err(error) => {
            log::warn!("update.download_failed error={error}");
            quit::tell(app, download_failed(&error)).await;
            return;
        }
    };
    while !quit::may_interrupt(app).await {
        quit::until_idle(app).await;
    }
    let shell = app.state::<Shell>();
    shell.splash.begin("正在更新桌面 App");
    crate::window::show_splash(app);
    if let Err(reason) = install(app, update, bytes).await {
        log::warn!("update.install_failed reason={reason}");
        quit::tell(app, "新版没装上，下次打开再更新").await;
        // serve 已经停了：从头起一遍
        crate::startup::kick(app);
    }
}

/// 新版的包与签名对不上（改过一个字节、换过一把 key、签的不是这一版）：下次打开还是同一个包，不说「下次再更新」
const SIGNATURE_MISMATCH: &str = "新版的包与签名对不上，没有装，先照旧用这一版";

/// 下载失败时对人说的那句
fn download_failed(error: &tauri_plugin_updater::Error) -> &'static str {
    use tauri_plugin_updater::Error;
    match error {
        Error::Minisign(_)
        | Error::SignatureUtf8(_)
        | Error::SignedVersionMismatch { .. }
        | Error::MissingSignedVersion => SIGNATURE_MISMATCH,
        _ => "新版没下载完，下次打开再更新",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tauri_plugin_updater::Error;

    #[test]
    fn a_package_that_does_not_match_its_signature_is_not_called_unfinished() {
        // 端到端：包改了一个字节、换了一把 key，以前都说「没下载完，下次打开再更新」——下次还是同一个坏包
        let signed = [
            Error::MissingSignedVersion,
            Error::SignedVersionMismatch {
                signed: "9.0.1".into(),
                announced: "9.0.2".into(),
            },
        ];
        for error in &signed {
            assert_eq!(download_failed(error), SIGNATURE_MISMATCH, "{error}");
        }
        let cut = Error::Network("connection reset".into());
        assert_eq!(download_failed(&cut), "新版没下载完，下次打开再更新");
    }
}
