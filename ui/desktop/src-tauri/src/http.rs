//! 两个 HTTP 客户端：上 CDN 的（与更新器同一套 rustls + ring，依赖树里不多出第二份 TLS）、问本机 serve
//! 的（不走系统代理：代理够不着 127.0.0.1）。

use std::time::Duration;

/// 进程里装一次 TLS 的密码学实现（更新器也是这样装的，谁先装都一样）
pub fn install_tls() {
    let _ = rustls::crypto::ring::default_provider().install_default();
}

pub fn internet(shell_version: &str) -> reqwest::Result<reqwest::Client> {
    install_tls();
    reqwest::Client::builder()
        .user_agent(format!("AAAI4S/{shell_version}"))
        .connect_timeout(Duration::from_secs(10))
        .build()
}

pub fn loopback() -> reqwest::Result<reqwest::Client> {
    install_tls();
    reqwest::Client::builder().no_proxy().build()
}
