//! AAAI4S 桌面 App 的外壳（外层 #282，spec docs/specs/desktop.md）：一个窗口套在 `ai4sci serve` 外面，
//! 不另起后端。外壳只依赖 `contract.rs` 里的后端约定，不认识框架内部。

pub mod contract;
pub mod env;
pub mod http;
pub mod install;
pub mod logfile;
pub mod manifest;
pub mod places;
pub mod progress;
pub mod serve;
pub mod state;
pub mod supervise;
pub mod version;
