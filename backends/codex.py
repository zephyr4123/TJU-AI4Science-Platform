"""Codex 适配器：`codex exec --json`（执行层一次性会话）与 `codex exec resume`（协调层续接）。

每一条都是 2026-09-22 在本机实测的（codex-cli 0.147.0，ChatGPT Plus 账号登录），flag 与配置键先对过
官方文档（learn.chatgpt.com/docs/*，developers.openai.com/codex/* 308 跳过去）与源码
（github.com/openai/codex 的 rust-v0.147.0：exec/src/cli.rs、exec/src/exec_events.rs）；外层 #131。
2026-10-05 升到 0.160.0 后 live 复测过（探测、执行层写文件、协调层两轮续接，外层 #247）。

- **隔离的承重位是私有 `CODEX_HOME`**：平台的家里这家的目录（`Link.home`，框架给，外层 #263）。
  协调层用根、执行层用 `executor/` 子目录，因为 execpolicy 规则是按 home 放的、两层放行的命令不同。
  本机的 config.toml、plugins、MCP、hooks、memories、用户 skills 都不进；**登录是平台自己的**：
  在这个目录里 `codex login`（`login_command`），`auth.json` 落在根上，执行层的 `auth.json` 软链到
  根上那份（一次登录两层用；token 刷新写穿软链）。不再软链用户的 `~/.codex/auth.json`——平台的
  登录归平台，清除家时一起走。协调层的会话 rollout 也落在私有 home 下，续接靠它。
  `--ignore-user-config` 照带（自动化的官方开关）。
- **供应商**（外层 #266，0.160.0 实测）：官方登录在平台的 CODEX_HOME 里；OpenAI API 与第三方
  （DeepSeek、Kimi、自定义）走 `-c model_providers.ai4sci={base_url, wire_api="responses",
  env_key}` + `model_provider="ai4sci"`，第三方再给模型说明 `model_catalog_json`（cc-switch 的，见
  `backends/catalog/README.md`）。key 放进 `AI4SCI_PROVIDER_KEY` 交给 Codex；它缺省把整个环境透传给
  agent 跑的命令、带 KEY 的也不例外（实测看得见），所以 `shell_environment_policy.exclude` 挡掉它，
  挡完看不见。DeepSeek 冒烟：pong 约 $0.003。Kimi 没 key、未实测。
- **`ai4sci` 在沙箱外跑，其余命令都在沙箱里**：Codex 没有 Claude Code 那种按工具名的白名单，但
  execpolicy 的 `.rules` 能做「这个前缀的命令在沙箱外跑」（`prefix_rule(decision="allow")`，实测
  `/bin/zsh -lc 'ai4sci …'` 也命中、写到了 HOME 下）。端口的 `bash_rules`（协调层 `ai4sci`，执行层
  `ai4sci skill`）
  就翻成私有 home 的 `rules/ai4sci.rules`——与 Claude Code 的 `Bash(ai4sci *)` 一个模型：
  平台自己的 CLI 是放行的那扇门，能写平台自己的目录、能联网、起作业不嵌套沙箱；agent 敲的别的命令
  留在沙箱里（只能写工作区、没网）。所以不用 `--ignore-rules`，也不把平台的家加进可写根。
  嵌套的沙箱走不通：作业若在沙箱里起、里面的执行层 codex 连自己的可写根都写不进（实测 apply_patch
  「Operation not permitted」），这就是要把 `ai4sci` 放到沙箱外的原因。
- **skills 关不干净得自己关**：
`$HOME/.agents/skills` 与随包的 `.system/` 在私有 home 下照样被扫（实测
  88 个个人 skill 全进清单、一句 pong 19k tokens）；只有 `[[skills.config]] path=<SKILL.md 的路径>
  enabled=false` 关得掉（写目录路径不认），所以每次起会话现扫现关（`-c skills.config=[...]`），关完
  12k tokens、agent 自报「No skills available」。
- **沙箱**：`workspace-write` + `sandbox_workspace_write.writable_roots`（exec 与 resume 都认这个
`-c`；
  `--add-dir` resume 上没有）。工作区外、HOME 下的写「operation not permitted」退 1，`.git` 只读，
  `$TMPDIR` / `/tmp` 缺省可写；网络缺省关，留着关（联网的都走 `ai4sci`）。审批 exec 硬写 never，
  这里显式再带一遍。真门仍是框架事后的 `changed_files`。
- **事件**（`--json`，一行一个）：`thread.started{thread_id}`、`turn.started`、`item.started |
  item.updated | item.completed{item:{id,type,…}}`、`turn.completed{usage}`、
  `turn.failed{error.message}`、
  `error{message}`。item.type：agent_message{text}、reasoning{text}、command_execution{command,
  aggregated_output, exit_code, status}、file_change{changes:[{path,kind}], status}、mcp_tool_call、
  collab_tool_call、web_search{query, action}、todo_list、error{message}。**没有逐字事件**：
  一段话说完
  才来一条 agent_message，所以一段一条 `text`（端口注释里写明了这是 CLI 的限制）。被中断时既无
  turn.completed 也无 turn.failed，流直接断——收尾同时看 EOF。
- **prompt 一律从 stdin 喂**（位置参数 `-`）：stdin 不关它会一直等 EOF（实测挂了 15 分钟）；resume
  只在 `-` 时读 stdin，给了位置参数就静默丢掉管道里的内容。
- **续接**：`codex exec resume <thread_id> -` 加同一组 `-c`；`--ephemeral` 的线程续不了（no rollout
  found），协调层不带它、执行层带。resume 时 `developer_instructions` 不再生效（线程开头那份留着），
  指南变了由框架把变了的几节塞进话里。
- **指南**走 `-c developer_instructions="<TOML 字符串>"`：叠加在内置指令之外，不替换
  （`model_instructions_file` 是整体替换，官方不建议）；换行与中文实测都行。AGENTS.md 一律不读：
  `project_doc_max_bytes=0`。
- **联网搜索**：顶层 `web_search="live"`（`tools.web_search=true` 在 0.147 会被反序列化器丢掉），
  搜索在服务端，沙箱没网也通；事件是 `web_search` item。接 DeepSeek 写 `"disabled"`：它的 Responses
  API 忽略内置工具，实测模型说没有搜索工具（外层 #266）。
- **模型 / 深度**：`-m <slug>` + `-c model_reasoning_effort="<档>"`。0.160 随包的目录（二进制里的
  `models` 数组，外层 #247）按排序：gpt-6.1-sol（Latest workhorse，最低客户端 0.153）、gpt-6-astra
  （Frontier，0.153）、gpt-6-sol（Previous workhorse，0.155）、gpt-6-luna（Fast，0.155），往后是
  gpt-5.6-sol / terra / luna、gpt-5.5（Older / Legacy），都给 Plus。清单收四款：6.1 Sol、6 Astra、
  6 Luna，加 5.6 Terra——旧配置与旧对话只用过它，留着就不用迁移。四款共有 low / medium / high /
  xhigh（sol、astra、terra 另有 max、ultra，luna 有 max，不进清单，`Knobs.check` 才守得住）。
  slug 写错是服务端 400：`error` + `turn.failed`，退出码 1。
- **成本**：ChatGPT 订阅报不出美元，`turn.completed.usage` 只有 token 数——`cost_usd` 一律 NaN、usage
  进 raw（端口：绝不填 0）；`cost_reporting = "turn"`。退出码只有 0 / 1；没有轮数 / 花费的闸，超时
  是唯一的闸。长命令 agent 自己等着跑完（sleep 70 实测通过），没有 Claude Code 那种 2 分钟挪后台的
  机制。Codex 塞给子进程的 `CODEX_CI` / `CODEX_SANDBOX` / `CODEX_THREAD_ID` 实测不碍事。
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from backends import (
    CATALOG_DIR,
    CUSTOM,
    INSTALLED_ITEM,
    LOGIN_ITEM,
    OFFICIAL,
    VERSION_ITEM,
    AgentProbe,
    ChatEvent,
    Choice,
    Dist,
    Install,
    KeyMissing,
    Knobs,
    Link,
    Provider,
    RunResult,
    Tuning,
    Usage,
    price,
)
from backends._procs import kill_tree
from backends._snapshot import diff, snapshot

__all__ = ["CodexRunner", "CodexChat", "MODELS", "EFFORTS", "PROVIDERS", "PRICED", "LAYERS",
           "provider", "connect_config",
           "codex_home", "write_rules", "build_env", "config_args", "skill_off_paths", "toml_str",
           "tool_guide", "chat_tool_guide", "parse_events", "Translator", "final_report", "usage",
           "probe", "parse_version", "npm_dist", "INSTALL", "make_runner", "make_chat",
           "login_command", "logout_command"]

NAME = "codex"
HOME_ENV = "CODEX_HOME"
LAYERS = ("chat", "executor")
AUTH_NAME = "auth.json"
RULES_NAME = "ai4sci.rules"
CHAT_ID_ENV = "AI4SCI_CHAT_ID"
MIN_VERSION = (0, 160, 0)
# 起点 6.1 Sol / medium（P-25，外层 #247；主人 2026-10-05 定：性价比最高）：0.160 目录里排第一的
# 主力款（Latest workhorse for coding and everyday work）；Astra 是目录里写的 Frontier 那档，
# Luna 快而省
MODELS = (Choice("gpt-6.1-sol", "GPT-6.1 Sol", "主力"),
          Choice("gpt-6-astra", "GPT-6 Astra", "最强"),
          Choice("gpt-6-luna", "GPT-6 Luna", "快"),
          Choice("gpt-5.6-terra", "GPT-5.6 Terra", "上一代"))
EFFORTS = (Choice("low", "低"), Choice("medium", "中"), Choice("high", "高"),
           Choice("xhigh", "超高"))
# 第三方的思考档一档对一档（主人 2026-10-06 定）：Codex 把 `model_reasoning_effort` 原样写进
# `reasoning.effort`（本机抓包），两家的 Responses 都只认 low / high / max；起点照官方缺省——DeepSeek
# high（https://api-docs.deepseek.com/zh-cn/guides/thinking_mode ，它给 Codex 的 models.json 同），
# Kimi max（https://platform.kimi.com/docs/api/models-overview ，2026-10-06）。随包的模型说明
# （CATALOGS）与这里对账，`test_third_party_effort_lists_match_the_model_catalogs` 守着
THIRD_EFFORTS = (Choice("low", "低"), Choice("high", "高"), Choice("max", "最高"))
# 供应商目录（外层 #266）：地址与模型照 cc-switch 的 src/config/codexProviderPresets.ts（a4d07f31，
# 2026-10-06），都是原生 Responses（`wire_api="responses"`），不用中间转发。第三方要带一份模型说明
# （`model_catalog_json`，CATALOGS），不然 Codex 不知道这些模型怎么调工具
# 联网搜索（外层 #271）：`web_search` 是 Responses API 的内置工具，搜索由那家的服务端跑，能不能搜看
# 它的 Responses 接口实没实现——同一家在 Claude Code 那边可以相反（DeepSeek、Kimi 正好反过来）
PROVIDERS = {
    OFFICIAL: Provider(OFFICIAL, "ChatGPT 登录", MODELS, EFFORTS, "gpt-6.1-sol", "medium",
                       tested="0.160.0 在平台的私有目录里登录后用", web_search=True),
    "openai": Provider("openai", "OpenAI API", MODELS, EFFORTS, "gpt-6.1-sol", "medium",
                       key="openai", base_url="https://api.openai.com/v1", web_search=True),
    "deepseek": Provider("deepseek", "DeepSeek",
                         (Choice("deepseek-flash", "DeepSeek V4.1 Flash", "快"),
                          Choice("deepseek-v4-pro", "DeepSeek V4 Pro", "强")),
                         THIRD_EFFORTS, "deepseek-flash", "high", key="deepseek",
                         base_url="https://api.deepseek.com",
                         tested="2026-10-06 冒烟：pong 约 $0.003，agent 的命令看不见 key；"
                                "联网搜不了（模型说没有搜索工具）",
                         # Responses API 的 Tools 表里 web_search 等内置工具一律 Ignored，官方给
                         # Codex 的配置也是 web_search = "disabled"
                         # （https://api-docs.deepseek.com/guides/responses_api ，2026-10-06）
                         web_search=False),
    # Kimi 的 Responses API 认 web_search，「由服务端执行」
    # （https://platform.kimi.com/docs/api/responses ，2026-10-06；没 key，未实测）
    "kimi": Provider("kimi", "Kimi", (Choice("kimi-k3", "Kimi K3"),), THIRD_EFFORTS, "kimi-k3",
                     "max", key="kimi", base_url="https://api.moonshot.cn/v1", web_search=True),
}
CATALOGS = {"deepseek": CATALOG_DIR / "codex-deepseek.json",
            "kimi": CATALOG_DIR / "codex-kimi.json"}
# 价目表里这家用得上的（Codex 报不出美元，首页照这些折算；标准短上下文价，>272K 的长上下文档与写缓存
# 的加价不计）。加模型要在这里加，`backends/catalog/prices.json` 也得有（测试对账）
PRICED = ("gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna", "gpt-5.6-terra", "deepseek-flash",
          "deepseek-v4-pro", "kimi-k3")
# 第三方的连接：`-c` 里写一个叫这个名字的供应商，key 放进这个环境变量交给 Codex（`env_key`），
# 再用 `shell_environment_policy.exclude` 挡在 agent 跑的命令外面
PROVIDER_NAME = "ai4sci"
PROVIDER_KEY_ENV = "AI4SCI_PROVIDER_KEY"
# 执行层留档的第一行：Codex 的事件里不写模型，适配器记下这次用的哪个（外层 #256：首页按模型数花费）
MODEL_EVENT = "ai4sci.model"
# 两层共用的 exec 参数：JSONL、不查 git 仓库（工作区不是仓库）、不读本机配置；execpolicy 规则要读
# （私有 home 里只有我们写的那份）
BASE_ARGS = ("--json", "--skip-git-repo-check", "--ignore-user-config")
# 两层共用的配置覆盖（`-c key=value`，值按 TOML 解析）；可写根另算
BASE_CONFIG = (
    'approval_policy="never"',         # exec 本就 never，写明
    "project_doc_max_bytes=0",         # 不读 AGENTS.md（源码行为，文档没给开关）
    'sandbox_mode="workspace-write"',  # resume 没有 -s，两种形态都用 -c
    "features.hooks=false",
    "features.memories=false",
    "mcp_servers={}",
    "notify=[]",
)
_TAIL_CHARS = 4000
_RESULT_CHARS = 4000
# 系统 skills 的目录（随包安装进 CODEX_HOME）、个人 skills、管理员 skills：都要按 SKILL.md 逐个关
SKILL_ROOTS = ("skills/.system",)
USER_SKILLS = Path.home() / ".agents" / "skills"
ADMIN_SKILLS = Path("/etc/codex/skills")
TOOL_GUIDE = """## 工具怎么用

- 读文件、找文件、搜内容用 shell 的只读命令（cat / rg / ls）；改文件用 apply_patch。
- 运行动作只用 {commands} 一类命令：它们在沙箱外跑。别的命令都在沙箱里——只能写允许的目录、
  没有网络，pip、curl、git 这类不要去凑，被拒（operation not permitted）就换路子，不要反复试。
- 写完不用自己查行宽、跑 lint：框架会跑 ruff 与校验，问题喂回给你。
"""
# 协调层的同一段：这家没有单独的读文件工具，看文件就是 shell 的只读命令；「只能运行 ai4sci」
# 说的是动作
CHAT_TOOL_GUIDE = """## 工具怎么用

- 看文件、列目录、搜内容用 shell 的只读命令：ls、cat、head、rg、find（原件在 `materials/`，要看
  就直接看）。这不算「运行动作」——沙箱只让你写工作区，读是放开的。
- 运行动作只用 {commands} 一类命令：它们在沙箱外跑，能起作业、能联网。别的命令都在沙箱里、没有
  网络，不要拿 pip、curl、git、python 去凑（没有对应的命令就停下来说缺什么）。
- 改文件（需求、流程实例）用 apply_patch 或 ai4sci 的命令，只在工作区里。
"""


def parse_version(text: str) -> tuple[int, ...] | None:
    """`codex --version` 的原文形如 `codex-cli 0.147.0`：取最后一个词的三段数字；认不出返回 None。
    """
    words = text.strip().split()
    parts = words[-1].split(".") if words else []
    if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
        return None
    return tuple(int(p) for p in parts[:3])


# npm 的平台名 → Codex 程序包里 vendor/ 下的目录名（照 0.160.1 的 bin/codex.js；Linux 只发 musl 版）
TRIPLES = {"darwin-arm64": "aarch64-apple-darwin", "darwin-x64": "x86_64-apple-darwin",
           "linux-x64": "x86_64-unknown-linux-musl", "linux-arm64": "aarch64-unknown-linux-musl",
           "win32-x64": "x86_64-pc-windows-msvc", "win32-arm64": "aarch64-pc-windows-msvc"}


def npm_dist(platform: str, version: str) -> Dist:
    """原生程序在主包的平台版本里（`@openai/codex@<版本>-<平台>`）。`vendor/<三元组>/` 整个留下：
    除了 `bin/codex` 还有它找的 `codex-path/rg` 与 `codex-resources/`，按 `codex-package.json` 的
    布局、相对程序自己的位置找（0.160.1 实测）。"""
    if platform not in TRIPLES:
        raise ValueError(f"Codex 没有 {platform} 的程序包；有：{', '.join(TRIPLES)}")
    exe = "codex.exe" if platform.startswith("win32") else "codex"
    return Dist(package=INSTALL.npm, version=f"{version}-{platform}",
                root=f"package/vendor/{TRIPLES[platform]}", entry=f"bin/{exe}")


INSTALL = Install(command="codex", min_version=MIN_VERSION, npm="@openai/codex",
                  parse_version=parse_version, dist=npm_dist)


def toml_str(text: str) -> str:
    """一段任意文字写成 TOML 基本字符串：JSON 的转义规则是它的子集（`"` `\\` 控制字符），非 ASCII
    原样留着（TOML 允许）；DEL 是 TOML 不许裸写、JSON 又不转义的唯一一个，单独处理。"""
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def codex_home(link: Link, layer: str) -> Path:
    """这一层的私有 CODEX_HOME：协调层就是 `link.home`（老对话的 rollout 在那儿，挪了就
    no rollout found），执行层是它下面的 `executor/`，`auth.json` 软链到根上那份——平台登录一次，
    两层都用。根上还没登录就是悬空软链，`codex login status` 说 Not logged in，自检原样给人。"""
    assert layer in LAYERS, f"层只有 {LAYERS}，得到 {layer!r}"
    root = link.home
    home = root if layer == "chat" else root / layer
    home.mkdir(parents=True, exist_ok=True)
    if layer == "chat":
        return home
    real = root / AUTH_NAME
    auth = home / AUTH_NAME
    if auth.is_symlink() and auth.readlink() != real:
        auth.unlink()  # 指错了（旧版本软链到用户的 ~/.codex）：重连
    if not auth.is_symlink():
        assert not auth.exists(), f"{auth} 是普通文件不是软链：执行层不该有自己的凭据"
        auth.symlink_to(real)
    return home


def write_rules(home: Path, bash_rules: tuple[str, ...]) -> Path:
    """端口的命令前缀 → 这一层私有 home 的 execpolicy 规则：命中的命令在沙箱外跑。每次起会话重写，
    同一层并发起的会话给的前缀相同，写的是同一份。"""
    rules_dir = home / "rules"
    rules_dir.mkdir(exist_ok=True)
    lines = ["# ai4sci 写的（纲领 P-14 / P-25）：平台自己的 CLI 在沙箱外跑，其余命令留在沙箱里。"]
    for prefix in bash_rules:
        pattern = ", ".join(json.dumps(word) for word in prefix.split())
        lines.append(f'prefix_rule(pattern=[{pattern}], decision="allow", '
                     f'justification="ai4sci 是平台自己的命令行，放行的门（{prefix}）")')
    path = rules_dir / RULES_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def skill_off_paths(home: Path, cwd: Path) -> list[Path]:
    """要关掉的 skill：私有 home 里随包装的系统 skills、`$HOME/.agents/skills`、
    `/etc/codex/skills`，
    以及 cwd 一路往上每级的 `.agents/skills`（文档说 REPO 层这么扫）。只认 SKILL.md 的路径。"""
    roots = [home / r for r in SKILL_ROOTS] + [USER_SKILLS, ADMIN_SKILLS]
    roots += [p / ".agents" / "skills" for p in (cwd.resolve(), *cwd.resolve().parents)]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if (entry / "SKILL.md").is_file():
                found.append(entry / "SKILL.md")
    return found


def provider(link: Link) -> Provider:
    """这次接的供应商：目录里的那条，或照 `link` 拼的自定义（兼容 OpenAI Responses 的地址 +
    人填的模型名）。"""
    if link.provider == CUSTOM:
        if not link.base_url or not link.models:
            raise ValueError("自定义供应商要填地址和至少一个模型名")
        models = tuple(Choice(m, m) for m in link.models)
        return Provider(CUSTOM, "自定义", models, EFFORTS, models[0].id, "medium",
                        key=f"{CUSTOM}.{NAME}", base_url=link.base_url, web_search=None)
    try:
        return PROVIDERS[link.provider]
    except KeyError:
        raise ValueError(f"Codex 没有叫 {link.provider!r} 的供应商；"
                         f"有：{', '.join([*PROVIDERS, CUSTOM])}") from None


def connect_config(link: Link) -> list[str]:
    """接这个供应商要加的 `-c`（外层 #266，照 cc-switch 的预设）：官方登录什么都不加；其余写一个
    `model_providers.ai4sci`（地址、Responses、key 从哪个变量读）并选它，第三方再给模型说明。
    要 key 却没填：KeyMissing。"""
    picked = provider(link)
    if picked.key is None:
        return []
    if not link.key:
        raise KeyMissing(f"{picked.title} 的 key 还没填：设置 → AI 里粘贴")
    table = (f"{{name={toml_str(picked.title)}, base_url={toml_str(picked.base_url)}, "
             f"env_key={toml_str(PROVIDER_KEY_ENV)}, wire_api=\"responses\"}}")
    items = [f"model_provider={toml_str(PROVIDER_NAME)}",
             f"model_providers.{PROVIDER_NAME}={table}",
             # Codex 缺省把整个环境透传给 agent 跑的命令，带 KEY 的也不例外（2026-10-06 实测
             # 看得见）：挡掉这一个，agent 一个 printenv 不会把 key 打进对话记录与产出
             f"shell_environment_policy.exclude=[{toml_str(PROVIDER_KEY_ENV)}]"]
    if picked.id in CATALOGS:
        items.append(f"model_catalog_json={toml_str(str(CATALOGS[picked.id]))}")
    return items


def config_args(link: Link, writable: list[Path], *, tuning: Tuning | None,
                skills_off: list[Path], developer_instructions: str = "") -> list[str]:
    """`-c` 那一串：基本项、接哪个供应商、可写根、要关的 skill、模型深度，协调层开新线程时再加
    指南。"""
    picked = provider(link).knobs().fill(tuning)
    roots = ", ".join(toml_str(str(Path(p).resolve())) for p in writable)
    off = ", ".join("{path=" + toml_str(str(p)) + ", enabled=false}" for p in skills_off)
    # 自带的联网搜索（端口要求）：供应商的接口不认的照实关掉（DeepSeek），不发一个被忽略的设置
    search = "disabled" if provider(link).web_search is False else "live"
    items = [*BASE_CONFIG, f"web_search={toml_str(search)}", *connect_config(link),
             f"sandbox_workspace_write.writable_roots=[{roots}]", f"skills.config=[{off}]",
             f"model_reasoning_effort={toml_str(picked.effort)}"]
    if developer_instructions:
        items.append(f"developer_instructions={toml_str(developer_instructions)}")
    argv: list[str] = []
    for item in items:
        argv += ["-c", item]
    return [*argv, "-m", picked.model]


def build_env(timeout_s: float, home: Path, link: Link,
              chat_id: str | None = None) -> dict[str, str]:
    """子进程环境：继承本进程，venv 的 bin **追加**进 PATH（裸 `ai4sci` 找得到，
    同 Claude Code 的教训）、
    `CODEX_HOME` 指到这一层的私有 home、`AI4SCI_CHAT_ID` 告诉它调用的命令属于哪段对话。Codex 缺省把
    整个环境透传给它跑的命令（`shell_environment_policy.inherit = all`），AI4SCI_* 不用另外放行。
    `timeout_s` 留着与 Claude Code 的签名对齐：Codex 没有每条命令的超时，agent 自己等。
    用 key 的供应商：key 放进 `AI4SCI_PROVIDER_KEY`（只这一个进程有；shell 里的同名变量先去掉）。"""
    assert timeout_s > 0
    bin_dir = str(Path(sys.executable).parent)
    inherited = os.environ.get("PATH", "")
    env = {**os.environ, "PATH": f"{inherited}{os.pathsep}{bin_dir}" if inherited else bin_dir,
           HOME_ENV: str(home)}
    env.pop(PROVIDER_KEY_ENV, None)
    if provider(link).key is not None and link.key:
        env[PROVIDER_KEY_ENV] = link.key
    env.pop(CHAT_ID_ENV, None)
    if chat_id:
        env[CHAT_ID_ENV] = chat_id
    return env


def _commands(bash_rules: tuple[str, ...]) -> str:
    return ("、".join(f"`{p} …`" for p in bash_rules) if bash_rules
            else "（没有：这次一条都不跑）")


def tool_guide(bash_rules: tuple[str, ...]) -> str:
    return TOOL_GUIDE.format(commands=_commands(bash_rules))


def chat_tool_guide(bash_rules: tuple[str, ...]) -> str:
    return CHAT_TOOL_GUIDE.format(commands=_commands(bash_rules))


def parse_events(raw: list[str]) -> tuple[list[dict], list[str]]:
    """拆成结构化事件与非 JSON 行；非 JSON 行原样留给 stdout_tail（不吞）。"""
    events: list[dict] = []
    junk: list[str] = []
    for line in raw:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            junk.append(line)
    return events, junk


def usage(events: list[dict]) -> Usage | None:
    """用量是每个 turn.completed 的 usage 加起来（外层 #256）：`input_tokens` 已含命中缓存的；
    订阅报不出美元，花费是 NaN（未知）；模型 CLI 不报，执行层留档第一行有适配器记的
    （`MODEL_EVENT`），对话的没有、是 None。
    一次 turn.completed 都没有就是 None。"""
    done = [e["usage"] for e in events
            if e.get("type") == "turn.completed" and isinstance(e.get("usage"), dict)]
    if not done:
        return None
    model = next((e.get("model") for e in events if e.get("type") == MODEL_EVENT), None)
    return Usage(input_tokens=sum(int(u.get("input_tokens") or 0) for u in done),
                 cached_tokens=sum(int(u.get("cached_input_tokens") or 0) for u in done),
                 output_tokens=sum(int(u.get("output_tokens") or 0) for u in done),
                 model=model if isinstance(model, str) else None)


def final_report(events: list[dict]) -> str:
    """收尾的自述 = 最后一条 agent_message；没有就空串，不编。"""
    for event in reversed(events):
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text")
            return text.strip() if isinstance(text, str) else ""
    return ""


def _write_stdin(proc: subprocess.Popen, text: str) -> None:
    """prompt 走 stdin：另起线程写、写完关——大 prompt 撑满管道时不能卡住读 stdout 的主线程。"""
    def _pump() -> None:
        try:
            proc.stdin.write(text)
        except BrokenPipeError:
            pass  # CLI 没读完就退了（参数错、没登录）：退出码与 stderr 会说明，这里不是失败点
        finally:
            proc.stdin.close()
    threading.Thread(target=_pump, daemon=True).start()


class CodexRunner:
    name = NAME

    def __init__(self, link: Link) -> None:
        self.link = link
        self.cli = link.cli or INSTALL.command

    @staticmethod
    def tool_guide(bash_rules: tuple[str, ...]) -> str:
        return tool_guide(bash_rules)

    def build_argv(self, cwd: Path, allowed_paths: list[Path], bash_rules: tuple[str, ...] = (),
                   tuning: Tuning | None = None, *, home: Path | None = None) -> list[str]:
        """一次性会话：`--ephemeral`（不留 rollout）。可写根 = 只许改的目录；放行的命令前缀写进
        这一层 home 的规则。`--ephemeral` 与 `--color` 只在根形态有（resume 没有）。"""
        home = codex_home(self.link, "executor") if home is None else home
        write_rules(home, bash_rules)
        return [self.cli, "exec", *BASE_ARGS, "--ephemeral", "--color", "never",
                "-C", str(Path(cwd).resolve()),
                *config_args(self.link, list(allowed_paths), tuning=tuning,
                             skills_off=skill_off_paths(home, Path(cwd))),
                "-"]

    def run(self, prompt: str, cwd: Path, timeout_s: float,
            allowed_paths: list[Path], bash_rules: tuple[str, ...] = (),
            tuning: Tuning | None = None, max_turns: int | None = None,
            max_budget_usd: float | None = None) -> RunResult:
        # max_turns / max_budget_usd：Codex 没有这两个闸（文档与 --help 都没有），超时是唯一的闸
        home = codex_home(self.link, "executor")
        before = snapshot(cwd)
        argv = self.build_argv(cwd, allowed_paths, bash_rules, tuning, home=home)
        raw: list[str] = []
        err: list[str] = []
        started = time.monotonic()
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", start_new_session=True,
                                env=build_env(timeout_s, home, self.link))
        _write_stdin(proc, prompt)
        readers = [threading.Thread(target=lambda: raw.extend(proc.stdout), daemon=True),
                   threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc.pid)
            proc.wait()
        for reader in readers:
            reader.join(timeout=5)
        wall_s = time.monotonic() - started
        events, junk = parse_events(raw)
        _persist(cwd, raw, err, model=provider(self.link).knobs().fill(tuning).model)
        # 成功也是 NaN：订阅账号报不出美元（端口：绝不填 0），
        # token 用量在 turn.completed 的 usage 里
        return RunResult(exit_code=proc.returncode, events=events,
                         changed_files=diff(before, snapshot(cwd)), cost_usd=math.nan,
                         duration_s=wall_s, timed_out=timed_out,
                         stdout_tail="".join(junk + err)[-_TAIL_CHARS:],
                         report=final_report(events))


def _persist(cwd: Path, raw: list[str], err: list[str], *, model: str) -> None:
    # 与 Claude Code 同一处、同一种命名：框架按这个模式把日志搬到产出目录（P-9：日志不进 prompt）
    log_dir = cwd / ".ai4sci"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    head = json.dumps({"type": MODEL_EVENT, "model": model}) + "\n"
    (log_dir / f"executor-{stamp}.jsonl").write_text(head + "".join(raw), encoding="utf-8")
    if err:
        (log_dir / f"executor-{stamp}.stderr.log").write_text("".join(err), encoding="utf-8")


class Translator:
    """`--json` 的一行 → 零个或几个 ChatEvent。有状态：done 要带最后一段话，`error` 顶层事件与
    `turn.failed` 成对出现只报一次，命令的开始与结束要配成 tool_use / tool_result。"""

    def __init__(self, started: float) -> None:
        self.started = started
        self.last_text = ""
        self.fatal: str | None = None
        self.finished = False  # 见过 turn.completed 或 turn.failed
        self.thread_id: str | None = None

    def feed(self, line: str) -> list[ChatEvent]:
        if not line.strip():
            return []
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            return []
        kind = raw.get("type")
        sid = self.thread_id
        if kind == "thread.started":
            self.thread_id = sid = str(raw.get("thread_id") or "") or None
            return [ChatEvent("init", session_id=sid, raw=raw)]
        if kind == "turn.completed":
            self.finished = True
            return [ChatEvent("done", text=self.last_text, session_id=sid, cost_usd=math.nan,
                              duration_s=time.monotonic() - self.started, exit_code=0, raw=raw)]
        if kind == "turn.failed":
            self.finished = True
            message = str((raw.get("error") or {}).get("message") or self.fatal or "turn failed")
            return [ChatEvent("error", text=message, is_error=True, session_id=sid, exit_code=1,
                              duration_s=time.monotonic() - self.started, raw=raw)]
        if kind == "error":
            self.fatal = str(raw.get("message") or "")  # 随后多半跟着 turn.failed，那时一起报
            return []
        if kind not in ("item.started", "item.completed"):
            return []  # item.updated 只有 todo_list 用，页面不画计划
        item = raw.get("item") or {}
        itype = item.get("type")
        done = kind == "item.completed"
        if itype == "agent_message" and done:
            self.last_text = str(item.get("text") or "")
            return [ChatEvent("text", text=self.last_text, session_id=sid, raw=raw)]
        if itype == "command_execution":
            if not done:
                return [ChatEvent("tool_use", tool="shell", session_id=sid, raw=raw,
                                  tool_input={"command": str(item.get("command") or "")})]
            code = item.get("exit_code")
            bad = item.get("status") in ("failed", "declined") or (code not in (None, 0))
            output = str(item.get("aggregated_output") or "")[:_RESULT_CHARS]
            return [ChatEvent("tool_result", text=output, is_error=bool(bad), session_id=sid,
                              raw=raw)]
        if itype == "file_change" and done:
            changes = [f"{c.get('kind')} {c.get('path')}" for c in item.get("changes") or []]
            return [ChatEvent("tool_use", tool="apply_patch", session_id=sid, raw=raw,
                              tool_input={"changes": changes}),
                    ChatEvent("tool_result", text="\n".join(changes), session_id=sid,
                              is_error=item.get("status") == "failed", raw=raw)]
        if itype == "web_search" and done:
            # 搜索只在 completed 时才有 query，一条事件配成一对：只发 tool_use 页面那一行会一直转
            # 「运行中」
            action = item.get("action") or {}
            query = str(item.get("query") or "")
            return [ChatEvent("tool_use", tool="web_search", session_id=sid, raw=raw,
                              tool_input={"query": query, "action": str(action.get("type") or "")}),
                    ChatEvent("tool_result", text=query, session_id=sid, raw=raw)]
        if itype == "mcp_tool_call":
            tool = f"{item.get('server', '')}.{item.get('tool', '')}"
            if not done:
                return [ChatEvent("tool_use", tool=tool, session_id=sid, raw=raw,
                                  tool_input=dict(item.get("arguments") or {}))]
            error = (item.get("error") or {}).get("message")
            result = item.get("result") or {}
            text = error or json.dumps(result.get("content", ""), ensure_ascii=False)
            return [ChatEvent("tool_result", text=str(text)[:_RESULT_CHARS], is_error=bool(error),
                              session_id=sid, raw=raw)]
        if itype == "error" and done:
            # 非致命的 item 错误（模型元数据缺失之类）：留一行给人看，不算这一轮失败
            return [ChatEvent("tool_result", text=str(item.get("message") or ""), is_error=True,
                              session_id=sid, raw=raw)]
        return []


class CodexChat:
    """协调层：开新线程用 `codex exec`（不 ephemeral），续接用 `codex exec resume <thread_id>`。

    实测：第一轮 thread.started 给 thread_id，第二轮 resume 带上它模型记得第一轮说的词；resume 认
    `-c` 的沙箱与可写根覆盖（read-only 开的线程 resume 成 workspace-write 后能写）；
    `developer_instructions` 只在开线程那次生效。`cost_reporting = "turn"`，值永远 NaN（订阅账号）。
    """

    name = NAME
    cost_reporting = "turn"

    def __init__(self, link: Link) -> None:
        self.link = link
        self.cli = link.cli or INSTALL.command

    def knobs(self) -> Knobs:
        """有哪些模型、哪几档思考深度、起点：跟着供应商走（外层 #266）。"""
        return provider(self.link).knobs()

    def forget(self, session_id: str, cwd: Path) -> None:
        """删这条线程在私有 home 里的 rollout（实测 0.147.0 的布局：`sessions/<年>/<月>/<日>/
        rollout-<时间>-<thread_id>.jsonl`；官方文档不写存哪、也没有删会话的命令）。cwd 用不上——
        Codex 的会话不按目录分。"""
        del cwd
        home = codex_home(self.link, "chat")
        for path in (home / "sessions").glob(f"*/*/*/rollout-*-{session_id}.jsonl"):
            path.unlink()

    @staticmethod
    def tool_guide(bash_rules: tuple[str, ...]) -> str:
        return chat_tool_guide(bash_rules)

    def build_argv(self, cwd: Path, *, session_id: str | None, system_prompt: str,
                   allowed_paths: list[Path], bash_rules: tuple[str, ...] = (),
                   tuning: Tuning | None = None, home: Path | None = None) -> list[str]:
        home = codex_home(self.link, "chat") if home is None else home
        write_rules(home, bash_rules)
        skills_off = skill_off_paths(home, Path(cwd))
        if session_id:
            # resume 没有 -C / -s / --add-dir / --color；线程的 cwd 记在 rollout 里，
            # 沙箱与可写根靠 -c
            return [self.cli, "exec", "resume", *BASE_ARGS,
                    *config_args(self.link, list(allowed_paths), tuning=tuning,
                                 skills_off=skills_off),
                    session_id, "-"]
        return [self.cli, "exec", *BASE_ARGS, "--color", "never", "-C", str(Path(cwd).resolve()),
                *config_args(self.link, list(allowed_paths), tuning=tuning, skills_off=skills_off,
                             developer_instructions=system_prompt), "-"]

    def turn(
        self, message: str, cwd: Path, timeout_s: float, *, session_id: str | None,
        system_prompt: str, allowed_paths: list[Path], bash_rules: tuple[str, ...],
        readable_paths: list[Path] = (), chat_id: str | None = None,
        tuning: Tuning | None = None,
    ) -> Iterator[ChatEvent]:
        # readable_paths 用不上：沙箱里读是全盘放开的
        home = codex_home(self.link, "chat")
        try:
            argv = self.build_argv(cwd, session_id=session_id, system_prompt=system_prompt,
                                   allowed_paths=allowed_paths, bash_rules=bash_rules,
                                   tuning=tuning, home=home)
        except KeyMissing as exc:  # 选了要 key 的供应商却没填：这一轮说清楚，不起 CLI
            yield ChatEvent("error", text=str(exc), is_error=True)
            return
        err: list[str] = []
        started = time.monotonic()
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", start_new_session=True,
                                env=build_env(timeout_s, home, self.link, chat_id))
        _write_stdin(proc, message)
        drain = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
        drain.start()
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            kill_tree(proc.pid)

        timer = threading.Timer(timeout_s, _kill)
        timer.start()
        translator = Translator(started)
        try:
            for line in proc.stdout:
                yield from translator.feed(line)
        finally:
            timer.cancel()
            proc.wait()
            drain.join(timeout=5)
        tail = "".join(err)[-_TAIL_CHARS:]
        if timed_out.is_set():
            yield ChatEvent("error", text=f"这一轮超过 {timeout_s:g} 秒，进程树已杀",
                            is_error=True, exit_code=proc.returncode,
                            duration_s=time.monotonic() - started, raw={"stderr_tail": tail})
        elif not translator.finished:
            why = translator.fatal or tail.strip() or "无 stderr"
            yield ChatEvent("error", is_error=True, exit_code=proc.returncode,
                            duration_s=time.monotonic() - started,
                            text=f"CLI 退出码 {proc.returncode}，没有 turn.completed：{why}",
                            raw={"stderr_tail": tail})
        elif session_id and translator.thread_id and translator.thread_id != session_id:
            # resume 找不到线程时 Codex 会静默开一条新的（源码 resolve_resume_thread_id）：
            # 对不上就报，
            # 不让「记忆丢了」悄悄过去
            yield ChatEvent("error", is_error=True, exit_code=proc.returncode,
                            text=(f"续接的线程 {session_id} 不在了，"
                                  f"Codex 静默开了 {translator.thread_id}"),
                            duration_s=time.monotonic() - started, raw={"stderr_tail": tail})


def probe(link: Link, speak_timeout_s: float = 120.0) -> AgentProbe:
    """四句人话（纲领 P-25）：装了没、版本够不够、登录了没、能不能说话。

    登录看 `codex login status` 的退出码（0 / 1，文字在 stderr），在平台的 CODEX_HOME 下跑——问的是
    平台自己的登录，不是用户本机的；说话真跑一句 pong，走与真会话同一组隔离参数。
    """
    result = AgentProbe()
    cli = link.cli or INSTALL.command
    exe = shutil.which(cli)
    if exe is None:
        result.items.append((INSTALLED_ITEM, False, f"找不到 `{cli}`"))
        return result
    result.installed = True
    result.items.append((INSTALLED_ITEM, True, exe))
    version = subprocess.run([cli, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
    raw = (version.stdout or version.stderr).strip()
    result.version = raw
    parsed = parse_version(raw)
    want = ".".join(map(str, MIN_VERSION))
    if version.returncode != 0 or parsed is None:
        result.items.append((VERSION_ITEM, False, f"`{cli} --version` 认不出：{raw or '无输出'}"))
        return result
    if parsed < MIN_VERSION:
        result.items.append((VERSION_ITEM, False, f"{raw}，要 ≥ {want}（这版实测过的 flag）"))
        return result
    result.items.append((VERSION_ITEM, True, raw))
    home = codex_home(link, "chat")
    picked = provider(link)
    if picked.key is None:  # 官方登录：问平台私有目录里的登录，不是用户本机的
        status = subprocess.run([cli, "login", "status"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=30, env=build_env(30.0, home, link))
        result.logged_in = status.returncode == 0
        said = (status.stderr or status.stdout).strip()
        if not result.logged_in:
            result.items.append((LOGIN_ITEM, False, f"{said or 'Not logged in'}：平台里还没登录"))
            return result
        result.items.append((LOGIN_ITEM, True, said or "已登录"))
    else:  # 用 key 的供应商：key 在平台的家里（外层 #265），这里只看填了没有
        result.logged_in = bool(link.key)
        if not result.logged_in:
            result.items.append((LOGIN_ITEM, False,
                                 f"{picked.title} 的 key 还没填：设置 → AI 里粘贴"))
            return result
        result.items.append((LOGIN_ITEM, True, f"{picked.title} 的 key 已填"))
    started = time.monotonic()
    write_rules(home, ())
    argv = [cli, "exec", *BASE_ARGS, "--ephemeral", "--color", "never", "-C", str(home),
            *config_args(link, [], tuning=None, skills_off=skill_off_paths(home, home)), "-"]
    try:
        # cwd 也放在私有 home 里：说一句话不该在谁的目录里留下东西
        spoke = subprocess.run(argv, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=speak_timeout_s,
                               input="Reply with exactly the word pong and nothing else.",
                               env=build_env(speak_timeout_s, home, link), cwd=str(home))
    except subprocess.TimeoutExpired:
        result.items.append(("说话", False, f"{speak_timeout_s:g} 秒没回话"))
        return result
    events, _ = parse_events(spoke.stdout.splitlines(keepends=True))
    reply = final_report(events)
    if spoke.returncode != 0 or "pong" not in reply.lower():
        failed = next((e for e in events if e.get("type") in ("turn.failed", "error")), {})
        why = (str((failed.get("error") or {}).get("message") or failed.get("message") or "")
               or spoke.stderr.strip() or reply or "无输出")
        result.items.append(("说话", False, f"退出码 {spoke.returncode}：{why[-300:]}"))
        return result
    result.spoke_s = time.monotonic() - started
    # Codex 报不出美元：照价目折算（订阅也是，按 API 公开价算的，不是实扣）
    used = usage([{"type": MODEL_EVENT, "model": picked.model}, *events])
    rate = price(picked.model)
    result.cost_usd = rate.cost(used) if rate and used else math.nan
    said = f"约 ${result.cost_usd:.4f}（按价目折算）" if rate and used else "成本未知"
    result.items.append(("说话", True, f"pong，{result.spoke_s:.1f} 秒，{said}"))
    return result


def login_command(link: Link) -> tuple[list[str], dict[str, str]]:
    """在平台的 CODEX_HOME 里登录 ChatGPT：CLI 自己开浏览器授权，`auth.json` 落在那里
    （外层 #263）。"""
    return [link.cli or INSTALL.command, "login"], build_env(600.0, codex_home(link, "chat"), link)


def logout_command(link: Link) -> tuple[list[str], dict[str, str]]:
    """登出平台 CODEX_HOME 里的登录（删 `auth.json`）。"""
    return [link.cli or INSTALL.command, "logout"], build_env(60.0, codex_home(link, "chat"), link)


def make_runner(link: Link) -> CodexRunner:
    return CodexRunner(link)


def make_chat(link: Link) -> CodexChat:
    return CodexChat(link)
