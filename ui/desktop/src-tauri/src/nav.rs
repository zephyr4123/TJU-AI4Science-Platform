//! 窗口能去哪（spec §2、§4「外壳替页面做的事」）。
//!
//! 页面是远程来源、对外壳零权限；页面里的 markdown 来自模型输出，不能让它够到外壳。所以：
//! - 导航只放行后端来源本身；回启动页只认外壳自己发起的那一次（导航前置一个一次性的标记）——不然后端
//!   来源上的任何脚本都能把窗口导回本地来源，拿到启动页能调的命令。
//! - `target=_blank`、`window.open` 与导航到别处：只有 http、https、mailto 交给系统浏览器；`file:`、`data:`、
//!   `blob:`、`javascript:`、`about:` 与一切自定义协议直接拒，日志只记协议名（Windows 上把文件拖进窗口，
//!   WebView2 缺省会导航到 `file:`，于是什么都不会运行）。

use std::path::{Path, PathBuf};
use std::sync::Mutex;

use url::Url;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    Allow,
    /// 交给系统浏览器（或邮件程序）
    External,
    Deny,
}

/// 交给系统去开的只有这三种：别的协议交出去等于让操作系统打开任意东西
pub fn external(url: &Url) -> bool {
    matches!(url.scheme(), "http" | "https" | "mailto")
}

/// 来源：协议、主机、端口。不用 `Url::origin()`：`tauri://` 不是特殊协议，它的 origin 是不透明的、
/// 每次都不相等
#[derive(Debug, Clone, PartialEq, Eq)]
struct Site(String, String, Option<u16>);

impl Site {
    fn of(url: &Url) -> Option<Self> {
        Some(Self(
            url.scheme().to_string(),
            url.host_str()?.to_string(),
            url.port_or_known_default(),
        ))
    }
}

pub struct Gate {
    /// 启动页的来源（`tauri://localhost`，Windows 上 `http://tauri.localhost`，源码桌面是开发服务器）
    splash: Option<Site>,
    inner: Mutex<Inner>,
}

struct Inner {
    backend: Option<Site>,
    splash_once: bool,
}

impl Gate {
    /// 第一次显示启动页本身也是一次外壳发起的导航：一开始就带着标记
    pub fn new(splash: &Url) -> Self {
        Self {
            splash: Site::of(splash),
            inner: Mutex::new(Inner {
                backend: None,
                splash_once: true,
            }),
        }
    }

    fn inner(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    pub fn navigation(&self, url: &Url) -> Verdict {
        let mut inner = self.inner();
        let site = Site::of(url);
        if site.is_some() && inner.backend == site {
            return Verdict::Allow;
        }
        if site.is_some() && self.splash == site && inner.splash_once {
            inner.splash_once = false;
            return Verdict::Allow;
        }
        if external(url) {
            Verdict::External
        } else {
            Verdict::Deny
        }
    }

    /// 新窗口一律不开：能交给系统的交出去，其余拒
    pub fn new_window(&self, url: &Url) -> Verdict {
        if external(url) {
            Verdict::External
        } else {
            Verdict::Deny
        }
    }

    /// serve 起来了：窗口要去的就是它
    pub fn open_backend(&self, url: &Url) {
        let mut inner = self.inner();
        inner.backend = Site::of(url);
        inner.splash_once = false;
    }

    /// 外壳要把窗口带回启动页：后端来源不再放行，放行接下来那一次回启动页
    pub fn back_to_splash(&self) {
        let mut inner = self.inner();
        inner.backend = None;
        inner.splash_once = true;
    }
}

/// 下载落「下载」目录、不重名：`a.pdf`、`a (1).pdf`、`a (2).pdf`…
pub fn download_target(dir: &Path, suggested: &str) -> PathBuf {
    // 建议的名字来自页面：只取最后一段，不许带路径爬出「下载」目录
    let name = Path::new(suggested)
        .file_name()
        .and_then(|n| n.to_str())
        .filter(|n| !n.is_empty() && *n != "..");
    let name = name.unwrap_or("download");
    let (stem, ext) = match name.rsplit_once('.') {
        Some((stem, ext)) if !stem.is_empty() => (stem, format!(".{ext}")),
        _ => (name, String::new()),
    };
    let mut target = dir.join(name);
    let mut n = 1;
    while target.exists() {
        target = dir.join(format!("{stem} ({n}){ext}"));
        n += 1;
    }
    target
}

#[cfg(test)]
mod tests {
    use super::*;

    fn u(raw: &str) -> Url {
        Url::parse(raw).unwrap()
    }

    #[test]
    fn only_the_backend_and_the_shells_own_way_back_are_allowed() {
        let gate = Gate::new(&u("tauri://localhost/index.html"));
        assert_eq!(
            gate.navigation(&u("tauri://localhost/index.html")),
            Verdict::Allow,
            "第一次显示启动页"
        );
        assert_eq!(
            gate.navigation(&u("tauri://localhost/index.html")),
            Verdict::Deny,
            "标记只用一次"
        );
        let backend = u("http://127.0.0.1:51234/");
        gate.open_backend(&backend);
        assert_eq!(
            gate.navigation(&u("http://127.0.0.1:51234/projects/x")),
            Verdict::Allow
        );
        assert_eq!(
            gate.navigation(&u("http://127.0.0.1:51235/")),
            Verdict::External,
            "别的端口是别人"
        );
        assert_eq!(
            gate.navigation(&u("http://localhost:51234/")),
            Verdict::External
        );
        // 后端页面上的脚本想回启动页：外壳没发起，拒
        assert_eq!(
            gate.navigation(&u("tauri://localhost/index.html")),
            Verdict::Deny
        );
        gate.back_to_splash();
        assert_eq!(
            gate.navigation(&backend),
            Verdict::External,
            "回启动页以后后端来源不再放行"
        );
        assert_eq!(
            gate.navigation(&u("tauri://localhost/index.html")),
            Verdict::Allow
        );
    }

    #[test]
    fn only_web_and_mail_links_go_to_the_system() {
        let gate = Gate::new(&u("http://tauri.localhost/index.html"));
        gate.open_backend(&u("http://127.0.0.1:51234/"));
        for raw in [
            "https://openalex.org/settings/api",
            "http://example.com/a",
            "mailto:a@b.c",
        ] {
            assert_eq!(gate.navigation(&u(raw)), Verdict::External, "{raw}");
            assert_eq!(gate.new_window(&u(raw)), Verdict::External, "{raw}");
        }
        for raw in [
            "file:///C:/Users/r/Desktop/run.bat",
            "data:text/html,<script>1</script>",
            "blob:http://127.0.0.1:51234/0b2c",
            "javascript:alert(1)",
            "about:blank",
            "ms-settings:privacy",
            "vscode://file/x",
            "tauri://localhost/index.html",
        ] {
            assert_eq!(gate.navigation(&u(raw)), Verdict::Deny, "{raw}");
            assert_eq!(gate.new_window(&u(raw)), Verdict::Deny, "{raw}");
        }
    }

    #[test]
    fn a_download_never_overwrites_and_never_leaves_the_folder() {
        let dir = std::env::temp_dir().join(format!("aaai4s-dl-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(download_target(&dir, "notes.pdf"), dir.join("notes.pdf"));
        std::fs::write(dir.join("notes.pdf"), "").unwrap();
        std::fs::write(dir.join("notes (1).pdf"), "").unwrap();
        assert_eq!(
            download_target(&dir, "notes.pdf"),
            dir.join("notes (2).pdf")
        );
        assert_eq!(
            download_target(&dir, "../../etc/passwd"),
            dir.join("passwd")
        );
        assert_eq!(download_target(&dir, ""), dir.join("download"));
        assert_eq!(download_target(&dir, ".bashrc"), dir.join(".bashrc"));
        std::fs::remove_dir_all(dir).unwrap();
    }
}
