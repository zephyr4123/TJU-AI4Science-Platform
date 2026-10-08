//! 退出（spec §4「退出」）：Mac 的 Cmd+Q 与「退出」菜单、Windows 关窗口、更新器装新版前都走这里。
//!
//! 1. `/health` 的 `turns` 不为 0：先问一句（只防误触，不改退出语义）。
//! 2. 关掉 serve 的标准输入，serve 自己停掉在跑的轮次后退出；同时收掉安装脚本、setup。
//! 3. 5 秒还没退就收拾整棵树（守进程那边：Windows 结束 Job，Mac 先杀后代再杀整组）。
//! 4. 后台作业不受影响：它们生来就不在外壳的 Job、进程组与 serve 的后代里（#284）。
//!
//! 收拾挂在 `RunEvent::Exit` 上：Mac 的 Dock「退出」、注销不经过第 1 步，直接到这里。

use std::sync::atomic::Ordering;

use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_dialog::{DialogExt, MessageDialogBuilder, MessageDialogButtons};
use tokio::sync::oneshot;

use crate::serve;
use crate::shell::{GRACE, Shell};
use crate::window;

/// 系统对话框问一句：点了 `yes` 是 true；`yes` 在确定键（回车）上，Esc、关掉对话框算 `no`
pub async fn ask<R: Runtime>(app: &AppHandle<R>, text: &str, yes: &str, no: &str) -> bool {
    let (tx, rx) = oneshot::channel();
    dialog(app, text)
        .buttons(MessageDialogButtons::OkCancelCustom(
            yes.to_string(),
            no.to_string(),
        ))
        .show(move |answer| {
            let _ = tx.send(answer);
        });
    rx.await.unwrap_or(false)
}

/// 系统对话框说一句（键写「好」：缺省的 OK 在 Mac 上是英文）
pub async fn tell<R: Runtime>(app: &AppHandle<R>, text: &str) {
    let (tx, rx) = oneshot::channel();
    dialog(app, text)
        .buttons(MessageDialogButtons::OkCustom("好".to_string()))
        .show(move |_| {
            let _ = tx.send(());
        });
    let _ = rx.await;
}

/// 对话框挂在主窗口上（Mac 是窗口上的 sheet，Windows 是它的模态框），窗口关着、最小化着先叫回来：问的
/// 总是窗口里的事。不挂的话 Mac 上由系统的 UserNotificationCenter 另起一个浮在所有程序之上的提示，
/// 跟窗口脱节、App 自己的窗口列表里也没有它（端到端撞到的）
fn dialog<R: Runtime>(app: &AppHandle<R>, text: &str) -> MessageDialogBuilder<R> {
    let builder = app.dialog().message(text).title("AAAI4S");
    window::bring_back(app);
    match window::main_window(app) {
        Some(main) => builder.parent(&main),
        None => builder,
    }
}

/// 可以打断吗：没有在跑的轮次，或人点了「仍然退出」
pub async fn may_interrupt<R: Runtime>(app: &AppHandle<R>) -> bool {
    let shell = app.state::<Shell>();
    let Some((url, _)) = shell.serve() else {
        return true;
    };
    match serve::turns(&shell.loopback, &url).await {
        Some(turns) if turns > 0 => {
            log::info!("quit.turns_running turns={turns}");
            // 「仍然退出」在确定键上：Esc、关掉对话框落在取消键，取消该是不退（端到端在 Windows 上按 Esc
            // 就退了、打断了那一轮）
            ask(
                app,
                "助理这一轮还没回完，退出会打断它",
                "仍然退出",
                "等它回完",
            )
            .await
        }
        _ => true,
    }
}

/// 等到没有在跑的轮次（或 serve 不在了、问不到）
pub async fn until_idle<R: Runtime>(app: &AppHandle<R>) {
    const EVERY: std::time::Duration = std::time::Duration::from_secs(3);
    loop {
        let shell = app.state::<Shell>();
        let Some((url, _)) = shell.serve() else {
            return;
        };
        match serve::turns(&shell.loopback, &url).await {
            Some(turns) if turns > 0 => tokio::time::sleep(EVERY).await,
            _ => return,
        }
    }
}

/// 人要退出（菜单、Cmd+Q、Windows 关窗口）：问过了再退
pub fn request<R: Runtime>(app: &AppHandle<R>) {
    let shell = app.state::<Shell>();
    if shell.quitting.swap(true, Ordering::SeqCst) {
        return;
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        if may_interrupt(&app).await {
            log::info!("quit.requested");
            app.exit(0);
        } else {
            app.state::<Shell>().quitting.store(false, Ordering::SeqCst);
        }
    });
}

/// `RunEvent::Exit`：在主线程上同步收拾完再让进程退出
pub fn on_exit<R: Runtime>(app: &AppHandle<R>) {
    let Some(shell) = app.try_state::<Shell>() else {
        return;
    };
    shell.quitting.store(true, Ordering::SeqCst);
    tauri::async_runtime::block_on(shell.sup.shutdown(GRACE));
    log::logger().flush();
}
