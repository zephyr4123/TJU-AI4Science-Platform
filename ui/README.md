# ui/ · 界面层

平台的界面是**适配器**：一种界面一个目录，全部是 `ai4sci serve` 那几个 HTTP 端点的客户端，
互相不认识，也不认识框架内部。换一种界面（现在是网页，之后是终端里的 TUI）就是加一个目录，
后端一行不改。

| 目录 | 是什么 | 状态 |
|---|---|---|
| `web/` | 网页：React 19 + Tailwind v4 + shadcn，Vite 构建成静态文件，`ai4sci serve` 缺省端它 | 第一版（外层 [#52](https://github.com/zephyr4123/TJU-AI4Science/issues/52)） |
| `tui/` | 终端界面：同一套端点的客户端，给只有 ssh 的场景 | 留位置，没建 |

## 契约：每种界面都只靠这些端点

端点定义在 `framework/chat/server.py` 顶部的清单里，响应体在 `framework/chat/boards.py`。
`web/src/api/client.ts` 是网页对这份契约的照抄，写 TUI 时照它再抄一份即可。
端点按域分前缀（纲领 P-16）：`/workspaces/<id>/…` 是研究助理的域，`/studio/…` 是造流助理的域；对话四个端点两个域共用。

| 看板 | 端点 | 人在这里做什么 |
|---|---|---|
| 工作区 | `GET /workspaces`、`POST /workspaces`、`GET /workspaces/<id>` | 顶栏选一个工作区，或起一个（一个工作区一份需求，P-15）；一整份里有需求、流实例、全部 run |
| 对话 | `POST <域>/chats`、`POST <域>/chats/<id>/messages`（SSE）、`GET <域>/chats[/<id>]` | 主页面和研究助理说话、编辑台和造流助理说话；助理运行的每条命令以 `tool_use` / `tool_result` 事件流回来 |
| 需求 | `GET /workspaces/<id>`（里面的 `task`）、`POST /workspaces/<id>/publish` | 脊柱上的需求对齐：看 manifest、设计说明、预检；按**发布**。发布是钥匙（`publish.json`），后面的按钮没它不开 |
| 库 | `GET /workflows`、`POST /workflows`、`GET /cap`、`GET /stages`、`GET /flow/check` | 编辑台：工作流墙、七段货架、拼流台；存进库。研究者不改库 |
| 结果 | `GET /workspaces/<id>/runs[/<rid>]`、`POST …/runs/<rid>/accept`、`GET …/jobs[/<jid>]` | 脊柱上的 run：看 best、账本、分析、验证、后台作业；按**验收**（`accept.json`，签这一版 best 与验证结论） |

两颗键（发布、验收）是产品形态里仅有的两个人工停点（外层 `docs/vision.md`「两个发布键、一次验收」）。
界面上的键是"只有人能按"的唯一保证——CLI 里的 `ai4sci sign task` / `ai4sci sign run`
是给在终端里当协调层的人用的，研究助理的指南写明它不该替人按。

## 网页怎么跑

```bash
make ui            # 装依赖（只进 ui/web/node_modules）并构建到 ui/web/dist
ai4sci serve       # 起后端并端出页面：http://127.0.0.1:8765
```

开发时两个进程：`ai4sci serve`（接口，8765）+ `cd ui/web && npm run dev`（页面，5173，接口按前缀代理过去）。
门禁 `make ui-check` = 类型检查 + oxlint + vitest + 构建，已并入 `make check` 与 CI。

## 网页的结构

设计口径在 `docs/PRODUCT.md`（给谁用、反例、原则）与 `docs/DESIGN.md`（色板、字阶、布局）。
页面先认工作区：顶栏一个下拉切工作区、一个加号起新的；没有工作区时主页面是「起一个工作区」的欢迎屏。
主页面 = 这个工作区的对话 + 流程脊柱（当前 run 照的那条流，或需求对齐）；编辑台 = 造流助理的对话 + 库（工作流墙、货架、拼流台）。
正文只许出现 `lib/humanize.ts` 翻译过的句子；状态码、哈希、命令只在折叠层。

```
web/src/
  api/        契约：types.ts（响应体的类型）、client.ts（每个端点一个函数，Scope 定域前缀）、sse.ts（事件流）
  chat/       对话：trace.ts（事件流折成条目，纯函数、有单测）、ChatView（两个域共用，文案由父组件给）/ TurnView / Composer
  workspace/  WorkspaceSwitcher（顶栏下拉）、NewWorkspace（起一个工作区的欢迎屏与表单）
  spine/      流程脊柱：derive.ts（从便条、作业、两颗键算每一步的状态，纯函数、有单测）、Spine（按工作区读）
  studio/     编辑台的库那一半：工作流墙、七段货架、拼流台
  keys/       发布、验收两颗键（StarBorder 改装）
  sidebar/    对话列表抽屉
  components/ 零件 bits.tsx、Markdown.tsx、shadcn 生成的 ui/、reactbits 的改装件
  lib/        humanize.ts（术语翻人话、能力的人话说法，有单测）、useChats（一个域的对话清单）、format、取数 hook、署名记忆
```

依赖方向：`App → workspace / spine / studio / chat / sidebar → keys / components → api`；`api/` 不 import 任何组件。
组件不直接 `fetch`，都经 `api/client.ts`。

## 不做（第一版）

- 拖拽编排画布与「摆一串查通不通」：等套餐文件有了第二个用例（外层 #47 第 6 件）；第一版做过的检查工具已砍，CLI 的 `flow check` 还在
- 多用户、鉴权、token 级流式：后端是本机单人服务
- 深色主题：使用场景是白天实验室里读数字，先只做浅色
