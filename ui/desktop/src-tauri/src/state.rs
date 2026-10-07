//! 外壳自己记的几件事：一个 `shell.json`，在系统给 App 的配置目录里（标识 `com.zephyrxiang.aaai4s`，
//! 卸载 App 时可以一起删；平台的家 `~/.ai4sci` 外壳不往里写东西）。
//!
//! 文件坏了或不在当作什么都没记：这里的每一项丢了都只是多做一次（重跑 setup、换一次端口、重取 PATH）。

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

pub const FILE_NAME: &str = "shell.json";

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Remembered {
    /// 上次用的端口：页面的主题等存在 localStorage，按来源（含端口）分（spec §4 第 7 步）
    #[serde(default)]
    pub port: Option<u16>,
    /// 跑通过 setup 的那一版平台（§4 第 6 步）：换了版本才再跑
    #[serde(default)]
    pub setup_ok: Option<String>,
    /// 上次从登录 shell 取到的 PATH（§3）：这次 3 秒内没取到就用它
    #[serde(default)]
    pub login_path: Option<String>,
    /// 上次查新版本的时刻（Unix 秒）：Mac 上收起后点 Dock 回来，隔了一天才再查（§4 第 10 步）
    #[serde(default)]
    pub checked_at: Option<u64>,
}

pub struct Store {
    path: PathBuf,
    lock: Mutex<()>,
}

impl Store {
    pub fn new(dir: &Path) -> Self {
        Self {
            path: dir.join(FILE_NAME),
            lock: Mutex::new(()),
        }
    }

    pub fn load(&self) -> Remembered {
        let _guard = self
            .lock
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        self.read()
    }

    fn read(&self) -> Remembered {
        match fs::read(&self.path) {
            Ok(bytes) => serde_json::from_slice(&bytes).unwrap_or_else(|error| {
                log::warn!(
                    "state.unreadable path={} error={error}",
                    self.path.display()
                );
                Remembered::default()
            }),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Remembered::default(),
            Err(error) => {
                log::warn!(
                    "state.unreadable path={} error={error}",
                    self.path.display()
                );
                Remembered::default()
            }
        }
    }

    /// 读、改、整体写回（先写临时文件再改名，写一半断电不会留下半个文件）
    pub fn update(&self, change: impl FnOnce(&mut Remembered)) {
        let _guard = self
            .lock
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let mut remembered = self.read();
        change(&mut remembered);
        if let Err(error) = self.write(&remembered) {
            log::warn!(
                "state.unwritable path={} error={error}",
                self.path.display()
            );
        }
    }

    fn write(&self, remembered: &Remembered) -> io::Result<()> {
        if let Some(dir) = self.path.parent() {
            fs::create_dir_all(dir)?;
        }
        let tmp = self.path.with_extension("json.tmp");
        fs::write(&tmp, serde_json::to_vec_pretty(remembered)?)?;
        fs::rename(&tmp, &self.path)
    }
}

pub fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn what_is_remembered_survives_and_a_broken_file_is_forgotten() {
        let dir = std::env::temp_dir().join(format!("aaai4s-state-{}", std::process::id()));
        let store = Store::new(&dir);
        assert_eq!(store.load(), Remembered::default());
        store.update(|r| r.port = Some(51234));
        store.update(|r| r.setup_ok = Some("1.9.0".into()));
        assert_eq!(store.load().port, Some(51234));
        assert_eq!(store.load().setup_ok.as_deref(), Some("1.9.0"));
        fs::write(dir.join(FILE_NAME), "{not json").unwrap();
        assert_eq!(store.load(), Remembered::default());
        fs::remove_dir_all(dir).unwrap();
    }
}
