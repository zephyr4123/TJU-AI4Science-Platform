"""外壳与后端的约定里后端这一侧的值（外层 #282，spec `docs/specs/desktop.md` §3）。

桌面 App 的外壳（`ui/desktop/`）只认 §3 那张表；表里外壳那一侧的常量集中在
`ui/desktop/src-tauri/src/contract.rs`，后端要声明的放这里，一处。这张表只加不改，不适用内测期例外
（已装的外壳跟不上 wheel）；要改走弃用周期。

`MIN_DESKTOP`：后端要求的最低外壳版本。发版时 `.github/scripts/cdn.py` 把它写进签名的
`dist/platform.json` 的 `min_desktop`；外壳低于它就先更新外壳、不升后端。约定改了、旧外壳跟不上
新后端时抬它。
"""

MIN_DESKTOP = "1.9.0"
