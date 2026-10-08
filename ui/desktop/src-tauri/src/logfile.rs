//! 外壳的日志：系统给 App 的日志目录里一个 `shell.log`，过 5 MB 换成 `shell.log.1` 重写。
//!
//! 走 `log` 门面。外壳自己的事件 target 是模块名（`aaai4s::serve`），消息写「事件名 键=值」；子进程的
//! 每一行 target 是 `child.<哪个>`、原样记下（spec §4：子进程的 stdout、stderr 一直读，写进外壳的日志）；
//! 依赖库只记 WARN 以上。不记传给子进程的环境、不记登录 shell 的原始输出（用户 rc 里常 export key）。

use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use log::{Level, LevelFilter, Log, Metadata, Record};
use time::OffsetDateTime;
use time::format_description::well_known::Rfc3339;

pub const FILE_NAME: &str = "shell.log";
pub const CHILD_TARGET: &str = "child.";
const ROTATE_AT: u64 = 5 * 1024 * 1024;

struct FileLog {
    path: PathBuf,
    file: Mutex<Option<(File, u64)>>,
}

/// 装上全局日志，返回日志文件的路径（「打开日志」要它）。
pub fn init(dir: &Path) -> io::Result<PathBuf> {
    fs::create_dir_all(dir)?;
    let path = dir.join(FILE_NAME);
    let opened = open(&path)?;
    let logger = FileLog {
        path: path.clone(),
        file: Mutex::new(Some(opened)),
    };
    log::set_boxed_logger(Box::new(logger)).map_err(io::Error::other)?;
    log::set_max_level(LevelFilter::Info);
    Ok(path)
}

fn open(path: &Path) -> io::Result<(File, u64)> {
    let file = OpenOptions::new().create(true).append(true).open(path)?;
    let size = file.metadata()?.len();
    Ok((file, size))
}

fn ours(target: &str) -> bool {
    target.starts_with("aaai4s")
        || target.starts_with(CHILD_TARGET)
        || target.starts_with("tauri_plugin_updater")
}

impl FileLog {
    fn write_line(&self, line: &str) -> io::Result<()> {
        let mut guard = self
            .file
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if guard.as_ref().is_some_and(|(_, size)| *size >= ROTATE_AT) {
            *guard = None; // 先关掉再改名：Windows 上开着的文件改不了名
            fs::rename(&self.path, self.path.with_extension("log.1"))?;
        }
        if guard.is_none() {
            *guard = Some(open(&self.path)?);
        }
        let (file, size) = guard.as_mut().expect("刚打开");
        file.write_all(line.as_bytes())?;
        *size += line.len() as u64;
        Ok(())
    }
}

impl Log for FileLog {
    fn enabled(&self, metadata: &Metadata) -> bool {
        metadata.level() <= Level::Warn
            || (metadata.level() <= Level::Info && ours(metadata.target()))
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        let stamp = OffsetDateTime::now_utc()
            .format(&Rfc3339)
            .unwrap_or_default();
        let stamp = stamp.get(..19).unwrap_or(&stamp);
        let line = format!(
            "{stamp}Z {} {} {}\n",
            record.level(),
            record.target(),
            record.args()
        );
        if cfg!(debug_assertions) {
            eprint!("{line}");
        }
        if let Err(error) = self.write_line(&line) {
            // 日志写不进去不能让 App 停下；源码桌面在终端里看得到
            eprintln!("aaai4s: 写不进日志 {}：{error}", self.path.display());
        }
    }

    fn flush(&self) {
        if let Some((file, _)) = self
            .file
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .as_mut()
        {
            let _ = file.flush();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_our_own_lines_are_kept_below_warnings() {
        assert!(ours("aaai4s::serve"));
        assert!(ours("child.serve"));
        assert!(ours("tauri_plugin_updater::updater"));
        assert!(!ours("reqwest::connect"));
        assert!(!ours("tao::platform_impl"));
    }

    #[test]
    fn the_file_starts_over_past_five_megabytes() {
        let dir = std::env::temp_dir().join(format!("aaai4s-log-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join(FILE_NAME);
        fs::write(&path, vec![b'x'; ROTATE_AT as usize]).unwrap();
        let log = FileLog {
            path: path.clone(),
            file: Mutex::new(Some(open(&path).unwrap())),
        };
        log.write_line("next\n").unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "next\n");
        assert_eq!(
            fs::metadata(path.with_extension("log.1")).unwrap().len(),
            ROTATE_AT
        );
        fs::remove_dir_all(dir).unwrap();
    }
}
