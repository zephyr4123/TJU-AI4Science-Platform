# ui/ · 界面层

平台的界面是**适配器**：一种界面一个目录，全部是 `ai4sci serve` 那几个 HTTP 端点的客户端，
互相不认识，也不认识框架内部。换一种界面（现在是网页，之后是终端里的 TUI）就是加一个目录，
后端一行不改。

| 目录 | 是什么 | 状态 |
|---|---|---|
| `web/` | 网页：React 19 + Tailwind v4 + shadcn，Vite 构建成静态文件，`ai4sci serve` 缺省端它 | 在用 |
| `tui/` | 终端界面：同一套端点的客户端，给只有 ssh 的场景 | 留位置，没建 |

## 契约：每种界面都只靠这些端点

端点定义在 `framework/chat/server.py` 顶部的清单里，响应体在 `framework/chat/boards.py`。
`web/src/api/client.ts` 是网页对这份契约的照抄，写 TUI 时照它再抄一份即可。
端点按域分前缀（纲领 P-16）：`/workspaces/<id>/…` 是研究助理的域，`/studio/…` 是造流助理的域；对话四个端点两个域共用。

| 看板 | 端点 | 人在这里做什么 |
|---|---|---|
| 工作区 | `GET /workspaces`、`POST /workspaces`（`id` / `title` / `template`）、`GET /workspaces/<id>`、`GET /stages`、`GET /templates` | 地方栏选一个工作区，或按模板起一个（一个工作区一个课题，P-15）；一整份里有需求、七个阶段的产出、每条流的进度、作业 |
| 对话 | `POST <域>/chats`、`POST <域>/chats/<id>/messages`（SSE）、`GET <域>/chats[/<id>]`、`GET /backends` | 主页面和研究助理说话、编辑台和造流助理说话；助理运行的每条命令以 `tool_use` / `tool_result` 事件流回来，落盘成 `turn-N/trace.jsonl`、随 `history[].events` 回来，页面重放成一行一条的工具调用（不折叠、不翻译）；输入框上「模型」「思考」两枚旋钮的清单来自 `GET /backends`（后端自报），选了随消息的 `model` / `effort` 发出去、记进对话 |
| 需求 | `GET /workspaces/<id>/requirement`、`POST /workspaces/<id>/requirement/confirm` | 没确认时需求文档就是主页面（按二级标题一格一节，「待填」是空格），人**确认**（`requirement.lock`）；确认后收成顶部一条，助理又改了显示 diff、确认下一版。页面只渲染不编辑，改需求只走对话 |
| 产出 | `GET /workspaces/<id>/outputs/<stage>/<n>`、`POST …/outputs/<stage>/<n>/sign`、`GET …/jobs[/<jid>]` | 一条流一张表：横向是流经过的阶段（有什么阶段就几列，列头是阶段名 + 能力的人话），纵向是每一列跑过的每一次产出（编号 + 一个词：运行中 / 失败 / 待确认 / 已确认 / 完成），断点是两列之间一道线，右上角一句话说在等谁；点开侧滑看记录（来源、输入、状态）、目录里的文件（小文本直接渲染）、作业；流在这儿有断点就人**确认**（`signed.json`）。不在任何流里的产出只在最底下一行「其它」 |
| 文件 | `GET /workspaces/<id>/files?path=`、`GET …/file?path=`、`GET …/raw?path=` | 主页面的第二个镜头（页眉「看板 / 文件」切换，对话列两边都在）：左边一棵大纲式的树直接印在底上不加框——缩进导线、七个阶段目录显示阶段名与阶段图标并拉开成小节、每次产出那一层是编号 + 右对齐的状态词（冻结另加一把锁）、`.ai4sci/` 灰显、一层一层懒加载、根一层按工作区骨架排；右边是唯一抬起的面：头部是位置（面包屑写平台语义 + 文件名大字 + 大小与行数 +「在看板打开」「下载」），正文按种类渲染（代码高亮带行号、markdown 排版、图片、csv / tsv 成表，大的截断、二进制只给下载），产出那一层是它的记录与确认。**只看不改**：改动走对话（手改会撞冻结）。看板的侧滑里「打开目录」跳过来定位到那次产出 |
| 库 | `GET /workflows`、`POST /workflows`、`POST /workflows/check`、`GET /cap`、`GET /stages` | 编辑台的画布：节点是研究阶段（装能力 + 参数）或断点，边只表示顺序；边拼边查（问题贴到节点上）；存进库。研究者不改库 |

需求确认是框架唯一内置的门；断点几个、放哪由拼流的人定，一个断点 = 上一项的产出要人确认下游才能读。
界面上的两处确认是"只有人能确认"的唯一保证——CLI 里的 `ai4sci requirement confirm` / `ai4sci sign <stage>/<n>`
是给在终端里当协调层的人用的，研究助理的指南写明它不该替人确认。

## 网页怎么跑

```bash
make ui            # 装依赖（只进 ui/web/node_modules）并构建到 ui/web/dist
ai4sci serve       # 起后端并端出页面：http://127.0.0.1:8765
```

开发时两个进程：`ai4sci serve`（接口，8765）+ `cd ui/web && npm run dev`（页面，5173，接口按前缀代理过去）。
门禁 `make ui-check` = 素材不进仓的检查（`git ls-files ui/` 没有 png / jpg / mp4，纲领 P-17）+ 类型检查 + oxlint + vitest + 构建，已并入 `make check` 与 CI。

## 网页的结构

设计口径在 `docs/PRODUCT.md`（给谁用、反例、原则）与 `docs/DESIGN.md`（色板、字阶、布局）。
页面先认工作区：最左一条地方栏（先「工作区 / 编辑台」两个世界的开关，工作区世界里再列封面块与「新建」；编辑台是全局一个库，进了编辑台工作区块整段收掉）；没有工作区时主页面是门口那一屏（一句话 + 模板起工作区，循环视频背景）。
主页面 = 这个工作区的看板铺满 + 右边一列对话（可收，收起后右下角一枚圆形入口）。看板按 `requirement.lock` 在不在分两个状态：没确认，需求文档就是页面（一格一节，底下「确认」）；确认了，需求收成顶部一条，下面一条流一张表（横向阶段、纵向每次产出、断点是列间的线、右上角在等谁），产出点开侧滑。编辑台 = 画布铺满（React Flow：一条线性的链，阶段 / 断点两种节点；左上角阶段梯与题头，右上角库、保存与选中节点的配置；底下一层风景）+ 右下角圆形入口弹出的悬浮对话窗（造流助理）。
正文只许出现 `lib/humanize.ts` 翻译过的词；状态码、哈希、命令的输出只在展开层。对话里的工具调用是例外：原样一行（`chat/trace.ts::toolLine`）。

```
web/src/
  assets.ts   页面里全部图片 / 视频的 CDN URL，仅此一处（纲领 P-17）；素材清单在 docs/DESIGN.md
  api/        契约：types.ts（响应体的类型）、client.ts（每个端点一个函数，Scope 定域前缀）、sse.ts（事件流）
  chat/       对话：trace.ts（事件流折成条目、落盘的事件重放、工具行原样，纯函数、有单测）、ChatView（两个域共用，文案由父组件给）/ TurnView（人的气泡、工具行、回答、花费）/ Composer
  places/     Rail（宽屏的地方栏）、PlacesSheet（窄屏的清单）、place.ts（页面此刻在哪）
  workspace/  NewWorkspace（门口那一屏：一句话 + 模板起工作区）
  files/      主页面的文件镜头：Files（目录树 + 内容区；树按 `GET /workspaces/<id>` 的阶段与产出标语义）、derive.ts（一行是什么、文件怎么渲染、csv 切表、根一层的顺序，纯函数、有单测）、highlight.ts（highlight.js 五种语言，配色在 index.css 的 `.hl`）
  board/      主页面的看板：Board（按需求确认与否分两个状态；有作业在跑时轮询）、Requirement（未确认的整页 / 确认后的一条 + 侧滑 diff）、Flows（一条流一张表：阶段列、产出卡、断点线、在等谁）、OutputSheet（一次产出的侧滑：记录、文件、确认）、derive.ts（在等谁的一句话、下一步、产出的状态词、断点的短标签，纯函数、有单测）
  studio/     编辑台的画布：model.ts（链的数据：排版、插入、重排、页面形状 ↔ 文件形状，纯函数、有单测）、nodes（阶段 / 断点两种节点）、Palette（阶段梯与库的弹层）、Inspector（选中节点：勾能力、填参数、断点的确认事项）、Studio（React Flow 画布、边拼边查、保存）
  keys/       确认需求、确认产出两处人的动作（StarBorder 改装）
  sidebar/    对话列表抽屉
  components/ 零件 bits.tsx、Markdown.tsx、Backdrop（门口的视频背景）、Band / Scene（图 + 纱幕）、shadcn 生成的 ui/、reactbits 的改装件
  lib/        humanize.ts（术语翻人话、能力的人话说法，有单测）、stages.ts（阶段图标与流里一项的说法）、diff.ts（行级 diff，有单测）、useChats（一个域的对话清单）、format、取数 hook、署名记忆
```

依赖方向：`App → workspace / board / studio / chat / sidebar → keys / components → api`；`api/` 不 import 任何组件。
组件不直接 `fetch`，都经 `api/client.ts`。

## 不做（第一版）

- 画布上的分叉 / 并行：流是线性的（一条链），节点一进一出；顺序 = 阅读顺序，人摆过的坐标存在文件的 `layout` 块里
- 多用户、鉴权、token 级流式：后端是本机单人服务
