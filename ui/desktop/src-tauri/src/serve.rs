//! 起 serve（spec §3 serve、§4 第 7 步）：`ai4sci serve --host 127.0.0.1 --port <N> --until-stdin-closes`，
//! 读到 stdout 上 `ok http://` 开头的那一行（60 秒内）就算起来了；退出码 3 是端口用不了。
//! 读 `/health` 的在跑轮数也在这里：外壳退出前要不要问一句。

use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::sync::oneshot;
use url::Url;

use crate::contract::{
    EXIT_PORT, HEALTH_PATH, SERVE_HOST, SERVE_OK_PREFIX, TURNS_FIELD, serve_args,
};
use crate::env::Overlay;
use crate::supervise::{Handle, Kind, Launch, Sink, Stream, Supervisor};

pub const READY_TIMEOUT: Duration = Duration::from_secs(60);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(2);

/// `ok http://127.0.0.1:51234\thome=…\tui=…` → `http://127.0.0.1:51234/`；只认本机回环上的
pub fn parse_ok_line(line: &str) -> Option<Url> {
    if !line.starts_with(SERVE_OK_PREFIX) {
        return None;
    }
    let first = line[3..].split('\t').next()?.trim();
    let url = Url::parse(first).ok()?;
    let ours = url.scheme() == "http" && url.host_str() == Some(SERVE_HOST) && url.port().is_some();
    ours.then(|| url.join("/").ok()).flatten()
}

#[derive(Debug)]
pub enum ServeError {
    /// 端口被占或在 Windows 的保留段里（退出码 3）：换一个端口再起
    PortBusy,
    /// 没打 `ok` 那一行就退了
    Exited(Option<i32>),
    /// 60 秒没打 `ok` 那一行（已收拾掉）
    Timeout,
    Spawn(std::io::Error),
}

impl std::fmt::Display for ServeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ServeError::PortBusy => write!(f, "端口用不了"),
            ServeError::Exited(Some(code)) => write!(f, "服务一起来就退了（退出码 {code}）"),
            ServeError::Exited(None) => write!(f, "服务一起来就被停了"),
            ServeError::Timeout => write!(f, "服务 {} 秒没起来", READY_TIMEOUT.as_secs()),
            ServeError::Spawn(error) => write!(f, "服务起不来：{error}"),
        }
    }
}

pub struct Running {
    pub url: Url,
    pub serve: Handle,
}

/// 起一次 serve；`port` 为 0 时让系统给一个空闲端口。`sink` 照常收到每一行（写日志、给启动页）。
pub async fn start(
    sup: &Supervisor,
    cli: &Path,
    port: u16,
    overlay: Overlay,
    cwd: &Path,
    sink: Sink,
) -> Result<Running, ServeError> {
    let (ready_tx, ready_rx) = oneshot::channel();
    let ready_tx = Arc::new(Mutex::new(Some(ready_tx)));
    let watch: Sink = Arc::new(move |kind, stream, line| {
        if stream == Stream::Out
            && let Some(url) = parse_ok_line(line)
            && let Some(tx) = ready_tx.lock().unwrap_or_else(|p| p.into_inner()).take()
        {
            let _ = tx.send(url);
        }
        sink(kind, stream, line);
    });
    let launch = Launch {
        kind: Kind::Serve,
        program: cli.to_path_buf(),
        args: serve_args(port).into_iter().map(Into::into).collect(),
        overlay,
        extra: Vec::new(),
        cwd: cwd.to_path_buf(),
    };
    let child = sup.spawn(launch, watch).map_err(ServeError::Spawn)?;
    let outcome = tokio::time::timeout(READY_TIMEOUT, async {
        tokio::select! {
            biased; // 打了 ok 行就算起来了，哪怕紧接着就退
            url = ready_rx => url.ok(),
            _ = child.wait() => None,
        }
    })
    .await;
    match outcome {
        Ok(Some(url)) => {
            log::info!("serve.ready url={url} pid={:?}", child.handle.pid);
            Ok(Running {
                url,
                serve: child.handle,
            })
        }
        Ok(None) => {
            let exit = child.wait().await;
            log::warn!("serve.exited_early code={:?}", exit.code);
            if exit.code == Some(EXIT_PORT) {
                Err(ServeError::PortBusy)
            } else {
                Err(ServeError::Exited(exit.code))
            }
        }
        Err(_) => {
            log::warn!("serve.not_ready_in_time pid={:?}", child.handle.pid);
            child.kill();
            child.wait().await;
            Err(ServeError::Timeout)
        }
    }
}

/// 此刻在跑的对话轮数；问不到（服务已经不在、旧版平台的 `/health` 没有这一项）是 None
pub async fn turns(client: &reqwest::Client, base: &Url) -> Option<u64> {
    let url = base.join(HEALTH_PATH).ok()?;
    let resp = client.get(url).timeout(HEALTH_TIMEOUT).send().await.ok()?;
    let body: serde_json::Value = resp.json().await.ok()?;
    body.get(TURNS_FIELD)?.as_u64()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_ok_line_gives_the_address_and_nothing_else_does() {
        let url = parse_ok_line("ok http://127.0.0.1:51234\thome=/Users/r/.ai4sci\tui=-").unwrap();
        assert_eq!(url.as_str(), "http://127.0.0.1:51234/");
        assert_eq!(
            parse_ok_line("ok http://127.0.0.1:8765").unwrap().port(),
            Some(8765)
        );
        for line in [
            "INFO serving on http://127.0.0.1:8765",
            "ok http://localhost:8765\thome=-",
            "ok http://0.0.0.0:8765",
            "ok http://127.0.0.1",
            "ok https://127.0.0.1:8765",
            " ok http://127.0.0.1:8765",
            "ok http://127.0.0.1.evil.com:8765",
        ] {
            assert_eq!(parse_ok_line(line), None, "{line}");
        }
    }
}
