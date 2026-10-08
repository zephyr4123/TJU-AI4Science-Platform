//! 进度行（spec §3 setup）：安装脚本与 setup 一行一项 `  <标记> <标签> <说明>`，标签按 14 列补齐。
//! 启动页一个标签一行：同一标签后来的行就地换掉前面的（`↓` 的已下多少一直在变，最后变成 `✓`）。

use serde::Serialize;

use crate::contract::MARKS;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Row {
    pub mark: String,
    pub label: String,
    pub note: String,
}

/// 不是进度行（日志、空行、别的输出）就是 None：只进日志，不上启动页
pub fn parse(line: &str) -> Option<Row> {
    let rest = line.strip_prefix("  ")?;
    let mark = MARKS.iter().find(|mark| rest.starts_with(**mark))?;
    let rest = rest[mark.len()..].strip_prefix(' ')?.trim_end();
    if rest.trim().is_empty() || rest.starts_with(' ') {
        return None;
    }
    // 标签与说明之间是补齐的空格（至少两个）；标签里可以有一个空格（Claude Code）
    let (label, note) = match rest.find("  ") {
        Some(at) => (&rest[..at], rest[at..].trim()),
        None => rest.split_once(' ').unwrap_or((rest, "")),
    };
    Some(Row {
        mark: mark.to_string(),
        label: label.to_string(),
        note: note.trim().to_string(),
    })
}

/// 把一行并进启动页的清单：同一标签换掉，新标签接在后面
pub fn merge(rows: &mut Vec<Row>, row: Row) {
    match rows.iter_mut().find(|r| r.label == row.label) {
        Some(same) => *same = row,
        None => rows.push(row),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(mark: &str, label: &str, note: &str) -> Row {
        Row {
            mark: mark.into(),
            label: label.into(),
            note: note.into(),
        }
    }

    #[test]
    fn the_lines_of_the_install_script_and_setup_are_read() {
        assert_eq!(
            parse("  ✓ uv            已装，跳过"),
            Some(row("✓", "uv", "已装，跳过"))
        );
        assert_eq!(
            parse("  ↓ Claude Code   已下 120 MB / 共 224 MB"),
            Some(row("↓", "Claude Code", "已下 120 MB / 共 224 MB"))
        );
        assert_eq!(
            parse("  … Codex         下载中"),
            Some(row("…", "Codex", "下载中"))
        );
        assert_eq!(
            parse("  ! git           装命令行工具的框弹出来了"),
            Some(row("!", "git", "装命令行工具的框弹出来了"))
        );
        assert_eq!(
            parse("  ✗ ai4sci        取不到 https://x/1.9.0/ai4sci.whl"),
            Some(row("✗", "ai4sci", "取不到 https://x/1.9.0/ai4sci.whl"))
        );
        assert_eq!(parse("  ✓ git"), Some(row("✓", "git", "")));
    }

    #[test]
    fn other_output_stays_in_the_log() {
        for line in [
            "",
            "2026-10-07 INFO ai4sci.setup start",
            "✓ uv 已装",
            "  ✓",
            "  ✓   ",
            "  * uv  done",
            "    ✓ uv  nested",
        ] {
            assert_eq!(parse(line), None, "{line:?}");
        }
    }

    #[test]
    fn a_label_keeps_one_row_that_updates_in_place() {
        let mut rows = Vec::new();
        for line in [
            "  ✓ git           已装，跳过",
            "  … Claude Code   下载中",
            "  ↓ Claude Code   已下 10 MB / 共 224 MB",
            "  ↓ Claude Code   已下 120 MB / 共 224 MB",
            "  ✓ Claude Code   装好了",
        ] {
            merge(&mut rows, parse(line).unwrap());
        }
        assert_eq!(
            rows,
            [
                row("✓", "git", "已装，跳过"),
                row("✓", "Claude Code", "装好了")
            ]
        );
    }
}
