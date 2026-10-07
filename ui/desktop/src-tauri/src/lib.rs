//! AAAI4S 桌面 App 的外壳（外层 #282，spec docs/specs/desktop.md）：一个窗口套在 `ai4sci serve` 外面，
//! 不另起后端。外壳只依赖 `contract.rs` 里的后端约定，不认识框架内部。
//!
//! 模块分两层：不认识 Tauri 的（约定、版本、清单、环境、守进程、serve、装与 setup、导航、进度、外壳
//! 自己记的状态、日志），各自能单独测；接 Tauri 的（`shell` 状态、`startup` 启动、`quit` 退出、`update`
//! 外壳更新、`window` 窗口与菜单、`commands` 启动页的命令、`splash` 那一屏）把它们串起来。

pub mod contract;
pub mod env;
pub mod http;
pub mod install;
pub mod logfile;
pub mod manifest;
pub mod nav;
pub mod places;
pub mod progress;
pub mod serve;
pub mod state;
pub mod supervise;
pub mod version;

mod commands;
mod quit;
mod shell;
mod splash;
mod startup;
mod update;
mod window;

use tauri::{Manager, RunEvent};
use tauri_plugin_window_state::StateFlags;

pub fn run() {
    let app = tauri::Builder::default()
        // 必须第一个注册：第二次打开时在这里就退出了，起不了第二套后端
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            log::info!("single_instance.second_launch");
            window::bring_back(app);
        }))
        // 窗口记大小与位置，不记显示与否（Mac 上收起着退出，下次照样要显示）
        .plugin(
            tauri_plugin_window_state::Builder::new()
                .with_state_flags(StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED)
                .build(),
        )
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            commands::attach,
            commands::retry,
            commands::open_log,
            commands::open_webview2_download
        ])
        .setup(|app| {
            let handle = app.handle();
            let log_path = shell::init_log(&shell::log_dir(handle)?);
            let shell = shell::Shell::new(handle, log_path, shell::splash_url(handle))?;
            app.manage(shell);
            #[cfg(target_os = "macos")]
            {
                app.set_menu(window::mac_menu(handle)?)?;
                app.on_menu_event(|app, event| {
                    if event.id() == window::QUIT_ID {
                        quit::request(app);
                    }
                });
            }
            window::create(handle)?;
            startup::kick(handle);
            Ok(())
        })
        .on_window_event(window::on_event)
        .build(tauri::generate_context!());
    let app = match app {
        Ok(app) => app,
        Err(error) => {
            log::error!("shell.build_failed error={error}");
            eprintln!("aaai4s: {error}");
            std::process::exit(1);
        }
    };
    app.run(|app, event| match event {
        RunEvent::Exit => quit::on_exit(app),
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => window::reopen(app),
        _ => {}
    });
}
