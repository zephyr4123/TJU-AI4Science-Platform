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

| 看板 | 端点 | 人在这里做什么 |
|---|---|---|
| 对话 | `POST /chats`、`POST /chats/<id>/messages`（SSE）、`GET /chats[/<id>]` | 和协调 agent 说话；agent 按的每个按钮以 `tool_use` / `tool_result` 事件流回来 |
| 需求 | `GET /tasks[/<id>]`、`POST /tasks/<id>/publish` | 看 manifest、设计说明、预检；按**发布**。发布是钥匙（`publish.json`），后面的按钮没它不开 |
| 工作流 | `GET /workflows`、`GET /cap` | 平台是一盒能力，工作流是预装的拼法：列出现在有几条工作流（每步谁做、做什么）、几颗能力（吃什么吐什么、机器还是助理做）。不写死顺序 |
| 结果 | `GET /runs[/<id>]`、`POST /runs/<id>/accept` | 看 best、账本、分析、验证；按**验收**（`accept.json`，签这一版 best 与验证结论） |

两颗键（发布、验收）是产品形态里仅有的两个人工停点（外层 `docs/vision.md`「两个发布键、一次验收」）。
界面上的键是"只有人能按"的唯一保证——CLI 里的 `ai4sci sign task` / `ai4sci sign run`
是给在终端里当协调层的人用的，协调 agent 的指南写明它不该替人按。

## 网页怎么跑

```bash
make ui            # 装依赖（只进 ui/web/node_modules）并构建到 ui/web/dist
ai4sci serve       # 起后端并端出页面：http://127.0.0.1:8765
```

开发时两个进程：`ai4sci serve`（接口，8765）+ `cd ui/web && npm run dev`（页面，5173，接口按前缀代理过去）。
门禁 `make ui-check` = 类型检查 + oxlint + vitest + 构建，已并入 `make check` 与 CI。

## 网页的结构

设计口径在 `docs/PRODUCT.md`（给谁用、反例、原则）与 `docs/DESIGN.md`（色板、字阶、布局）。
每张看板是助理写给研究者的一页纸：一句话结论 → 三个大数字 → 几段人话 → 细节折叠 → 键在文末。
正文只许出现 `lib/humanize.ts` 翻译过的句子；状态码、哈希、命令只在折叠层。

```
web/src/
  api/        契约：types.ts（响应体的类型）、client.ts（每个端点一个函数）、sse.ts（事件流）
  chat/       对话：trace.ts（事件流折成条目，纯函数、有单测）、ChatView（含欢迎屏）/ TurnView / Composer
  boards/     三页：TaskBoard（需求 + 发布键）、WorkflowBoard（工作流 + 能力清单）、RunBoard（结果 + 验收键）
  sidebar/    对话列表抽屉
  components/ 一页纸的零件 bits.tsx、Markdown.tsx、shadcn 生成的 ui/、reactbits 的 Waves / BlurText / ClickSpark
  lib/        humanize.ts（术语翻人话、能力的人话说法，有单测）、format、取数 hook、署名记忆
```

依赖方向：`App → boards / chat / sidebar → components → api`；`api/` 不 import 任何组件。
组件不直接 `fetch`，都经 `api/client.ts`。

## 不做（第一版）

- 拖拽编排画布与「摆一串查通不通」：等套餐文件有了第二个用例（外层 #47 第 6 件）；第一版做过的检查工具已砍，CLI 的 `flow check` 还在
- 多用户、鉴权、token 级流式：后端是本机单人服务
- 深色主题：使用场景是白天实验室里读数字，先只做浅色
