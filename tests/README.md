# tests/ · 后端测试怎么写

给写或改测试的人和 agent 读。前端的测试政策在 `ui/README.md`。总原则在 `CLAUDE.md` §4：改行为先写一条会失败的测试，机器能查的进门禁，不用 mock 模型。

## 1. 目录与命名

- 目录是平的：`tests/test_<层>_<模块>.py`（`test_contracts_output.py`、`test_chat_server.py`、`test_capability_design.py`）；共用夹具在 `tests/fixtures/`。
- 全部是普通函数，不写 `class Test…`。用例名是英文的行为句（`test_cap_refuses_before_the_requirement_is_confirmed`），docstring 用中文写**为什么要有这条**——最好点名它防的那次事故或那条纲领。
- 断言信息只说位置与撞上的词，不把整段日志或前言原文塞进 assert（输出里「子进程被杀」这类字眼会触发安全过滤器，主人撞到过）。

## 2. 夹具：一切长在 tmp_path 上

- `tests/fixtures/packs_factory.py`：假工作区与设计那包（`make_workspace`、`make_pack`、`default_scoring`、各种 launcher 文本）；`runs_factory.py`：假实验目录；`spaces.py`：项目 + 工作区。
- `tests/fixtures/scripted_backend.py`（`ScriptedRunner`）与 `scripted_chat.py`：**剧本后端**，形状与真 `Runner` / `Chat` 完全一致，「这一轮执行层干了什么」由剧本一条条给出（真改进、假改进、改坏、动 harness、崩溃、超时…），`changed_files` 走 `backends/_snapshot` 同一份快照 diff。框架的正确性不由模型的发挥证明（P-5）。
- `tests/conftest.py` 的 autouse 夹具把按人的算力清单、底座清单、Codex 私有 home 都指到 tmp：测试绝不读开发机的配置（第一次就真的 ssh 到远端机器跑了起来）。
- 删掉仓里的 `projects/`、`domains/`、`skills/` 测试照过（P-5）；仓里的样例只在「在就校验」的用例里用（`test_experiment_pack.py::test_real_pack_*`）。
- 不用 `unittest.mock` 去替换框架内部的函数；要换的是端口（传剧本后端进去）或环境变量（`monkeypatch.setenv`）。`monkeypatch.setattr("framework.cli._common.get_backend", …)` 这种只用来把剧本后端塞进 CLI。

## 3. 三种写法

| 测什么 | 怎么写 | 例 |
|---|---|---|
| 纯函数、契约 | 直接调，`pytest.raises(SomeError, match="关键词")` 断言拒绝的原因说到了哪个文件哪个字段 | `test_contracts_*.py`、`test_experiment_pack.py` |
| CLI | 两种：子进程跑真命令（`run_cli(...)`，断言退出码、stdout 那一行、stderr 的关键词）；或进程内 `main([...])` + `capsys` | `test_cli.py`、`test_skills.py` |
| 服务端 | 起 `ChatServer` 注入剧本 chat，走真 HTTP；页面读的每个响应体都过「id / name / slug 必带 title / label」的检查 | `test_chat_server.py` |

**检查器必须带反例**：任何「扫代码判规矩」的测试（分层、指南里的命令、文案禁用词、包数据）都要有一条证明它抓得到违规（`test_layering.py` 最后几条）——一个永远返回「没问题」的检查器比没有检查器更坏。

**出厂件也要测**：流程文件、模板、领域包、skill、指南、每个能力的 `prompt.md` 与包数据（`test_packaging.py`、`test_skills.py`、`test_chat_guide.py`）。

## 4. 真 CLI 与真机器：门控

- 连真 coding agent CLI 的冒烟：`AI4SCI_LIVE=1 make test`（会花钱）。
- 连清单里那台真机器：`AI4SCI_LIVE_SSH=<名字> make test`。
- 都用 `pytest.skip` 门控、都不进 CI。除此之外没有别的跳过：一条测试永远跳过等于没有。

## 5. 门禁

`make check` = `changelog`（CHANGELOG 格式）→ `lint`（ruff，含 BLE 不吞异常）→ `skills`（SKILL.md 校验 + 脚本锁文件 + uv 预热，唯一联网的一步）→ `test`（pytest）→ `ui-check`（素材不进仓 + tsc + oxlint + vitest + 构建）。CI 跑的就是这一句。

- 提交前跑 `make check`，不接 `| tail`（管道会吞退出码）：`make check > /tmp/check.log 2>&1; echo $?`。
- 没有覆盖率工具，也不设覆盖率门槛：判据是爆炸半径——改了行为的地方有测试，改了检查器的地方有反例。
- 改了页面看得见的东西，还要过浏览器（`ui/README.md` §5）。
