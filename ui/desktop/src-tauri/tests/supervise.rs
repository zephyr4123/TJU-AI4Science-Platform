//! 守进程的集成测试：用假的 `ai4sci`（`examples/fake_ai4sci.rs`，`cargo test` 会顺带编出来）真起进程。
//! 退出 App 时不留孤儿是硬要求（spec §0 第 4 条）：这里断言整棵树——serve 与它起的「对话轮次」——都没了。
//!
//! 最后一条连真的后端（仓里 `.venv` 的 `ai4sci`，`make venv` 或 CI 的 `uv sync` 建的）。

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use aaai4s::env::Overlay;
use aaai4s::install;
use aaai4s::progress;
use aaai4s::serve::{self, ServeError};
use aaai4s::supervise::{Kind, Sink, Stream, Supervisor};
use aaai4s::version::Version;

fn fake() -> PathBuf {
    // target/debug/deps/supervise-<hash> → target/debug/examples/fake_ai4sci
    let exe = std::env::current_exe().unwrap();
    let path = exe
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("examples")
        .join(format!("fake_ai4sci{}", std::env::consts::EXE_SUFFIX));
    assert!(
        path.is_file(),
        "没有 {}：先 cargo build --examples（cargo test 会顺带编）",
        path.display()
    );
    path
}

/// 外壳给子进程的那一层环境，再加上调假 ai4sci 行为的变量
fn overlay(extra: &[(&str, &str)]) -> Overlay {
    let mut overlay = Overlay::new(&[], std::env::var_os("PATH"), true);
    overlay.set.extend(
        extra
            .iter()
            .map(|(k, v)| (k.to_string(), OsString::from(v))),
    );
    overlay
}

#[derive(Clone, Default)]
struct Lines(Arc<Mutex<Vec<(Kind, Stream, String)>>>);

impl Lines {
    fn sink(&self) -> Sink {
        let lines = self.0.clone();
        Arc::new(move |kind, stream, line| {
            lines.lock().unwrap().push((kind, stream, line.to_string()))
        })
    }

    fn all(&self) -> Vec<(Kind, Stream, String)> {
        self.0.lock().unwrap().clone()
    }

    /// 假 serve 在 stderr 上报的那一轮对话的 pid。stdout 与 stderr 各一个读线程，`start` 读到 `ok`
    /// 那一行就返回，这时 stderr 上先打的那一行不一定已经读进来（CI 的 Windows 上撞到过）：等一会儿
    async fn turn_pid(&self) -> u32 {
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            let found = self
                .all()
                .iter()
                .find_map(|(_, _, line)| line.strip_prefix("turn ")?.parse().ok());
            if let Some(pid) = found {
                return pid;
            }
            assert!(Instant::now() < deadline, "假 serve 没报对话轮次的 pid");
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    }
}

fn alive(pid: u32) -> bool {
    #[cfg(unix)]
    {
        use nix::sys::signal::kill;
        use nix::unistd::Pid;
        kill(Pid::from_raw(pid as i32), None).is_ok()
    }
    #[cfg(windows)]
    {
        let out = std::process::Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV", "/NH"])
            .output()
            .unwrap();
        String::from_utf8_lossy(&out.stdout).contains(&format!("\"{pid}\""))
    }
}

async fn gone(pid: u32) -> bool {
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline {
        if !alive(pid) {
            return true;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    false
}

fn cwd() -> PathBuf {
    std::env::temp_dir()
}

#[tokio::test(flavor = "multi_thread")]
async fn the_version_is_read_whichever_way_it_is_spelled() {
    let sup = Supervisor::default();
    let found = install::installed_version(
        &sup,
        &fake(),
        &overlay(&[("FAKE_AI4SCI_VERSION", "1.9.0rc1")]),
        &cwd(),
    )
    .await;
    assert_eq!(found, Some(Version::parse("1.9.0-rc.1").unwrap()));
    assert_eq!(
        install::installed_version(&sup, Path::new("/no/such/ai4sci"), &overlay(&[]), &cwd()).await,
        None
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn setup_streams_its_progress_line_by_line() {
    let sup = Supervisor::default();
    let lines = Lines::default();
    let ok = install::setup(
        &sup,
        &fake(),
        &overlay(&[("FAKE_AI4SCI_SLOW_MS", "10")]),
        &cwd(),
        lines.sink(),
    )
    .await;
    assert!(ok);
    let mut rows = Vec::new();
    for (kind, stream, line) in lines.all() {
        assert_eq!(kind, Kind::Setup);
        if let Some(row) = progress::parse(&line) {
            assert_eq!(stream, Stream::Out);
            progress::merge(&mut rows, row);
        }
    }
    let labels: Vec<_> = rows
        .iter()
        .map(|r| (r.mark.as_str(), r.label.as_str()))
        .collect();
    assert_eq!(labels, [("✓", "git"), ("✓", "Claude Code"), ("✓", "Codex")]);
    let failed = install::setup(
        &sup,
        &fake(),
        &overlay(&[
            ("FAKE_AI4SCI_SLOW_MS", "1"),
            ("FAKE_AI4SCI_SETUP_EXIT", "1"),
        ]),
        &cwd(),
        lines.sink(),
    )
    .await;
    assert!(!failed);
}

#[tokio::test(flavor = "multi_thread")]
async fn closing_stdin_stops_serve_and_the_turns_it_started() {
    let sup = Supervisor::default();
    let lines = Lines::default();
    let running = serve::start(&sup, &fake(), 0, overlay(&[]), &cwd(), lines.sink())
        .await
        .unwrap();
    assert_eq!(running.url.host_str(), Some("127.0.0.1"));
    assert_ne!(running.url.port(), Some(0));
    let turns = serve::turns(&aaai4s::http::loopback().unwrap(), &running.url).await;
    assert_eq!(turns, Some(0));
    let serve_pid = running.serve.pid.unwrap();
    let turn_pid = lines.turn_pid().await;
    assert!(alive(turn_pid));
    sup.shutdown(Duration::from_secs(5)).await;
    assert_eq!(
        running.serve.wait().await.code,
        Some(0),
        "serve 自己收拾完退出"
    );
    assert!(gone(serve_pid).await);
    assert!(gone(turn_pid).await, "对话轮次被 serve 停掉");
    assert!(
        sup.spawn(launch_version(), lines.sink()).is_err(),
        "退出以后不再起子进程"
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn a_serve_that_ignores_its_stdin_is_cleared_with_its_whole_tree() {
    let sup = Supervisor::default();
    let lines = Lines::default();
    let running = serve::start(
        &sup,
        &fake(),
        0,
        overlay(&[("FAKE_AI4SCI_STUBBORN", "1")]),
        &cwd(),
        lines.sink(),
    )
    .await
    .unwrap();
    let serve_pid = running.serve.pid.unwrap();
    let turn_pid = lines.turn_pid().await;
    let started = Instant::now();
    sup.shutdown(Duration::from_millis(500)).await;
    assert!(started.elapsed() < Duration::from_secs(4));
    assert!(gone(serve_pid).await, "serve 被收拾");
    // Mac 上这一轮自成进程组，只 killpg 杀不到它；Windows 上它在 serve 的 Job 里
    assert!(gone(turn_pid).await, "自成进程组的对话轮次也被收拾");
}

#[tokio::test(flavor = "multi_thread")]
async fn a_busy_port_is_reported_so_the_shell_can_take_another() {
    let sup = Supervisor::default();
    let busy = serve::start(
        &sup,
        &fake(),
        47123,
        overlay(&[("FAKE_AI4SCI_PORT_BUSY", "47123")]),
        &cwd(),
        Lines::default().sink(),
    )
    .await;
    assert!(
        matches!(busy, Err(ServeError::PortBusy)),
        "{:?}",
        busy.err()
    );
    let lines = Lines::default();
    let other = serve::start(
        &sup,
        &fake(),
        0,
        overlay(&[("FAKE_AI4SCI_PORT_BUSY", "47123")]),
        &cwd(),
        lines.sink(),
    )
    .await
    .unwrap();
    assert_ne!(other.url.port(), Some(47123));
    let turn_pid = lines.turn_pid().await;
    sup.stop(&other.serve, Duration::from_secs(5)).await;
    assert!(gone(turn_pid).await);
}

#[tokio::test(flavor = "multi_thread")]
async fn a_serve_that_is_killed_is_noticed() {
    let sup = Supervisor::default();
    let running = serve::start(
        &sup,
        &fake(),
        0,
        overlay(&[]),
        &cwd(),
        Lines::default().sink(),
    )
    .await
    .unwrap();
    running.serve.kill();
    let exit = tokio::time::timeout(Duration::from_secs(5), running.serve.wait())
        .await
        .expect("serve 退出要被看见");
    assert_eq!(exit.code, None, "被收拾的没有退出码");
}

#[tokio::test(flavor = "multi_thread")]
async fn a_child_that_goes_silent_is_taken_down() {
    let sup = Supervisor::default();
    let mut launch = launch_version();
    launch.kind = Kind::Install;
    launch.args = vec!["sleep".into()];
    let child = sup.spawn(launch, Lines::default().sink()).unwrap();
    let started = Instant::now();
    let exit = tokio::time::timeout(
        Duration::from_secs(10),
        child.finish_unless_silent(Duration::from_millis(500)),
    )
    .await
    .expect("不说话的子进程要被收掉");
    assert_eq!(exit, None, "收掉的不算退出");
    assert!(started.elapsed() >= Duration::from_millis(500));

    let child = sup
        .spawn(launch_version(), Lines::default().sink())
        .unwrap();
    let exit = child.finish_unless_silent(Duration::from_secs(10)).await;
    assert_eq!(exit.map(|e| e.code), Some(Some(0)), "说完就退的照常");
}

fn launch_version() -> aaai4s::supervise::Launch {
    aaai4s::supervise::Launch {
        kind: Kind::Version,
        program: fake(),
        args: vec!["--version".into()],
        overlay: overlay(&[]),
        extra: Vec::new(),
        cwd: cwd(),
    }
}

/// 真的后端（仓里 `.venv` 的 ai4sci，或 `AI4SCI_DESKTOP_CLI` 指的那个）：临时的家里真起 serve，读那一行、
/// 问 `/health`、关掉标准输入，5 秒内退干净。约定在后端那边变了，这里先红。
#[tokio::test(flavor = "multi_thread")]
async fn the_real_backend_starts_and_stops_on_the_contract() {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let cli = std::env::var_os("AI4SCI_DESKTOP_CLI")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            if cfg!(windows) {
                repo.join(".venv/Scripts/ai4sci.exe")
            } else {
                repo.join(".venv/bin/ai4sci")
            }
        });
    let home = std::env::temp_dir().join(format!("aaai4s-it-{}", std::process::id()));
    std::fs::create_dir_all(&home).unwrap();
    let sup = Supervisor::default();
    let it = overlay(&[("AI4SCI_HOME", home.to_str().unwrap())]);
    let version = install::installed_version(&sup, &cli, &it, &cwd()).await;
    assert!(version.is_some(), "{} --version 读不出版本", cli.display());
    let running = serve::start(&sup, &cli, 0, it, &cwd(), Lines::default().sink())
        .await
        .unwrap();
    let client = aaai4s::http::loopback().unwrap();
    assert!(
        serve::turns(&client, &running.url).await.is_some(),
        "/health 要有 turns"
    );
    let started = Instant::now();
    sup.stop(&running.serve, Duration::from_secs(5)).await;
    assert!(
        started.elapsed() < Duration::from_secs(5),
        "关掉标准输入 5 秒内退出"
    );
    let port = running.url.port().unwrap();
    assert!(
        std::net::TcpListener::bind(("127.0.0.1", port)).is_ok(),
        "端口放出来了"
    );
    let _ = std::fs::remove_dir_all(home);
}
