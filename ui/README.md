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
| 工作区 | `GET /workspaces`、`POST /workspaces`、`GET /workspaces/<id>` | 地方栏选一个工作区，或起一个（一个工作区一份需求，P-15）；一整份里有需求、流实例、全部 run |
| 对话 | `POST <域>/chats`、`POST <域>/chats/<id>/messages`（SSE）、`GET <域>/chats[/<id>]`、`GET /backends` | 主页面和研究助理说话、编辑台和造流助理说话；助理运行的每条命令以 `tool_use` / `tool_result` 事件流回来；输入框上「模型」「思考」两枚旋钮的清单来自 `GET /backends`（后端自报），选了随消息的 `model` / `effort` 发出去、记进对话 |
| 需求 | `GET /workspaces/<id>`（里面的 `task`）、`POST /workspaces/<id>/publish` | 脊柱上任务包那一段：看 manifest、设计说明、预检；人确认**发布**（`publish.json`），写裁判与开跑没它不动 |
| 库 | `GET /workflows`、`POST /workflows`、`POST /workflows/check`、`GET /cap`、`GET /stages` | 编辑台的画布：节点是研究阶段（装能力 + 参数）或断点，边只表示顺序；边拼边查（问题贴到节点上）；存进库。研究者不改库 |
| 结果 | `GET /workspaces/<id>/runs[/<rid>]`、`POST …/runs/<rid>/accept`、`GET …/jobs[/<jid>]` | 脊柱上的 run：一间一格看 best、账本、分析、验证、后台作业；人确认**验收**（`accept.json`，签这一版 best 与验证结论） |

发布、验收是出厂的两个断点（外层 `docs/vision.md`「两个发布键、一次验收」），机器守着记录；流里别的断点是助理停下来等人说「继续」。
界面上的发布 / 验收是"只有人能确认"的唯一保证——CLI 里的 `ai4sci sign task` / `ai4sci sign run`
是给在终端里当协调层的人用的，研究助理的指南写明它不该替人签。

## 网页怎么跑

```bash
make ui            # 装依赖（只进 ui/web/node_modules）并构建到 ui/web/dist
ai4sci serve       # 起后端并端出页面：http://127.0.0.1:8765
```

开发时两个进程：`ai4sci serve`（接口，8765）+ `cd ui/web && npm run dev`（页面，5173，接口按前缀代理过去）。
门禁 `make ui-check` = 素材不进仓的检查（`git ls-files ui/` 没有 png / jpg / mp4，纲领 P-17）+ 类型检查 + oxlint + vitest + 构建，已并入 `make check` 与 CI。

## 网页的结构

设计口径在 `docs/PRODUCT.md`（给谁用、反例、原则）与 `docs/DESIGN.md`（色板、字阶、布局）。
页面先认工作区：最左一条地方栏（先「工作区 / 编辑台」两个世界的开关，工作区世界里再列封面块与「新建」；编辑台是全局一个库，进了编辑台工作区块整段收掉）；没有工作区时主页面是门口那一屏（一句话起工作区，循环视频背景），有工作区还没对话时是配图 + 输入框，打字就开一段。
主页面 = 这个工作区的对话 + 流程脊柱（几条泳道：需求对齐、每个 run 一条、备着的流；默认收着只给目录，助理承接中的那条展开）；编辑台 = 画布铺满（React Flow：一条线性的链，阶段 / 断点两种节点；左上角阶段梯与题头，右上角库、保存与选中节点的配置；底下一层风景）+ 右下角圆形入口弹出的悬浮对话窗（造流助理）。
正文只许出现 `lib/humanize.ts` 翻译过的句子；状态码、哈希、命令只在折叠层。

```
web/src/
  assets.ts   页面里全部图片 / 视频的 CDN URL，仅此一处（纲领 P-17）；素材清单在 docs/DESIGN.md
  api/        契约：types.ts（响应体的类型）、client.ts（每个端点一个函数，Scope 定域前缀）、sse.ts（事件流）
  chat/       对话：trace.ts（事件流折成条目，纯函数、有单测）、ChatView（两个域共用，文案由父组件给）/ TurnView / Composer
  places/     Rail（宽屏的地方栏）、PlacesSheet（窄屏的清单）、place.ts（页面此刻在哪）
  workspace/  NewWorkspace（门口那一屏：一句话起工作区）
  spine/      流程脊柱：derive.ts（从进度记录、作业、发布 / 验收记录、任务包阶段算每一项——阶段或断点——的状态，纯函数、有单测）、Spine（按工作区读，几条泳道；有作业在跑时轮询）
  studio/     编辑台的画布：model.ts（链的数据：排版、插入、重排、页面形状 ↔ 文件形状，纯函数、有单测）、nodes（阶段 / 断点两种节点）、Palette（阶段梯与库的弹层）、Inspector（选中节点：勾能力、填参数、断点的确认事项）、Studio（React Flow 画布、边拼边查、保存）
  keys/       发布、验收两处人的确认（StarBorder 改装）
  sidebar/    对话列表抽屉
  components/ 零件 bits.tsx、Markdown.tsx、Backdrop（门口的视频背景）、shadcn 生成的 ui/、reactbits 的改装件
  lib/        humanize.ts（术语翻人话、能力的人话说法，有单测）、useChats（一个域的对话清单）、format、取数 hook、署名记忆
```

依赖方向：`App → workspace / spine / studio / chat / sidebar → keys / components → api`；`api/` 不 import 任何组件。
组件不直接 `fetch`，都经 `api/client.ts`。

## 不做（第一版）

- 画布上的分叉 / 并行：流是线性的（一条链），节点一进一出；坐标不进文件，按顺序自动排、放不下换行
- 多用户、鉴权、token 级流式：后端是本机单人服务
