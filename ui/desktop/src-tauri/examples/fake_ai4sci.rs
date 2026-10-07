//! 假的 `ai4sci`：外壳的集成测试（`tests/supervise.rs`）与手动验收（README「怎么测」）用。
//!
//! 只会外壳认的那几句（`src/contract.rs`）：`--version`、`setup --no-serve --no-input`、
//! `serve --host H --port N --until-stdin-closes`。serve 真的 listen、打 `ok` 那一行、端一个小页面与
//! `/health`，再起一个自成进程组的「对话轮次」（`sleep`），标准输入关了就先停掉它再退出——与真 serve
//! 的 `--until-stdin-closes` 一样。行为由环境变量调：
//!
//!   FAKE_AI4SCI_VERSION     `--version` 报的版本（缺省 1.9.0）
//!   FAKE_AI4SCI_PORT_BUSY   这个端口当作被占，serve 退 3
//!   FAKE_AI4SCI_STUBBORN    serve 不理标准输入关闭，逼外壳收拾整棵树
//!   FAKE_AI4SCI_TURNS       `/health` 报的在跑轮数（缺省 0）
//!   FAKE_AI4SCI_SETUP_EXIT  setup 的退出码（缺省 0）
//!   FAKE_AI4SCI_SLOW_MS     setup 每行之间停多久（缺省 400）

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::{Command, Stdio};
use std::time::Duration;

fn var(name: &str) -> Option<String> {
    std::env::var(name).ok().filter(|v| !v.is_empty())
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = match args.first().map(String::as_str) {
        Some("--version") => {
            println!(
                "ai4sci {}",
                var("FAKE_AI4SCI_VERSION").unwrap_or_else(|| "1.9.0".into())
            );
            0
        }
        Some("setup") if args[1..] == ["--no-serve", "--no-input"] => setup(),
        Some("serve") => serve(&args),
        Some("sleep") => {
            std::thread::sleep(Duration::from_secs(600));
            0
        }
        _ => {
            eprintln!("fake ai4sci: 不认识 {args:?}");
            2
        }
    };
    std::process::exit(code);
}

fn setup() -> i32 {
    let pause = Duration::from_millis(
        var("FAKE_AI4SCI_SLOW_MS")
            .and_then(|v| v.parse().ok())
            .unwrap_or(400),
    );
    for line in [
        "  ✓ git           已装，跳过",
        "  … Claude Code   下载中",
        "  ↓ Claude Code   已下 40 MB / 共 224 MB",
        "  ↓ Claude Code   已下 160 MB / 共 224 MB",
        "  ✓ Claude Code   2.1.0，装好了",
        "  ✓ Codex         0.50.0，装好了",
    ] {
        println!("{line}");
        eprintln!("INFO ai4sci.setup a log line");
        std::thread::sleep(pause);
    }
    var("FAKE_AI4SCI_SETUP_EXIT")
        .and_then(|v| v.parse().ok())
        .unwrap_or(0)
}

fn flag<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    args.iter()
        .position(|a| a == name)
        .and_then(|at| args.get(at + 1))
        .map(String::as_str)
}

fn serve(args: &[String]) -> i32 {
    let (Some(host), Some(port), true) = (
        flag(args, "--host"),
        flag(args, "--port").and_then(|p| p.parse::<u16>().ok()),
        args.iter().any(|a| a == "--until-stdin-closes"),
    ) else {
        eprintln!("fake ai4sci serve: 参数不对 {args:?}");
        return 2;
    };
    if port != 0 && var("FAKE_AI4SCI_PORT_BUSY") == Some(port.to_string()) {
        eprintln!("端口 {port} 用不了");
        return 3;
    }
    let listener = match TcpListener::bind((host, port)) {
        Ok(listener) => listener,
        Err(error) => {
            eprintln!("端口 {port} 用不了：{error}");
            return 3;
        }
    };
    let port = listener.local_addr().map(|a| a.port()).unwrap_or(port);
    let turn = match start_turn() {
        Ok(turn) => turn,
        Err(error) => {
            eprintln!("起不了对话轮次：{error}");
            return 1;
        }
    };
    eprintln!("turn {}", turn.id());
    println!("ok http://{host}:{port}\thome=-\tui=-");
    let _ = std::io::stdout().flush();
    // 一个连接一个线程：WebKit 会先开一条不发请求的预连接，挨个处理就被它堵住半分钟
    std::thread::spawn(move || {
        for stream in listener.incoming().flatten() {
            std::thread::spawn(move || answer(stream, port));
        }
    });
    let _ = std::io::stdin().read_to_end(&mut Vec::new());
    if var("FAKE_AI4SCI_STUBBORN").is_some() {
        say("标准输入关了，不理");
        loop {
            std::thread::sleep(Duration::from_secs(3600));
        }
    }
    // 先停轮次再说话：外壳崩了的时候管道另一头已经没人，写 stderr 会失败
    let mut turn = turn;
    let _ = turn.kill();
    let _ = turn.wait();
    say("标准输入关了：停掉在跑的轮次，退出");
    0
}

/// 写 stderr 不许失败就退：外壳死了以后管道断了，`eprintln!` 会 panic、把收拾打断
fn say(line: &str) {
    let _ = writeln!(std::io::stderr(), "{line}");
}

/// 一轮对话：真 serve 里它们各自一个会话，serve 所在的进程组够不着
fn start_turn() -> std::io::Result<std::process::Child> {
    let mut cmd = Command::new(std::env::current_exe()?);
    cmd.arg("sleep")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(unix)]
    std::os::unix::process::CommandExt::process_group(&mut cmd, 0);
    cmd.spawn()
}

fn answer(mut stream: TcpStream, port: u16) {
    let mut request = String::new();
    if BufReader::new(&stream).read_line(&mut request).is_err() {
        return;
    }
    let path = request.split_whitespace().nth(1).unwrap_or("/");
    say(&format!("GET {path}"));
    let turns = var("FAKE_AI4SCI_TURNS")
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(0);
    let (kind, extra, body) = match path {
        "/health" => (
            "application/json",
            "",
            format!("{{\"ok\": true, \"checks_ok\": true, \"turns\": {turns}}}"),
        ),
        "/notes.txt" => (
            "text/plain; charset=utf-8",
            "Content-Disposition: attachment; filename=\"notes.txt\"\r\n",
            "假的下载\n".to_string(),
        ),
        _ => ("text/html; charset=utf-8", "", page(port)),
    };
    let head = format!(
        "HTTP/1.0 200 OK\r\nContent-Type: {kind}\r\n{extra}Content-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    );
    let _ = stream.write_all(head.as_bytes());
    let _ = stream.write_all(body.as_bytes());
}

fn page(port: u16) -> String {
    format!(
        "<!doctype html><meta charset=utf-8><title>假的平台</title>\
         <body style=\"font:16px system-ui;padding:40px;line-height:2\">\
         <h1>假的平台页面</h1><p>端口 {port}</p><ul>\
         <li><a href=\"https://example.com/\" target=\"_blank\">外链（新窗口）：系统浏览器打开</a>\
         <li><a href=\"https://example.com/same\">外链（本窗口）：系统浏览器打开</a>\
         <li><a href=\"mailto:someone@example.com\">邮件</a>\
         <li><a href=\"file:///etc/hosts\">file: 链接：拒</a>\
         <li><a href=\"tauri://localhost/index.html\">回启动页：拒</a>\
         <li><a href=\"/notes.txt\">下载一个文件</a>\
         <li><a href=\"/health\">/health</a></ul></body>"
    )
}
