//! 版本：外壳只有这一个解析函数（spec §3「版本写法」）。
//!
//! `ai4sci --version` 打的是 PEP 440（rc 写成 `1.9.0rc1`），tag、外壳与 CDN 上的目录用 SemVer
//! （`1.9.0-rc.1`）；两种写法都认，比较时是同一个东西。下限（`MIN_PLATFORM`、`min_desktop`）按号比：
//! 同号的 rc 算满足这个号的下限，rc 外壳才装得上自己那一版的平台。

use std::cmp::Ordering;
use std::fmt;

/// 预发布的种类，按先后排：PEP 440 的 `.devN` < `aN` < `bN` < `rcN` < 正式版 < `.postN`
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum Stage {
    Dev,
    Alpha,
    Beta,
    Rc,
    Final,
    Post,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Version {
    release: [u64; 3],
    stage: Stage,
    number: u64,
}

#[derive(Debug, PartialEq, Eq)]
pub struct VersionError(String);

impl fmt::Display for VersionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "看不懂的版本号：{}", self.0)
    }
}

impl std::error::Error for VersionError {}

impl Version {
    /// `1.9.0`、`1.9.0rc1`、`1.9.0-rc.1`、`1.9.0.dev3+g1234`；本地段（`+…`）不参与比较
    pub fn parse(raw: &str) -> Result<Self, VersionError> {
        let bad = || VersionError(raw.to_string());
        let text = raw.trim().trim_start_matches('v');
        let text = text.split('+').next().unwrap_or_default();
        let digits = text
            .find(|c: char| !c.is_ascii_digit() && c != '.')
            .unwrap_or(text.len());
        let head = text[..digits].trim_end_matches('.');
        let tail = &text[head.len()..];
        let mut release = [0u64; 3];
        let parts: Vec<&str> = head.split('.').collect();
        if parts.len() != 3 {
            return Err(bad());
        }
        for (slot, part) in release.iter_mut().zip(&parts) {
            *slot = part.parse().map_err(|_| bad())?;
        }
        let (stage, number) = suffix(tail).ok_or_else(bad)?;
        Ok(Self {
            release,
            stage,
            number,
        })
    }

    pub fn is_prerelease(&self) -> bool {
        self.stage < Stage::Final
    }

    /// 是否满足下限 `floor`：只比号，同号的预发布也算满足
    pub fn meets(&self, floor: &Version) -> bool {
        self.release >= floor.release
    }
}

/// 号后面那一段：空、PEP 440 的 `rc1` `a1` `b1` `.dev1` `.post1`、SemVer 的 `-rc.1` `-alpha.1` `-beta.1`
fn suffix(tail: &str) -> Option<(Stage, u64)> {
    if tail.is_empty() {
        return Some((Stage::Final, 0));
    }
    let tail = tail.trim_start_matches(['-', '.']);
    let split = tail.find(|c: char| c.is_ascii_digit())?;
    let (word, number) = tail.split_at(split);
    let stage = match word.trim_end_matches('.') {
        "dev" => Stage::Dev,
        "a" | "alpha" => Stage::Alpha,
        "b" | "beta" => Stage::Beta,
        "rc" => Stage::Rc,
        "post" => Stage::Post,
        _ => return None,
    };
    Some((stage, number.parse().ok()?))
}

impl Ord for Version {
    fn cmp(&self, other: &Self) -> Ordering {
        (self.release, self.stage, self.number).cmp(&(other.release, other.stage, other.number))
    }
}

impl PartialOrd for Version {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl fmt::Display for Version {
    /// SemVer 写法：CDN 上带版本号的目录就是这样拼的（`<DIST>/1.9.0-rc.1/install.sh`）
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let [major, minor, patch] = self.release;
        write!(f, "{major}.{minor}.{patch}")?;
        match self.stage {
            Stage::Final => Ok(()),
            Stage::Dev => write!(f, "-dev.{}", self.number),
            Stage::Alpha => write!(f, "-alpha.{}", self.number),
            Stage::Beta => write!(f, "-beta.{}", self.number),
            Stage::Rc => write!(f, "-rc.{}", self.number),
            Stage::Post => write!(f, "-post.{}", self.number),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(raw: &str) -> Version {
        Version::parse(raw).unwrap()
    }

    #[test]
    fn both_spellings_of_a_release_candidate_are_the_same_version() {
        assert_eq!(v("1.9.0rc1"), v("1.9.0-rc.1"));
        assert_eq!(v("1.9.0b2"), v("1.9.0-beta.2"));
        assert_eq!(v("v1.9.0"), v("1.9.0"));
        assert_eq!(v("1.9.0rc1").to_string(), "1.9.0-rc.1");
    }

    #[test]
    fn versions_order_like_pep_440() {
        let order = [
            "1.8.0",
            "1.9.0.dev3",
            "1.9.0a1",
            "1.9.0b1",
            "1.9.0rc1",
            "1.9.0rc2",
            "1.9.0",
            "1.9.0.post1",
            "1.9.1",
            "1.10.0",
        ];
        for pair in order.windows(2) {
            assert!(v(pair[0]) < v(pair[1]), "{} < {}", pair[0], pair[1]);
        }
        assert!(v("1.8.1.dev3+g3d12220") > v("1.8.0"));
    }

    #[test]
    fn a_release_candidate_meets_the_floor_of_its_own_number() {
        let floor = v("1.9.0");
        assert!(v("1.9.0rc1").meets(&floor));
        assert!(v("1.9.0").meets(&floor));
        assert!(v("1.9.1").meets(&floor));
        assert!(!v("1.8.9").meets(&floor));
        assert!(!v("1.9.0rc1").meets(&v("1.9.1")));
    }

    #[test]
    fn only_versions_before_the_release_are_prereleases() {
        assert!(v("1.9.0-rc.1").is_prerelease());
        assert!(v("1.9.0.dev1").is_prerelease());
        assert!(!v("1.9.0").is_prerelease());
        assert!(!v("1.9.0.post1").is_prerelease());
    }

    #[test]
    fn what_the_cli_prints_when_it_is_not_installed_is_not_a_version() {
        for raw in [
            "未知",
            "",
            "1.9",
            "1.9.0.1",
            "1.9.0-rc",
            "1.9.0-gamma.1",
            "1.x.0",
            "1.9.0rc1junk",
        ] {
            assert!(Version::parse(raw).is_err(), "{raw}");
        }
    }
}
