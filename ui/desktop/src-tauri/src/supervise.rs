//! 守进程（spec §4「守进程树」）：外壳起的每个子进程（安装脚本、setup、`--version`、serve）都经这里。
//!
//! - Windows：process-wrap 把子进程挂起、放进一个只设 `KILL_ON_JOB_CLOSE` 的 Job、再恢复（不留竞态），
//!   不带控制台窗口。Job 的句柄在外壳手里、外壳自己不进 Job（更新器拉起的安装器、重启出的新实例才不会被
//!   连带杀掉）：外壳怎么死，内核都会关掉句柄、杀掉 Job 里的一切。
//! - Mac：各自一个进程组。收拾时先停住根进程，趁它还活着顺父子关系找出后代、从叶子起逐个 SIGKILL（对话
//!   轮次自成会话，killpg 够不着），再 SIGKILL 整组。
//! - 标准输入一律接管道（Windows 上接 NUL 时 `isatty()` 是真，getpass 会卡死）：serve 握着它，关掉就是
//!   让它收拾在跑的轮次后退出；别的子进程起来就关。
//! - stdout、stderr 一直读（不读会把 serve 顶住），按 UTF-8（坏字节替换）一行一行写进日志、交给 sink。
//!
//! 根进程退出后，它同组 / 同 Job 里还剩的立刻收掉：serve 自己崩了留下的轮次就在这里收（Windows 上「重试」
//! 前结束整个 Job 的那一步）；Mac 上自成会话的那些由下一个 serve 启动时按 #285 的登记清掉。

use std::collections::HashMap;
use std::ffi::OsString;
use std::io;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use process_wrap::tokio::{ChildWrapper, CommandWrap, KillOnDrop};
use tokio::io::{AsyncBufReadExt, AsyncRead, BufReader};
use tokio::process::ChildStdin;
use tokio::sync::{oneshot, watch};
use tokio::task::JoinHandle;

use crate::env::Overlay;

/// 看守多久看一眼根进程还在不在
const POLL: Duration = Duration::from_millis(100);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Kind {
    Version,
    Install,
    Setup,
    Serve,
}

impl Kind {
    pub fn name(self) -> &'static str {
        match self {
            Kind::Version => "version",
            Kind::Install => "install",
            Kind::Setup => "setup",
            Kind::Serve => "serve",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stream {
    Out,
    Err,
}

/// 每一行输出交给谁：启动页的进度、serve 的 `ok` 行、`--version` 的那一行都从这里拿
pub type Sink = Arc<dyn Fn(Kind, Stream, &str) + Send + Sync>;

pub fn quiet() -> Sink {
    Arc::new(|_, _, _| {})
}

/// 起一个子进程要的全部：程序、参数、环境那一层、额外的变量、工作目录（外壳的临时目录）
pub struct Launch {
    pub kind: Kind,
    pub program: PathBuf,
    pub args: Vec<OsString>,
    pub overlay: Overlay,
    pub extra: Vec<(String, OsString)>,
    pub cwd: PathBuf,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Exit {
    /// 被信号杀掉、被收拾掉的没有退出码
    pub code: Option<i32>,
}

#[derive(Clone, Default)]
pub struct Supervisor {
    inner: Arc<Mutex<Registry>>,
}

#[derive(Default)]
struct Registry {
    next: u64,
    closing: bool,
    running: HashMap<u64, Entry>,
}

struct Entry {
    kind: Kind,
    stdin: Option<ChildStdin>,
    kill: Option<oneshot::Sender<()>>,
    exit: watch::Receiver<Option<Exit>>,
}

/// 一个在跑的子进程：等它、停它、收拾它；可以复制给别的任务（看 serve 有没有中途退出的那个）
#[derive(Clone)]
pub struct Handle {
    id: u64,
    pub pid: Option<u32>,
    pub kind: Kind,
    exit: watch::Receiver<Option<Exit>>,
    sup: Supervisor,
}

/// 刚起来的子进程：多带着读它输出的两个任务、它上一次说话的时刻
pub struct Child {
    pub handle: Handle,
    readers: Vec<JoinHandle<()>>,
    heard: Arc<Mutex<Instant>>,
}

impl Supervisor {
    fn registry(&self) -> std::sync::MutexGuard<'_, Registry> {
        self.inner
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    pub fn spawn(&self, launch: Launch, sink: Sink) -> io::Result<Child> {
        if self.registry().closing {
            return Err(io::Error::other("外壳正在退出，不再起子进程"));
        }
        let kind = launch.kind;
        let mut cmd = tokio::process::Command::new(&launch.program);
        cmd.args(&launch.args).current_dir(&launch.cwd);
        launch.overlay.apply(&mut cmd);
        for (name, value) in &launch.extra {
            cmd.env(name, value);
        }
        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let mut wrapped = CommandWrap::from(cmd);
        #[cfg(unix)]
        wrapped.wrap(process_wrap::tokio::ProcessGroup::leader());
        #[cfg(windows)]
        {
            use process_wrap::tokio::{CreationFlags, JobObject};
            use windows::Win32::System::Threading::CREATE_NO_WINDOW;
            wrapped
                .wrap(CreationFlags(CREATE_NO_WINDOW))
                .wrap(JobObject);
        }
        wrapped.wrap(KillOnDrop);
        let mut child = wrapped.spawn().map_err(|error| {
            log::warn!(
                "child.spawn_failed kind={} program={} error={error}",
                kind.name(),
                launch.program.display()
            );
            error
        })?;
        let pid = child.id();
        let stdin = child.stdin().take().filter(|_| kind == Kind::Serve);
        let heard = Arc::new(Mutex::new(Instant::now()));
        let mut readers = Vec::new();
        if let Some(out) = child.stdout().take() {
            readers.push(read_lines(
                out,
                kind,
                Stream::Out,
                sink.clone(),
                heard.clone(),
            ));
        }
        if let Some(err) = child.stderr().take() {
            readers.push(read_lines(err, kind, Stream::Err, sink, heard.clone()));
        }
        let (kill_tx, kill_rx) = oneshot::channel();
        let (exit_tx, exit_rx) = watch::channel(None);
        let id = {
            let mut registry = self.registry();
            registry.next += 1;
            let id = registry.next;
            // 起的这一会儿外壳开始退出了：登记上就收拾，不漏一个
            let kill = if registry.closing {
                let _ = kill_tx.send(());
                None
            } else {
                Some(kill_tx)
            };
            let entry = Entry {
                kind,
                stdin,
                kill,
                exit: exit_rx.clone(),
            };
            registry.running.insert(id, entry);
            id
        };
        log::info!(
            "child.start kind={} pid={pid:?} program={}",
            kind.name(),
            launch.program.display()
        );
        tokio::spawn(own(child, kill_rx, exit_tx, self.clone(), id, kind));
        Ok(Child {
            handle: Handle {
                id,
                pid,
                kind,
                exit: exit_rx,
                sup: self.clone(),
            },
            readers,
            heard,
        })
    }

    fn close_stdin(&self, id: u64) {
        if let Some(entry) = self.registry().running.get_mut(&id) {
            entry.stdin = None;
        }
    }

    fn kill(&self, id: u64) {
        if let Some(kill) = self
            .registry()
            .running
            .get_mut(&id)
            .and_then(|e| e.kill.take())
        {
            let _ = kill.send(());
        }
    }

    /// 停一个子进程：关它的标准输入，`grace` 内没退就收拾整棵树
    pub async fn stop(&self, handle: &Handle, grace: Duration) -> Exit {
        self.close_stdin(handle.id);
        if let Ok(exit) = tokio::time::timeout(grace, handle.wait()).await {
            return exit;
        }
        log::warn!(
            "child.stop_grace_over kind={} pid={:?}",
            handle.kind.name(),
            handle.pid
        );
        self.kill(handle.id);
        handle.wait().await
    }

    /// 退出 App（spec §4「退出」第 2–3 步）：关掉 serve 的标准输入让它自己停掉在跑的轮次，同时收掉安装脚本、
    /// setup；`grace` 内还没退的整棵树收拾掉。之后不再起子进程。
    pub async fn shutdown(&self, grace: Duration) {
        let waits: Vec<_> = {
            let mut registry = self.registry();
            registry.closing = true;
            for entry in registry.running.values_mut() {
                entry.stdin = None;
                if entry.kind != Kind::Serve
                    && let Some(kill) = entry.kill.take()
                {
                    let _ = kill.send(());
                }
            }
            registry.running.values().map(|e| e.exit.clone()).collect()
        };
        if waits.is_empty() {
            return;
        }
        log::info!("shutdown.start children={}", waits.len());
        if tokio::time::timeout(grace, wait_all(waits.clone()))
            .await
            .is_err()
        {
            log::warn!("shutdown.grace_over");
            self.kill_all_now();
            if tokio::time::timeout(Duration::from_secs(3), wait_all(waits))
                .await
                .is_err()
            {
                log::warn!("shutdown.still_running");
            }
        }
        log::info!("shutdown.done");
    }

    /// 不等：关掉所有标准输入、让每个子进程的看守收拾整棵树。给拿不到异步的地方（更新器在 Windows 上
    /// `process::exit` 之前的钩子）；就算看守还没来得及动手，进程退出时 Job 的句柄一关，内核照样全杀。
    pub fn kill_all_now(&self) {
        let mut registry = self.registry();
        registry.closing = true;
        for entry in registry.running.values_mut() {
            entry.stdin = None;
            if let Some(kill) = entry.kill.take() {
                let _ = kill.send(());
            }
        }
    }

    /// 退出没走成（装外壳新版失败）：重新放行起子进程
    pub fn reopen(&self) {
        self.registry().closing = false;
    }

    fn forget(&self, id: u64) {
        self.registry().running.remove(&id);
    }
}

impl Handle {
    pub async fn wait(&self) -> Exit {
        let mut exit = self.exit.clone();
        match exit.wait_for(Option::is_some).await {
            Ok(exit) => exit.expect("等到的就是 Some"),
            // 看守走了却没留下结果：只会是运行时在关
            Err(_) => Exit { code: None },
        }
    }

    /// 不等它自己退，直接收拾整棵树
    pub fn kill(&self) {
        self.sup.kill(self.id);
    }

    pub fn close_stdin(&self) {
        self.sup.close_stdin(self.id);
    }
}

impl Child {
    pub async fn wait(&self) -> Exit {
        self.handle.wait().await
    }

    pub fn kill(&self) {
        self.handle.kill();
    }

    /// 同 `finish`，但它连着 `limit` 一行都不说就当卡住了（连接还在、数据不来）：收拾整棵树，返回 None
    pub async fn finish_unless_silent(self, limit: Duration) -> Option<Exit> {
        loop {
            let quiet = self
                .heard
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .elapsed();
            if quiet >= limit {
                log::warn!(
                    "child.silent kind={} pid={:?} secs={}",
                    self.handle.kind.name(),
                    self.handle.pid,
                    quiet.as_secs()
                );
                self.kill();
                self.finish().await;
                return None;
            }
            if tokio::time::timeout(limit - quiet, self.wait())
                .await
                .is_ok()
            {
                return Some(self.finish().await);
            }
        }
    }

    /// 等它退出，再给读输出的任务一点时间读完最后几行（留在管道里的孙进程不拖住这里）
    pub async fn finish(mut self) -> Exit {
        let exit = self.handle.wait().await;
        for reader in self.readers.drain(..) {
            let _ = tokio::time::timeout(Duration::from_secs(1), reader).await;
        }
        exit
    }
}

async fn wait_all(mut waits: Vec<watch::Receiver<Option<Exit>>>) {
    for wait in &mut waits {
        let _ = wait.wait_for(Option::is_some).await;
    }
}

fn read_lines<R: AsyncRead + Unpin + Send + 'static>(
    stream: R,
    kind: Kind,
    which: Stream,
    sink: Sink,
    heard: Arc<Mutex<Instant>>,
) -> JoinHandle<()> {
    let target = format!("{}{}", crate::logfile::CHILD_TARGET, kind.name());
    tokio::spawn(async move {
        let mut reader = BufReader::new(stream);
        let mut bytes = Vec::new();
        loop {
            bytes.clear();
            match reader.read_until(b'\n', &mut bytes).await {
                Ok(0) => break,
                Ok(_) => {
                    let text = String::from_utf8_lossy(&bytes);
                    let line = text.trim_end_matches(['\n', '\r']);
                    *heard.lock().unwrap_or_else(|p| p.into_inner()) = Instant::now();
                    log::info!(target: &target, "{line}");
                    sink(kind, which, line);
                }
                Err(error) => {
                    log::warn!("child.read_failed kind={} error={error}", kind.name());
                    break;
                }
            }
        }
    })
}

/// 一个子进程的看守：等根进程退出；被要求收拾时收拾整棵树；根进程走了把同组 / 同 Job 里剩下的也收掉
async fn own(
    mut child: Box<dyn ChildWrapper>,
    mut kill: oneshot::Receiver<()>,
    exit: watch::Sender<Option<Exit>>,
    sup: Supervisor,
    id: u64,
    kind: Kind,
) {
    let pid = child.id();
    let mut asked = false;
    let mut killed = false;
    // 只等根进程，不用包装的 wait()：Windows 上它要等 Job 里的一切都退，serve 崩了留下的轮次会把这里拖住
    let mut tick = tokio::time::interval(POLL);
    let status = loop {
        tokio::select! {
            _ = tick.tick() => match child.try_wait() {
                Ok(Some(status)) => break Ok(status),
                Ok(None) => {}
                Err(error) => break Err(error),
            },
            asked_to_kill = &mut kill, if !asked => {
                asked = true;
                if asked_to_kill.is_ok() {
                    log::info!("child.kill_tree kind={} pid={pid:?}", kind.name());
                    killed = true;
                    kill_tree(child.as_mut(), pid).await;
                }
            }
        }
    };
    // 根进程走了：同组（Mac）的剩下的 SIGKILL；Windows 上丢掉 Job 的句柄，KILL_ON_JOB_CLOSE 收掉其余
    #[cfg(unix)]
    let _ = child.start_kill();
    drop(child);
    // 收拾掉的不报码：Windows 上 TerminateJobObject 会给根进程一个 1，看着像它自己失败了
    let code = match &status {
        Ok(_) if killed => None,
        Ok(status) => status.code(),
        Err(error) => {
            log::warn!("child.wait_failed kind={} error={error}", kind.name());
            None
        }
    };
    log::info!("child.exit kind={} pid={pid:?} code={code:?}", kind.name());
    sup.forget(id);
    exit.send_replace(Some(Exit { code }));
}

#[cfg(windows)]
async fn kill_tree(child: &mut dyn ChildWrapper, _pid: Option<u32>) {
    // TerminateJobObject：Job 里的一切，连同后端每棵树自己的子 Job
    if let Err(error) = child.start_kill() {
        log::warn!("child.terminate_job_failed error={error}");
    }
}

#[cfg(unix)]
async fn kill_tree(child: &mut dyn ChildWrapper, pid: Option<u32>) {
    use nix::sys::signal::{Signal, kill};
    use nix::unistd::Pid;

    if let Some(root) = pid {
        let _ = kill(Pid::from_raw(root as i32), Signal::SIGSTOP); // 停住：收拾的这一会儿不再起新进程
        for _ in 0..3 {
            let doomed = match process_table().await {
                Ok(table) => descendants_leaf_first(&table, root),
                Err(error) => {
                    log::warn!("child.ps_failed error={error}");
                    break;
                }
            };
            if doomed.is_empty() {
                break;
            }
            for pid in doomed {
                let _ = kill(Pid::from_raw(pid as i32), Signal::SIGKILL);
            }
        }
    }
    if let Err(error) = child.start_kill() {
        log::warn!("child.killpg_failed error={error}");
    }
}

/// 整张进程表的（pid，父 pid）
#[cfg(unix)]
async fn process_table() -> io::Result<Vec<(u32, u32)>> {
    let out = tokio::process::Command::new("/bin/ps")
        .args(["-A", "-o", "pid=", "-o", "ppid="])
        .output()
        .await?;
    let text = String::from_utf8_lossy(&out.stdout);
    Ok(text
        .lines()
        .filter_map(|line| {
            let mut fields = line.split_whitespace().map(str::parse::<u32>);
            Some((fields.next()?.ok()?, fields.next()?.ok()?))
        })
        .collect())
}

/// `root` 的所有后代，叶子在前（先杀子再杀父：父先死，子就被 launchd 收养、顺父子关系找不到了）
pub fn descendants_leaf_first(table: &[(u32, u32)], root: u32) -> Vec<u32> {
    fn visit(table: &[(u32, u32)], parent: u32, out: &mut Vec<u32>, depth: usize) {
        if depth > 64 {
            return; // 进程表里的环（pid 复用的瞬间）不会无限往下走
        }
        for &(pid, ppid) in table {
            if ppid == parent && pid != parent {
                visit(table, pid, out, depth + 1);
                out.push(pid);
            }
        }
    }
    let mut out = Vec::new();
    visit(table, root, &mut out, 0);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn descendants_are_killed_from_the_leaves_up() {
        // 1 是 launchd；10 是 serve；11、12 是两轮对话的 CLI；13 是 11 起的 bash；20 是别人的
        let table = [
            (1, 0),
            (10, 1),
            (11, 10),
            (12, 10),
            (13, 11),
            (20, 1),
            (21, 20),
        ];
        let order = descendants_leaf_first(&table, 10);
        assert_eq!(order.len(), 3); // 11、12、13
        assert!(order.iter().position(|&p| p == 13) < order.iter().position(|&p| p == 11));
        assert!(!order.contains(&10) && !order.contains(&20) && !order.contains(&21));
        assert!(descendants_leaf_first(&table, 99).is_empty());
    }
}
