//! 启动页那一屏的内容（spec §1）：一行状态与已用时间、进度行（一个标签一行）、出错时说一句为什么。
//!
//! 外壳这边记着整屏的样子，启动页每次载入时 `attach` 一个 Channel，先拿一份全貌、之后收增量；窗口离开
//! 启动页就不再往它发（离开以后当前页面可能已经是远程页面）。启动页只拿到文字，一律 `textContent` 渲染。

use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::Serialize;
use tauri::ipc::Channel;

use crate::progress::{self, Row};

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Problem {
    pub text: String,
    /// 给「重试」：重来一遍能好的才给（拖进「应用程序」、装新版 WebView2 这种重试没用）
    pub retry: bool,
    /// 给「下载 WebView2」（Windows 上 WebView2 太旧）
    pub webview2: bool,
}

impl Problem {
    pub fn retry(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            retry: true,
            webview2: false,
        }
    }

    pub fn fatal(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            retry: false,
            webview2: false,
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub enum Event {
    #[serde(rename_all = "camelCase")]
    Snapshot {
        started_at: u64,
        status: String,
        rows: Vec<Row>,
        problem: Option<Problem>,
    },
    Status {
        text: String,
    },
    Row {
        row: Row,
    },
    Problem {
        problem: Problem,
    },
}

#[derive(Default)]
pub struct Splash {
    inner: Mutex<Inner>,
}

#[derive(Default)]
struct Inner {
    started_at: u64,
    status: String,
    rows: Vec<Row>,
    problem: Option<Problem>,
    channel: Option<Channel<Event>>,
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

impl Inner {
    fn snapshot(&self) -> Event {
        Event::Snapshot {
            started_at: self.started_at,
            status: self.status.clone(),
            rows: self.rows.clone(),
            problem: self.problem.clone(),
        }
    }

    fn send(&mut self, event: Event) {
        if let Some(channel) = &self.channel
            && channel.send(event).is_err()
        {
            self.channel = None; // 那一页已经没了
        }
    }
}

impl Splash {
    fn inner(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// 从头来一遍：清掉进度与出错，已用时间从现在算
    pub fn begin(&self, status: &str) {
        let mut inner = self.inner();
        inner.started_at = now_ms();
        inner.status = status.to_string();
        inner.rows.clear();
        inner.problem = None;
        let snapshot = inner.snapshot();
        inner.send(snapshot);
    }

    pub fn status(&self, text: &str) {
        let mut inner = self.inner();
        inner.status = text.to_string();
        inner.send(Event::Status {
            text: text.to_string(),
        });
    }

    /// 子进程的一行：是进度行就并进清单
    pub fn line(&self, line: &str) {
        if let Some(row) = progress::parse(line) {
            self.row(row);
        }
    }

    pub fn row(&self, row: Row) {
        let mut inner = self.inner();
        progress::merge(&mut inner.rows, row.clone());
        inner.send(Event::Row { row });
    }

    pub fn problem(&self, problem: Problem) {
        log::warn!(
            "splash.problem text={} retry={}",
            problem.text,
            problem.retry
        );
        let mut inner = self.inner();
        inner.problem = Some(problem.clone());
        inner.send(Event::Problem { problem });
    }

    /// 「重试」只在出了能重试的错时才算数
    pub fn retryable(&self) -> bool {
        self.inner().problem.as_ref().is_some_and(|p| p.retry)
    }

    pub fn attach(&self, channel: Channel<Event>) {
        let mut inner = self.inner();
        inner.channel = Some(channel);
        let snapshot = inner.snapshot();
        inner.send(snapshot);
    }

    pub fn detach(&self) {
        self.inner().channel = None;
    }
}
