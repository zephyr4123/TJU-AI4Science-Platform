// 外壳自己的命令只给启动页（spec §2）：登记成 app manifest，命令就要在 capability 里点名才放行，
// 本地来源也一样；后端页面是远程来源、没有任何 capability，一条也调不到。
const COMMANDS: &[&str] = &["attach", "retry", "open_log", "open_webview2_download"];

fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(COMMANDS)),
    )
    .expect("tauri-build 没跑通");
}
