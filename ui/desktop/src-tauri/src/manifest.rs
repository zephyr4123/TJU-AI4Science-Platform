//! 最新是哪一版（spec §3）：`<DIST>/platform.json` 与 `platform.json.sig`；每一版（rc 也是）另有一份
//! 带版本号的 `<DIST>/<版本>/platform.json(.sig)`，装那一版之前照它核脚本。
//!
//! 签名用更新器那把 key（`.sig` 与更新包的一样：minisign 签名全文的 base64），公钥就是 tauri.conf.json
//! 里更新器那一把，外壳没有第二份。验不过当作取不到：外壳每次打开都可能无人值守地跑装平台的脚本，
//! 脚本的 sha256 只认签过的这一份。

use std::time::Duration;

use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use minisign_verify::{PublicKey, Signature};
use serde::Deserialize;
use url::Url;

use crate::contract::{INSTALL_PS1, INSTALL_SH, MANIFEST_NAME, MANIFEST_SIG_NAME, WHEEL_KEY};
use crate::version::Version;

/// 取清单的总时限（spec §4 第 3 步）
pub const FETCH_TIMEOUT: Duration = Duration::from_secs(4);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Manifest {
    pub version: Version,
    /// 后端要求的最低外壳版本
    pub min_desktop: Version,
    pub install_sh: String,
    pub install_ps1: String,
    pub wheel: String,
}

#[derive(Deserialize)]
struct Raw {
    version: String,
    min_desktop: String,
    sha256: std::collections::HashMap<String, String>,
}

impl Manifest {
    /// 这台机器上跑的那份安装脚本的 sha256
    pub fn script_sha256(&self) -> &str {
        if cfg!(windows) {
            &self.install_ps1
        } else {
            &self.install_sh
        }
    }
}

fn decode_base64_text(what: &str, b64: &str) -> Result<String, String> {
    let bytes = STANDARD
        .decode(b64.trim())
        .map_err(|error| format!("{what} 不是 base64：{error}"))?;
    String::from_utf8(bytes).map_err(|_| format!("{what} 不是文本"))
}

/// 验签、解析：签名对不上、缺键、版本写法不对，都不认
pub fn verify(body: &[u8], signature: &str, pubkey: &str) -> Result<Manifest, String> {
    let key = PublicKey::decode(&decode_base64_text("公钥", pubkey)?)
        .map_err(|error| format!("公钥读不出：{error}"))?;
    let sig = Signature::decode(&decode_base64_text(MANIFEST_SIG_NAME, signature)?)
        .map_err(|error| format!("{MANIFEST_SIG_NAME} 读不出：{error}"))?;
    key.verify(body, &sig, true)
        .map_err(|error| format!("{MANIFEST_NAME} 的签名对不上：{error}"))?;
    let raw: Raw =
        serde_json::from_slice(body).map_err(|error| format!("{MANIFEST_NAME} 读不出：{error}"))?;
    let hash = |key: &str| -> Result<String, String> {
        let value = raw
            .sha256
            .get(key)
            .ok_or_else(|| format!("{MANIFEST_NAME} 缺 sha256.{key}"))?;
        let ok = value.len() == 64 && value.bytes().all(|b| b.is_ascii_hexdigit());
        if ok {
            Ok(value.to_ascii_lowercase())
        } else {
            Err(format!("{MANIFEST_NAME} 的 sha256.{key} 不是 sha256"))
        }
    };
    Ok(Manifest {
        version: Version::parse(&raw.version).map_err(|e| e.to_string())?,
        min_desktop: Version::parse(&raw.min_desktop).map_err(|e| e.to_string())?,
        install_sh: hash(INSTALL_SH)?,
        install_ps1: hash(INSTALL_PS1)?,
        wheel: hash(WHEEL_KEY)?,
    })
}

/// 最新的那份：取清单与签名、验过才算取到；连不上、超时、验不过都是 Err（启动页照常往下走）
pub async fn fetch(client: &reqwest::Client, dist: &Url, pubkey: &str) -> Result<Manifest, String> {
    fetch_at(client, dist, pubkey).await
}

/// 取到的「最新」能不能信：签名只说明是我们签的，不说明是最新的。每一版（rc 也算）都有一份签过的
/// `<版本>/platform.json`，能写桶的人把它或旧正式版的拷成最新的，验签照样过：最新的不会是预发布，
/// 也不会比这个外壳见过的旧
pub fn latest_ok(manifest: &Manifest, seen: Option<&Version>) -> Result<(), String> {
    if manifest.version.is_prerelease() {
        return Err(format!(
            "最新的 {MANIFEST_NAME} 写的是预发布 {}",
            manifest.version
        ));
    }
    match seen {
        Some(seen) if &manifest.version < seen => Err(format!(
            "最新的 {MANIFEST_NAME} 写的是 {}，比见过的 {seen} 旧",
            manifest.version
        )),
        _ => Ok(()),
    }
}

/// 某一版自己那份（预发布的外壳装它自己那一版时用）；清单里写的版本必须就是这一版
pub async fn fetch_version(
    client: &reqwest::Client,
    dist: &Url,
    version: &Version,
    pubkey: &str,
) -> Result<Manifest, String> {
    let base = dist
        .join(&format!("{}/", version.pep440()))
        .map_err(|error| error.to_string())?;
    let manifest = fetch_at(client, &base, pubkey).await?;
    if &manifest.version != version {
        return Err(format!(
            "{base}{MANIFEST_NAME} 写的是 {}，不是 {version}",
            manifest.version
        ));
    }
    Ok(manifest)
}

async fn fetch_at(client: &reqwest::Client, dist: &Url, pubkey: &str) -> Result<Manifest, String> {
    let get = |name: &'static str| async move {
        let url = dist.join(name).map_err(|error| error.to_string())?;
        let resp = client
            .get(url.clone())
            .send()
            .await
            .map_err(|error| format!("取不到 {url}：{}", error.without_url()))?;
        let resp = resp
            .error_for_status()
            .map_err(|error| format!("取不到 {url}：{}", error.without_url()))?;
        resp.bytes()
            .await
            .map_err(|error| format!("取不到 {url}：{}", error.without_url()))
    };
    let both = async { tokio::try_join!(get(MANIFEST_NAME), get(MANIFEST_SIG_NAME)) };
    let (body, sig) = tokio::time::timeout(FETCH_TIMEOUT, both)
        .await
        .map_err(|_| format!("{} 秒内没取到 {MANIFEST_NAME}", FETCH_TIMEOUT.as_secs()))??;
    verify(&body, &String::from_utf8_lossy(&sig), pubkey)
}

#[cfg(test)]
mod tests {
    use super::*;

    // 用一把只给测试的 key 签的（`tauri signer generate` / `tauri signer sign`），私钥没进仓
    const BODY: &str = include_str!("../tests/fixtures/manifest/platform.json");
    const SIG: &str = include_str!("../tests/fixtures/manifest/platform.json.sig");
    const KEY: &str = include_str!("../tests/fixtures/manifest/test-key.pub");
    const RELEASE_KEY: &str = "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEUzNjU0MzI3RTRFRUQxMDYKUldRRzBlN2tKME5sNDlSZzU3UTByV0o5RmUvSk8xUGZHRjlNZTRFYWlvVk1Od0FiVXhxWU5VTkIK";

    #[test]
    fn a_signed_manifest_is_read() {
        let manifest = verify(BODY.as_bytes(), SIG, KEY).unwrap();
        assert_eq!(manifest.version, Version::parse("1.9.0").unwrap());
        assert_eq!(manifest.min_desktop, Version::parse("1.9.0").unwrap());
        assert_eq!(manifest.install_sh, "a".repeat(64));
        assert_eq!(manifest.wheel, "c".repeat(64));
    }

    #[test]
    fn one_changed_byte_or_another_key_is_refused() {
        let tampered = BODY.replace("\"1.9.0\", \"min_desktop\"", "\"9.9.0\", \"min_desktop\"");
        assert_ne!(tampered, BODY);
        assert!(
            verify(tampered.as_bytes(), SIG, KEY)
                .unwrap_err()
                .contains("签名对不上")
        );
        assert!(verify(BODY.as_bytes(), SIG, RELEASE_KEY).is_err());
        assert!(verify(BODY.as_bytes(), "not base64!", KEY).is_err());
    }

    #[test]
    fn a_replayed_manifest_is_not_taken_as_the_latest() {
        let manifest = |raw: &str| Manifest {
            version: Version::parse(raw).unwrap(),
            min_desktop: Version::parse("1.9.0").unwrap(),
            install_sh: String::new(),
            install_ps1: String::new(),
            wheel: String::new(),
        };
        let seen = Version::parse("1.9.2").unwrap();
        assert!(latest_ok(&manifest("1.9.2"), Some(&seen)).is_ok());
        assert!(latest_ok(&manifest("1.10.0"), Some(&seen)).is_ok());
        assert!(latest_ok(&manifest("1.9.0"), None).is_ok());
        assert!(
            latest_ok(&manifest("1.9.1"), Some(&seen)).is_err(),
            "放回的旧正式版"
        );
        assert!(
            latest_ok(&manifest("1.10.0rc1"), None).is_err(),
            "拷过来的 rc"
        );
    }

    #[test]
    fn the_shipped_key_is_the_updater_key() {
        let conf: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        assert_eq!(conf["plugins"]["updater"]["pubkey"], RELEASE_KEY);
        assert!(PublicKey::decode(&decode_base64_text("公钥", RELEASE_KEY).unwrap()).is_ok());
    }
}
