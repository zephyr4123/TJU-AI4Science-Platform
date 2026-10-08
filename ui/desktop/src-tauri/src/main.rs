// release 版是 GUI 子系统，不带控制台窗口
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    aaai4s::run();
}
