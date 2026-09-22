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
端点按域分前缀（纲领 P-16）：`/projects/<p>/…` 是研究助理的域（一个项目一位助理，工作区在它下面 `/projects/<p>/workspaces/<id>/…`，[#136](https://github.com/zephyr4123/TJU-AI4Science/issues/136)），`/studio/…` 是流程助理的域；对话四个端点两个域共用。下表里工作区端点的前缀都是 `/projects/<p>/workspaces/<id>`。

| 看板 | 端点 | 人在这里做什么 |
|---|---|---|
| 项目与工作区 | `GET /projects`（一行：标题、目标一句、几个工作区、几个在跑、`created_at` 取目录的 birthtime）、`POST /projects`（`id` / `title` / `goal`）、`GET /projects/<p>`（project.md 原文 + 每个工作区一行：需求状态、每阶段几次产出、每条流程走到第几步 / 在等谁、跑着的作业）、`POST /projects/<p>/remove`、`POST /projects/<p>/workspaces`（`id` / `title` / `template`）、`GET /projects/<p>/workspaces/<id>`、`POST …/workspaces/<id>/remove`、`GET /stages`、`GET /templates` | 首页的项目墙、门口起项目、项目页的工作区清单与「新建」（一个项目一位助理，一个工作区一份需求，P-15）；工作区那一整份里有需求、七个阶段的产出、每条流程的进度、作业 |
| 对话 | `POST <域>/chats`、`POST <域>/chats/<id>/messages`（SSE）、`GET <域>/chats[/<id>]`、`GET /backends` | 项目页正中间的输入框和研究助理说话（对话归项目，工作区页右边那块板上是同一段）、编辑台和流程助理说话；助理运行的每条命令以 `tool_use` / `tool_result` 事件流回来，落盘成 `turn-N/trace.jsonl`、随 `history[].events` 回来，页面重放成一行一条的工具调用（不折叠、不翻译）；输入框上「模型」「思考」两枚旋钮的清单来自 `GET /backends`（后端自报，每家带产品名与新对话用的值），选了随消息的 `model` / `effort` 发出去、记进对话；旋钮上只有具体值，没有「默认」（P-25） |
| 设置 | `GET /settings`、`POST /settings/agents`、`POST /settings/check`、`POST /settings/computes`、`POST /settings/computes/<name>/remove`；`GET /health` 的 `checks_ok` | 底座（两层各用哪家、每家清单与缺省、上次自检）、算力（清单、接一台、删一台）、存放（数据根在哪、可写、余量）；`check` 真探并记回 `last_check`；地方栏「设置」旁的点按 `checks_ok` 亮 |
| 需求 | `GET …/workspaces/<id>/requirement`、`POST …/workspaces/<id>/requirement/confirm` | 没确认时需求文档就是工作区页（按二级标题一格一节，「待填」是空格），人**确认**（`requirement.lock`）；确认后收成顶部一条，助理又改了显示 diff、确认下一版。页面只渲染不编辑，改需求只走对话 |
| 产出 | `GET …/workspaces/<id>/outputs/<stage>/<n>`、`POST …/outputs/<stage>/<n>/sign`、`GET …/jobs[/<jid>]`、`POST …/jobs/<jid>/stop` | 一条流程一张表：横向是流程经过的阶段（有什么阶段就几列，列头是阶段名 + 能力的人话），纵向是每一列跑过的每一次产出（编号 + 一个词：运行中 / 失败 / 待确认 / 已确认 / 完成），断点是两列之间一道线，右上角一句话说在等谁；点开侧滑看记录（来源、输入、状态）、目录里的文件（小文本直接渲染）、作业；流程在这儿有断点就人**确认**（`signed.json`）。不在任何流程里的产出只在最底下一行「其它」 |
| 文件 | `GET …/workspaces/<id>/files?path=`、`GET …/file?path=`、`GET …/raw?path=` | 工作区页的第二个镜头（页眉「看板 / 文件」切换，对话列两边都在）：左边一棵大纲式的树直接印在底上不加框——缩进导线、七个阶段目录显示阶段名与阶段图标、每次产出那一层是编号 + 右对齐的状态词（冻结另加一把锁）、`.ai4sci/` 灰显、一层一层懒加载、根一层按工作区骨架排；右边是唯一抬起的面：头部是位置（面包屑写平台语义 + 文件名大字 + 大小与行数 +「在看板打开」），正文按种类渲染（代码高亮带行号、markdown 排版、图片、csv / tsv 成表，大的截断、二进制不显示），产出那一层是它的记录与确认。**只看不改**：改动走对话（手改会撞冻结）。看板的侧滑里「打开目录」跳过来定位到那次产出 |
| 库 | `GET /workflows`、`POST /workflows`、`POST /workflows/check`、`GET /cap`、`GET /stages` | 编辑台的画布：节点是研究阶段（装能力 + 参数）或断点，边只表示顺序；边拼边查（问题贴到节点上）；存进库。研究者不改库 |

需求确认是框架唯一内置的门；断点几个、放哪由拼流程的人定，一个断点 = 上一项的产出要人确认下游才能读。
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
页面先认项目（一个项目一位助理，工作区是它的工位，[#136](https://github.com/zephyr4123/TJU-AI4Science/issues/136)）：最左一条地方栏只有三个键——首页、编辑台、设置（项目不在栏上列）。首页是项目墙：一格一个项目（名字、目标一句、几个工作区、建于哪天、几个在跑；封面压暗当底），右上「新建项目」；一个都没有就一句「还没有项目」加一枚「新建项目」；门口那一屏一句话起项目（第一个工作区跟助理说或在项目页「新建」）。项目页 = 正中间一只对话输入框（一个项目只有一位助理，入口只有这一个）+ 底下这个项目的工作区一行一个（状态一个词、走到第几步、产出几次）+「对话 · N」；输入框里打第一句就开一段新对话、页面切成整屏的对话，「‹ 项目名」回来。
工作区页 = 页眉「‹ 项目名  工作区 ▾（换兄弟工作区）  看板 / 文件」，看板铺满 + 右边一块对话板（还是项目的那一段；可收，收起后右下角一枚带字的玻璃键）。看板按 `requirement.lock` 在不在分两个状态：没确认，需求文档就是页面（一格一节，底下「确认」）；确认了，需求收成顶部一条，下面一条流程一张表（横向阶段、纵向每次产出、断点是列间的线、右上角在等谁），产出点开侧滑。编辑台 = 画布铺满（React Flow：一条线性的链，阶段 / 断点两种节点；左上角阶段梯与题头，右上角库、保存与选中节点的配置；底下一层风景）+ 右边同一块对话板（流程助理）。
正文只许出现词表里的词与后端给的中文名（纲领 P-21：能力 `title` `brief`、参数 `label`、阶段名、流程 `title`；产出 id 写「设计 · 1」）；状态码、哈希、命令的输出只在展开层。对话里的工具调用是例外：原样一行（`chat/trace.ts::toolLine`）。`copy.test.ts` 扫源码：禁用词与 `font-mono` 出了文件镜头、工具行、diff、文件清单就不过。

```
web/src/
  assets.ts   页面里全部图片 / 视频的 CDN URL，仅此一处（纲领 P-17）；素材清单在 docs/DESIGN.md
  api/        契约：types.ts（响应体的类型）、client.ts（每个端点一个函数，Scope 定域前缀；WorkspaceClient 是绑死在（项目，工作区）上的一组端点，看板 / 文件 / 两处确认拿着它取数）、sse.ts（事件流）
  places/     Rail（宽屏的地方栏：首页 / 编辑台 / 设置）、PlacesSheet（窄屏的清单）、place.ts（页面此刻在哪：首页 / 门口 / 项目 / 工作区 / 编辑台；上次在哪记在浏览器里，纯函数有单测）
  home/       Home（首页 = 项目墙，一格一个项目，空态一枚「新建项目」）、NewProject（门口那一屏：一句话 + 目标一行起项目）
  project/    ProjectPlace（项目的世界：拿着项目的对话与清单，项目页 / 整屏对话 / 工作区页三个样子来回不断线）、Hub（项目页：正中间输入框 + 工作区清单 + 对话抽屉 + 删除项目）、NewWorkspace（清单顶上展开的表单：一句话 + 学科）、derive.ts（一行工作区的状态一个词与细节，纯函数、有单测）
  workspace/  WorkspacePage（工作区页：页眉「‹ 项目名  工作区 ▾  看板 / 文件  …」，看板 / 文件两个镜头常驻只切显示，对话板在右）
  chat/       对话：trace.ts（事件流折成条目、落盘的事件重放、工具行原样，纯函数、有单测）、ChatView（两个域共用，文案由父组件给；板里带自己那行头，整页时头由外面给）/ TurnView（人的气泡、工具行、回答、花费）/ Composer（玻璃输入框：项目页正中间、对话底下都是它）/ useTuning（输入框上「助理 / 模型 / 思考」三枚片的状态）/ ChatDrawer（「对话 · N」的抽屉）/ ChatPanel（右边那块板）
  files/      工作区页的文件镜头：Files（目录树 + 内容区；树按 `GET …/workspaces/<id>` 的阶段与产出标语义）、derive.ts（一行是什么、文件怎么渲染、csv 切表、根一层的顺序，纯函数、有单测）、highlight.ts（highlight.js 五种语言，配色在 index.css 的 `.hl`）
  board/      工作区页的看板：Board（按需求确认与否分两个状态；工作区那一整份由 WorkspacePage 拉、与文件镜头共用、有作业在跑时轮询）、Requirement（未确认的整页 / 确认后的一条 + 侧滑 diff）、Flows（一条流程一张表：阶段列、产出卡、断点线、在等谁）、OutputSheet（一次产出的侧滑：记录、文件、确认）、derive.ts（在等谁的一句话、下一步、产出的状态词、断点的短标签，纯函数、有单测）
  studio/     编辑台：StudioPlace（页眉 + 两个镜头 + 流程助理的对话板）、Studio（流程 / 能力常驻只切显示；Editor 是 React Flow 画布、边拼边查、保存——文件名由标题生成不上屏）、model.ts（链的数据：排版、插入、重排、页面形状 ↔ 文件形状，纯函数、有单测）、nodes（阶段 / 断点两种节点，能力小片 hover 一行、点了跳详情）、Palette（阶段梯与流程库的弹层）、Inspector（选中节点：勾能力、填参数——名字是描述符的 label、断点的确认事项）、Catalog（能力镜头：按阶段陈列 SpotlightCard 小卡，详情页是常驻返回键 + 一行 / 参数 / 五栏）
  keys/       确认需求、确认产出两处人的动作（StarBorder 改装）
  settings/   设置那块板（底座、算力、存放、外观）
  components/ 零件 bits.tsx、Markdown.tsx、Top（页眉：回上一级、标题、镜头开关、封面底）、Backdrop（门口的视频背景）、Band / Scene（图 + 纱幕）、shadcn 生成的 ui/、reactbits 的改装件（MagicBento 项目墙的格子、StatusMark 状态符、GlassSurface、GlideSelect、HoldButton……）
  lib/        humanize.ts（状态词与谁产的，有单测）、stages.ts（阶段图标、按阶段分组、经过哪几个阶段）、slug.ts（项目 / 工作区 id 与流程文件名从标题生成，有单测）、diff.ts（行级 diff，有单测）、format.ts（数字、钱、时间、只到天的日期，有单测）、useChats（一个域的对话清单）、取数 hook、署名记忆
```

依赖方向：`App → home / project / studio → workspace → board / files / chat → keys / components → api`；`api/` 不 import 任何组件。
组件不直接 `fetch`，都经 `api/client.ts`。

## 不做（第一版）

- 画布上的分叉 / 并行：流程是线性的（一条链），节点一进一出；顺序 = 阅读顺序，人摆过的坐标存在文件的 `layout` 块里
- 多用户、鉴权、token 级流式：后端是本机单人服务
