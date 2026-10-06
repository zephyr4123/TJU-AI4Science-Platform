# 变更日志

本仓库所有值得注意的变更都记录在这里。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

- 每个 PR 在 **Unreleased** 加一行：一条一行、≤ 200 字、带 #issue（`changelog.sh check` 守着）；发布时 `make release VERSION=x.y.z` 把它轮转成版本小节并打 tag，推送 tag 即触发 GitHub Release。
- 从 1.0.0 起承诺兼容：冻结的契约与 MAJOR / MINOR / PATCH 的判据见 CONTRIBUTING「版本与发布」；预发布 `vX.Y.Z-rc.N` 不占小节，Release Notes 取 Unreleased。
- 条目分类用：新增 / 变更 / 修复 / 移除 / 安全。

## [Unreleased]

### 新增

- 端点 `GET /attention`（跨项目要人做的与在跑的）与 `GET /usage?days=`（花费汇总）；适配器端口加 `Usage` 与各家 `usage()`、`Price` 与各家定价表 `PRICES`（价照 cc-switch 的内置表），Codex 执行层留档第一行记下用的模型（外层 #256）

### 变更

- 对话框（项目与编辑台两处）去掉「助理 / 模型 / 思考」三枚片：哪家、模型、思考深度只在设置里改，开对话照设置抄、改设置只影响之后开的对话；开对话与发消息的端点不再收 `backend` / `model` / `effort`，带了是 400（外层 #257）
- 首页改两栏：左半边项目清单、右半边「待你确认」「运行中」两张小卡与「花费」（近 7 / 30 / 90 天的折算成本或 token：成本、调用、token、缓存命中四个数，按天的柱子，项目 / 模型 / 会话 / 定价四张表；Codex 不报成本，照定价表折算），暖色与清单映衬，两边一样高；右上角一行同步（几分钟前同步、立即同步、自动刷新隔多久）；页底一行页脚（外层 #256）
- 工作区看板改成竖向时间线：需求收进标题下一行；一条流程一块面不再套框，阶段与断点是轨上的节点；产出一行一次、名说全（第几次、生成者、读取了哪次、用时），多了只露最近两次；「其它」改叫「单独运行」（外层 #255）

### 修复

- 对话花费报不出美元（Codex 订阅）时记「未知」不记 0：对话清单里不再一排 $0.00；旧数据用外层 scripts/oneoff/fix-unknown-chat-cost-256.py 修（外层 #256）
- 开发时的代理漏登记新端点会让页面拿到 index.html：加了 server 与 vite 前缀清单的对账测试（外层 #256）
- 看板漏显示产出：记了流程却没记第几步的那次产出，流程表与「其它」都不收，现在进「单独运行」（外层 #255）

## [1.5.1] - 2026-10-06

### 变更

- 首页的项目墙改成一行一个的项目清单：不放封面图，整张清单一块玻璃，名字与目标在左、三列事实在右对齐；加搜索框，按名字与目标筛，搜中的字标出来（外层 #249）
- 全站底图统一成首页那张「云雾里的山」：项目页、对话、工作区看板、设置、编辑台的大背景与页眉、对话抽屉顶上那条都换成它，按项目挑的六张封面与其余三张底图不再引用（外层 #251）
- 设置「外观」三档从「浅 / 深 / 跟随系统」改成 Light / Dark / Auto，字数齐了滑块不再显得怪（外层 #252）
- 侧边栏与页眉：同一种磨砂连成 L 形框，分割线换成两头渐隐的双层细线（左上角不再交成「T」）；选中的键加渐变、高光与淡靛光，没选中的去框改软底；页眉上一级与标题之间加淡斜杠（外层 #253）

### 修复

- 首页清单每行「…」里能直接删项目；项目页左上角「‹ 首页」，换地方进浏览器历史，后退 / 前进能用（外层 #250）
- 点进项目先闪一块骨架：项目详情算签字有没有过期时把 `.venv` 几万个文件全列一遍、几百 MB 原文每次重读，改成不进跳过的目录、文件没变不重读（635 ms → 20 ms）；首页鼠标停到哪行先取哪个项目（外层 #250）

## [1.5.0] - 2026-10-05

### 新增

- 文献检索与精读边跑边往产出目录写 `progress.jsonl`（`framework/files.py::append_event`），产出悬浮窗最上面按能力画定制的进度面板：检索是方块连线加收录蜂巢，精读是原文沿流水线流成笔记（外层 #242 #244 #245）
- 对话输入框上方挂「运行中 N」：项目里有作业在跑就出现，展开是每个作业与已运行多久，点一行去看那次产出的进度面板（外层 #243）

### 变更

- Codex 模型清单跟上 0.160：默认 GPT-6.1 Sol，另有 6 Astra（最强）、6 Luna（快）、5.6 Terra（上一代，旧配置与旧对话照样能用）；最低版本升到 0.160.0，`codex update` 一行升级（外层 #247）
- 看板上点开一次产出、点开需求全文不再是右边的侧滑，改成上下左右居中的圆角玻璃悬浮窗（`components/GlassDialog`，遮罩只压暗不糊）；「确认」键的点击火花没人点时不再每帧重画，产出窗开着时 Chrome 的 CPU 从 12% 降到 3%（外层 #242）
- 产出窗不再平铺目录里的文件，只一行「936 个：图片 791 · 文档 53 · …」加「打开目录」；产出记录的 `files` 只给路径与大小、不再带正文（要正文走 `…/file?path=`；一次检索从 1 MB 到 68 KB）、不再每 4 秒重拉，Markdown 字没变不重新解析：点开一次文献检索不再卡 3.4 秒（外层 #242）
- 确认需求、确认产出、叫停作业都不再填署名：本地部署，能按的只有用户自己，服务端记登录名（与 CLI `--by` 的缺省一样）；端点不再要 `by`，旧页面带着也不报错（外层 #242）
- 产出窗的记录改成一张白底表、名说全（生成者、所属流程、读取的产出、运行时间、生成文件……），去掉 `literature ok …` 那行与「被 … 读过」那句，确认只剩一颗键；进度面板的「详情」同一种排法（外层 #242）
- 项目页工作区的小字写「流程「文献调研」1 / 1 步」「共产出 6 次」，看板每条流程的题头前加「流程」二字：只写流程名看不出它是流程（外层 #242）

## [1.4.0] - 2026-10-05

### 新增
- 出厂流程「文献调研」`literature-survey`：一格里先检索、再精读，产出到精读的 sources.md 为止；不排写作阶段，综述之后单独设计（#239）
- 文献精读 `literature-read`（文献阶段第二个步骤）：读上游 sources.md 认出有原文的论文，一篇一个执行层会话（同时 4 个）按需求写七节笔记，主要结果每条抄一句原句，框架零模型去原文里核；失败只记那一篇；sources.md 是一句话目录 + 笔记在哪 + 原句对上几条（#233）
- 文献检索加起始年份 `since`：只查、只收这一年及以后发表的，推到四家检索与「谁引用了它」里，更早的种子与参考文献不交给模型筛；只认四位年份，写成 3 当场拒（#227）

### 变更
- 文献检索下载原文改成并行：同时 8 篇、同一站点同时 2 篇，提交顺序按站点轮着排；演练收录的 39 篇有链接的实测 298 秒 → 58 秒，成功篇数不变（#229）

### 修复
- 执行层会话没开工就失败（退出码非零、没超时、一个文件没动、没花钱，比如模型一时满载）隔 30 秒、90 秒各再起一次，所有能力都受益；原来只起一次，演练里文献精读因此丢了关键论文 Zep，同样的事落在检索某一跳上整条检索判失败（#235）
- 项目页上流程进度写走过几项：原来直接写后端给的下标，总少一（走完的单项流程写成 0 / 1，一项没走写成 -1 / 6）；走完写满（#238）
- 流程一格里点了几个步骤、后一个读前一个的产出（先检索再精读），后一个记在同一格，看板上摆在那一格；这一格后面的断点不拦它，往后走的照旧要签。原来只往下一格找，落空就算在流程之外，看板上看不到（#237）
- 工作区文件里的相对链接点了能打开：文件镜头与看板产出里渲染一份 markdown 时，`../../literature/2/notes/3/note.md` 这类相对路径按这份文件所在的目录解开，在文件镜头里打开，出了工作区的只显示文字；文献精读的 sources.md 把每篇笔记写成链接。原来只显示文字（#236）
- 需求各格都填了、只有模板开头的说明带「待填」两个字时，页面不再说「尚有待填」不让确认：页面与后端确认读同一个判断，只看格子（#234）
- 对话里指向本项目文件的链接点了能打开：助理写的本机绝对路径或项目内相对路径，页面认出是哪个工作区的哪个文件，跳过去在文件镜头里打开；认不出的本机路径只显示文字，网址新开一页；指南教助理写项目内相对路径。原来点了落到页面外壳上（#231）
- 页面看得见作业跑完叫醒助理的那一轮：对话接口带上正在跑的那一轮（别的进程起的也算）与还有几个作业会来叫醒它，页面据此定时重读、把这一轮摆出来、锁住输入框，跑完看板跟着重读；原来要刷新才出来，期间输入框看着能发、发了被拒（#230）
- 文献检索把同一篇的不同版本（预印本 / 会议 / 期刊各一个 OpenAlex 编号）认成一篇：题目一样、年份相近的并进去，补上编号与原文链接，不再多占筛选名额、列两遍；演练里 130 篇有 6 组，Mem0 等收的是没有 PDF 的期刊版（#232）
- 文献检索失败不阻塞：Crossref、arXiv、Europe PMC 各查各的，某家重试用完仍失败就不再问它，三家一共等 120 秒，没查成的写进 `sources.md`；原来逐条串行重试，arXiv 持续 429 时一次检索要多等近一个小时（#228）

## [1.3.1] - 2026-10-04

### 变更
- 文献检索交给筛选会话的清单砍短：摘要截到 500 字，「怎么找到的」只数每种几条（给人看的 `sources.md` 照旧写全）；连同关掉自动记忆，一次检索约 0.78 → 0.60 美元，三个分不变（#219）

### 修复
- 文献检索：筛选结论文件漏写、抄错号、同一篇写了相反结论的几篇单独补筛一次，补完还缺才判失败，不再一字抄错整次作废；arXiv 被限速（429）时按 5 / 15 / 30 / 60 秒退避，几次检索同时跑不再成批丢检索词（#216）
- Claude Code 两层会话的「工具怎么用」不再教 2.1.289 已经没有的 Glob / Grep 工具，改教单条的 ls、find、grep：照旧指南找文件白耗几轮（#219）
- 文献筛选的结论文件在提示里给绝对路径：给相对路径时执行层拼路径丢了一级目录、写到产出目录根上，整次检索作废（#219）

### 安全
- Claude Code 的两层会话关掉 CLI 的自动记忆：`--setting-sources ""` 挡不住它，会话所在仓库若被这个人用 Claude Code 开过，这个人的 MEMORY.md 记忆索引整段进了平台会话，一次文献筛选多读 7700 token、多花三成（#222）

## [1.3.0] - 2026-10-04

### 新增
- 文献阶段的第一个步骤 `literature-search`：执行层写检索词与纳入标准、用自带搜索找种子，框架拿检索词查四家不要 key 的学术库（OpenAlex、Crossref、arXiv、Europe PMC）、顺着引用往外扩几跳、每跳交执行层看摘要筛，收录的下原文解析，写 `sources.md`；不要 key 也能跑，设 `OPENALEX_API_KEY` 额度大十倍（#212）

### 修复
- 平台自带的 `pdf` skill 下载链接时只读一次，连接中途断了也不报错：真跑里两篇 arXiv 的 PDF 停在正好 1 MiB 与 8 MiB、解析报 `not a dict (null)`；改成读到结尾，比 Content-Length 短就按下载失败退 3（#212）

## [1.2.0] - 2026-10-01

### 新增
- skill 分类表 `framework/skills/shelves.py`：七个阶段加「通用」，每架再分 tag（实验分生物、化学与药物、模型训练等 18 个，共 37 个），202 个 skill 全部归位（#205）

### 变更
- 编辑台能力镜头一个阶段一行：步骤与 skill 挂在同一阶段下、行前标签分 tag，skill 按 tag 分组，末行「通用」，查找对所有行生效，出处不上屏；配置板默认列本阶段与通用的，按 tag 折叠（#205）
- skill 三处库同一种摆法 `<库>/<架>/<tag>/<name>/`，摆错地方的隔离成不合格、`make skills` 不过。迁移：自加的 skill 与领域包的 `skills/<name>/` 挪进分类表里的 `<架>/<tag>/`（#205）
- `GET /skills` 去掉 `library` `shelf` `where`、加 `stage` `tag`；`show skills` 等的位置一列写「实验·生物」，中文词也认 tag 名；收录台账去掉 `shelf`，位置以目录为准（#205）

## [1.1.1] - 2026-10-01

### 修复
- 作业记录、对话 meta、产出 meta 与签字、需求的锁、流程文件写盘改成原子的：边跑边读的一方会读到空文件（`cap --detach` 偶发报错，发布门禁撞到过）（#204）

## [1.1.0] - 2026-10-01

### 新增
- 编辑台：能力镜头里的 skill 按出处分架、能查找；配置板默认只列已挂的、平台自带的、本阶段那一架的，其余「查找全库」（#197）
- 收录社区 skill 库 `skills-curated/`：K-Dense、Nature Skills、AI Research SKILLs 按七个阶段加「通用」分拣，台账 `provenance.yaml` 记来源、提交、许可证、改动；`ai4sci show skills` 按词、按阶段查库（#198）
- 流程命名带血缘：机器名平台起（派生的 `<家族名>-<序号>`）、文件记 `from`、差异现算、库里结构一样的拒；`ai4sci workflow new [--from]`，编辑台流程库按家族分组、能「另存」（#199）
- `ai4sci skill show <name> <文件>` 读 skill 目录里的参考与模板（#197）
- 环境变量 `AI4SCI_CURATED_SKILLS_ROOT` 指收录库；`GET /skills/<name>` 取一个 skill 带正文（#197）

### 变更
- 流程里同一格挂同一个能力两次算问题；查重与差异同一个口径（一格里挂的先后不算、参数 2 与 2.0 相同）（#199）
- 升级：1.0.x 的数据根跑一次外层的 `scripts/oneoff/migrate-to-1.1.py <数据根>`（旧对话里塞进人话的指南挪出去、meta 去掉 `guide_sha`、续不上的会话改开新会话、流程实例补 `from`）（#200 #199）
- 能力按项目装载：研究助理与执行层只装平台自带的 skill 加本项目流程实例上挂的能力，装载之外的 `skill show / run` 与 `cap` 拒，领域 skill 也要挂上。迁移：先 `ai4sci flow take <流程>`，要用的 skill 挂到实例的格子上（#197）
- skill 宽进：规范外的 frontmatter 字段只提醒（平台自带的 `skills/` 除外，门禁里算问题），不合格的单个隔离、不拖垮整库；收录与领域包的脚本首次运行时按锁建环境，`make skills` 只预热平台自带的（#197）
- `show caps` 文本里 skill 按出处计数不逐个列；`show caps --json`、`GET /skills` 不带 SKILL.md 正文，`skill show` 不打库的路径。迁移：正文用 `ai4sci skill show <name>` 或 `GET /skills/<name>`（#197）
- `ai4sci skill` 与 `show skills` 按 cwd 所在的项目判装载，cwd 不在项目里才看 `AI4SCI_PROJECT`；流程上拼错的名字列为不可用、不再关掉那个阶段（#197）

### 修复
- 项目共用的原件（`projects/<p>/materials/`）进不了设计与复现：开工时与工作区的原件一起搬进 `data/`，同名以工作区的为准；复现的论文代码两处都找（#201）
- Claude Code 续接对话时沿用开会话那份指南、新送的不生效（实测）：改成与 Codex 一样只在开会话时送，指南中途变了由框架把变了的几节塞进那一轮，人的原话照原样存（#200）
- `ai4sci skill run <name> --script <文件>` 里写在名字后面的 `--script` 被当成脚本参数吞掉（#198）

### 移除
- 一个第三方 key 都不要：`download` 不再读 Hugging Face 凭据，只拉公开的仓库；门禁查三处库里要凭据的用法。迁移：门控仓库在网页上手动下好放进 `materials/`（#196）
- 协调层端口的 `guide_channel`（两家都只在开会话时收指南，没有第二种了）；`RunContext.domain`（没有读取方）（#200）

## [1.0.1] - 2026-09-23

### 修复
- 编辑台存的流程落进出厂的 `workflows/`（源码模式进 git、装包后升级会丢）：库分两层，人存的进数据根 `studio/workflows/`，`show workflows` / `flow take` / 页面两层都读，出厂的只读、重名拒（#149）

## [1.0.0] - 2026-09-23

### 新增
- 项目层：一个项目一位助理，工作区是项目里一份需求；`projects/<p>/` 目录、`project new / remove`、`show projects / project`、工作区级命令带 `--ws`，跨工作区 `--from <ws>:<stage>/<n>` 只限同项目（#136）
- 页面改项目口径：首页项目墙、门口一句话起项目、项目页正中的对话入口 + 工作区清单、工作区页页眉「‹ 项目名 工作区 ▾」（#136）
- 作业结果进那段对话的收件箱：空闲当场念，忙就排队，一条不丢（#136）
- 删：项目、工作区、对话、产出（只删叶子）、流程实例、库里的流程，级联清会话与机器上的镜像，出厂的不能删；页面上按住一秒才算数（#134）
- 能力两个 tag：步骤（`ai4sci cap`）与 skill（`ai4sci skill run`），两种都能挂到流程格子上，`GET /skills`（#113 #134）
- Codex 适配器：执行层与协调层、`probe()` 自检、私有 `CODEX_HOME` 隔离、`ai4sci` 在沙箱外跑（#131 #135）
- 按人的底座清单 `~/.config/ai4sci/agents.yaml`、`ai4sci agent list | check | use`、`ai4sci check` 冷启动自检（#132 #133）
- 设置端点与页面「设置」悬浮板：AI、算力、存放、外观；旋钮上只有具体值，没有「默认」（#133 #134）
- 复现流程 `reproduce`：`reproduction` 原码复现基线、`reproducibility` 复现性分析、`download` skill、`sources.md` 文献主文件、`templates/reproduce.md`（#120）
- `env use` 用机器上现成的解释器、`env add` 往现成环境补包、`env resolve --from`（#118 #120）
- 执行层会话额度按能力给、`analysis --feedback`、对话锁记 pid、指南变了提醒（#122 #123 #129）
- 环境收纳：uv 管一切（`uv.lock`、`make venv`）、出厂件进 wheel（`make package`）、`make up` 一行起、`make clean / purge`（#138）
- 平台的标（锥形瓶 + 星芒）、favicon、每个对话入口的欢迎屏；编辑台对话窗真浮起来、断点改成小圆点（#139）
- 文档全面对齐代码：`CLAUDE.md` 纲领化；`framework/` `tests/` `ui/` 各一份 README；`docs/add-a-domain.md`；两份助理指南标明是线上 prompt；`AGENTS.md` 符号链接（#140）
- README 做成代码侧的地图：系统组件图 + 文档索引；`framework/README.md` 分层图与两张时序图；`ui/README.md` 状态机与依赖图（#141）
- `CONTRIBUTING.md` 合并前清单；`changelog.sh` / `release.sh` 认 `-rc.N` 预发布；CI 在 `release/**` 上跑；PR 模板与 CODEOWNERS（#17 #142）
- 产出 `meta.yaml` 记执行层用的哪家、模型与思考深度（`agent`）；`ai4sci skill run --ws <名字>` 在那个工作区里起脚本（#140）

### 变更
- 从 1.0.0 起承诺兼容：冻结 CLI、框架认的文件、目录布局、端点、SKILL 格式、两份清单与三个端口，不兼容改动走弃用周期（#142）
- 助理会话里 `requirement confirm` 与 `sign` 一律拒（只有人能确认）；流程助理只放行 `ai4sci show` 与 `ai4sci workflow`（#140）
- 助理的本子搬到 `experiment/<n>/.ai4sci/journal.md`，不再算进产出 hash；实验被引用或签过之后照样能记（#140）
- `AI4SCI_COORDINATOR_MODEL` `_EFFORT`、`AI4SCI_EXECUTOR_MODEL` 退役，模型与深度从 `agents.yaml` 读；老对话 meta 里的 null 一次性填成当时缺省（#130）
- 旧的散装工作区搬成项目：外层 `scripts/oneoff/migrate-workspaces-to-projects.py`，只搬不删（#136）

### 修复
- `env use` / `env add` 改走 `uv pip freeze / install --python`，uv 建的没有 pip 的环境（平台自己的 venv 就是）也能登记、能补包；内仓 CI 从 7a4638b 起一直红的两条测试随之绿（#144）
- σ 由框架从 `baseline/repeats/` 算，执行层不再自己写 `sigma.json`；复现的种子照论文，不用平台的 42–46（#137）
- `compute check` 与 `env use` 带解释器路径；Codex 工具行显示命令、web_search 配对（#137）
- 分层检查看见 `from framework import cli` 这种写法；两条找旧路径永远跳过的测试改指到 `projects/`（#140）
- 算力快照目录已存在时的报错改成 `--continue … --resume`；schema 与注释里指向已不存在的 `packs.md` / `runstate.py` / `loop resume` 的说法清掉（#140）
- `design` 与 `reproduction` 两份提示词共用一份 harness 约定，复现骨架里写死的种子改成占位（#140）

### 移除
- 空包 `tools/`、死函数 `env._run` / `outputs.touch_output` / `computes.default_name`、前端死代码与没人用的样式类（#140）
- 页面的 `ThemeToggle`（主题开关搬进设置）、`Dock` / `FoldText` / `TiltedCard`（#134 #136）

## [0.2.0] - 2026-09-17

### 变更
- 页面与指南说人话（外层 [#69](https://github.com/zephyr4123/TJU-AI4Science/issues/69)，主人实测反馈）：「按钮」「能力单元」这类内部词从指南前言、`coordinator/README.md`、页面文案里清掉，改成「查了有哪些能力」「跑了基线」「写了分析，放到后台跑」这种直白句子（`humanize.ts` 每条命令一句）；被拒的命令翻成一句人话不贴英文；折叠行改成「助理做了 N 件事」。白名单也放行带 `.venv/bin/` 的老写法（老会话照自己以前几轮的写法来，前期别设坎），指南前言明说「以前写过带路径的现在一律写 `ai4sci`」
- 主页面重做（外层 [#67](https://github.com/zephyr4123/TJU-AI4Science/issues/67)）：右栏换成**流程脊柱**——当前 run 照的那条流一步一个模块（`spine/derive.ts` 从便条、作业、两颗键的记录算状态：实心 / 跑着 / 轮到助理 / 等你按键 / 轮到你 / 还没；没照流的老 run 按 auto-research 从文件推），模块内容按能力种类通用渲染（起点、基线→最好、分析摘要、验证结论），跑着的那步用 reactbits ElectricBorder 描边、ShinyText 报状态；没有 run 时脊柱是需求对齐（intake 那条流，状态从任务包阶段与发布记录推）；发布 / 验收两颗键搬到 `keys/`，用 reactbits StarBorder 改装成琥珀键；对话：研究者的话进靛蓝气泡，助理回答开头那句短结论用宋体立起来，按过的按钮折成一行「助理按了 N 个按钮」，轮次花费写成一句话；需求 / 结果两块旧看板删掉
- 设计系统第三版（外层 [#66](https://github.com/zephyr4123/TJU-AI4Science/issues/66)，母 [#64](https://github.com/zephyr4123/TJU-AI4Science/issues/64)）：五色 tokens（纸 / 墨 / 靛 / 铜绿 / 琥珀，颜色是信息）与深色模式（跟系统，`data-theme` 可强制），思源宋体只给结论与步骤标题、IBM Plex Sans 正文、Plex Mono 命令（Geist 去掉），`.t-step` / `.paper-grid` 两个新样式；壳改成顶栏（名字、当前对话、花费一句话、reactbits PillNav 改装的主页面 / 编辑台胶囊）+ 两块看板：主页面对话 + 右栏（需求 / 结果，#67 换脊柱），编辑台放工作流墙；`docs/DESIGN.md` 重写
- CLI 主导封装（外层 [#60](https://github.com/zephyr4123/TJU-AI4Science/issues/60)，纲领 P-14）：协调 agent 的 Bash 白名单收成 `Bash(ai4sci *)` 一条，`ClaudeCodeChat.build_env` 把本 venv 的 bin 追加进 PATH 让裸 `ai4sci` 找得到；指南前言写明一条命令一行、不加路径、不挂环境变量、不接管道，没有按钮就停下来说「平台缺这颗按钮」；指南第 5 步去掉 `AI4SCI_EXECUTOR_MODEL=sonnet` 前缀（执行层模型是起服务的人配的），接任务步骤改成先 `cap init` 再填模板，「撒一批起点探尽头」这句服务里做不到的指令删掉、改成问研究者或文献、没有就空着；`test_chat_guide` 加 lint：指南代码块里每条命令以 `ai4sci ` 开头。实验 #59 里 agent 照指南敲带前缀的命令被白名单拒、裸跑 python 探尽头被拒、只能逐文件 Read + Write 搬数据
- `docs/PRODUCT.md` 设计原则加两条（外层 [#58](https://github.com/zephyr4123/TJU-AI4Science/issues/58)，拍板记录，页面未改）：看板随工作流变、不写死流程；两块看板以可写目录划界，需求对齐在主页面
- 自定义工坊第一步（外层 [#56](https://github.com/zephyr4123/TJU-AI4Science/issues/56)）：协调 agent 可写目录加 `workflows/`（`chat/guide.py`），指南加「拼一条自己的流」一节（文件格式、先 `show flow` 后存、存完 `show workflows` 校验；样例文件有测试保证真能过）。实验 #55 里 agent 拼出了流却存不下来，现在能了
- 长按钮不进后台（外层 [#57](https://github.com/zephyr4123/TJU-AI4Science/issues/57)）：`ClaudeCodeChat` 起会话时 `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`，`BASH_DEFAULT_TIMEOUT_MS` / `BASH_MAX_TIMEOUT_MS` 抬到与本轮超时一样长；指南前言与「不要做的」写明 `ai4sci cap` 前台等、跑不完分批。实验 #55 里 `claude -p` 把超过 2 分钟的 `cap experiment` 自动挪到后台，一轮结束子进程被杀，第 4 轮死在半路
- 文档即接口（外层 [#54](https://github.com/zephyr4123/TJU-AI4Science/issues/54)，纲领 P-13）：`capabilities.discover()` 扫完子包再查整份清单——同级别里没有两颗能力声明同一个输出路径、每个输入路径要么是种子要么是同级某颗能力的输出，名字写错在加载时就被拒。`checkpoint.json` 归为 run 种子（`contracts.flow.RUN_SEEDS`；建它的是 `start`，experiment 只改它），experiment 的描述符不再把它记成输出
- 能力归到科研阶段下（外层 [#53](https://github.com/zephyr4123/TJU-AI4Science/issues/53)）：描述符契约加 `STAGES` 七个（文献、假设、设计、实验、分析、写作、验证）与三个必填字段 `stage` / `title` / `what`，人话标题与说明从页面的 `humanize.ts` 搬进描述符，页面与以后的 TUI 读同一份；阶段是标签不定先后，目录不动。`show caps` 按七个阶段列、空阶段标「还没有这一步的能力」，每颗带 `used_by`（从工作流文件反查，能力上不写）；`show workflows` / `show flow` / `GET /workflows` / `GET /flow/check` 带 `covers`（覆盖哪几个阶段，按步骤顺序算）与 `remarks`（有实验或分析却没有验证提醒一句，不拦）；新端点 `GET /stages`。工作流页的能力清单改按阶段分组，工作流卡片加「覆盖 …」一句
- 命令行收成四类（外层 [#52](https://github.com/zephyr4123/TJU-AI4Science/issues/52)）：`cap` 能力（agent 按）、`sign` 键（人按：`sign task` 发布 = 原 `task publish`，`sign run` 验收 = 原 `run accept`）、`show` 查询（只读：`show tasks` = `task list`、`show task` = `task validate`、`show run` = `status`、`show caps` = `cap list`、`show workflows` = `flow list`、`show flow` = `flow check`）、`chat` / `serve` 入口。并掉的：`loop run|resume` 就是 `cap experiment [--resume]`；`run extend` 成了 `cap experiment` 的参数（`--patience` / `--max-iterations` / `--max-cost-usd` / `--reason`，先续命再跑）；`run new` 是能力 `cap start`；`task env build` 不再单独按，`cap baseline` 缺环境就自己建。`Param` 类型加 `bool`（CLI 上是开关）。0.x 不承诺兼容，老命令直接没了

### 新增
- 编辑台（外层 [#68](https://github.com/zephyr4123/TJU-AI4Science/issues/68)）：工作流墙（reactbits SpotlightCard 改装的卡：标题、一句话、覆盖哪几段、几步、提醒，「照这条拼」）、七段能力货架（空的留空位，点一颗进拼流台）、拼流台（加人的事、加发布 / 验收键、上下移、改文字，通不通当场问 `GET /flow/check`，存成文件）。后端加 `POST /workflows`：`contracts.workflows.save_workflow` 与读文件走同一个 `parse_workflow`，形状与通不通都过了才写 `workflows/<name>.yaml`（名字只认小写英文加连字符），同名不覆盖除非明说；cli 注入 `_save_workflow`，chat 层照旧不认识 capabilities。旧的工作流页删掉
- 助理的话逐字流出（外层 [#65](https://github.com/zephyr4123/TJU-AI4Science/issues/65)）：`Chat` 端口加 `delta` 事件（刚到的几个字，不是累计；同一段说完仍有完整的 `text`），契约写明每家适配器都必须逐字吐；Claude Code 适配器开 `--include-partial-messages`，只翻 `content_block_delta` 的 `text_delta`（thinking / signature 不翻）；对话层往外吐但不落盘（events.jsonl 只留完整事件）；`chat send` 逐字打、完整 text 到了只补换行；SSE 多一种 `event: delta`；页面把片段攒进正在说的那段并带光标，完整 text 到了整段替换
- 异步作业、等待状态与叫醒（外层 [#63](https://github.com/zephyr4123/TJU-AI4Science/issues/63)，R-25）：每颗 `cap` 加 `--detach`，把去掉它的同一条命令起成独立进程当作业（新会话，不随 agent 的轮次死；`framework/run/jobs.py`，记录在 `<runs 根>/jobs/<id>.json` + 日志，子进程跑完回写结论行，pid 探活把没人回写的记成 lost），`show jobs` / `show job <id>`、`GET /jobs[/<id>]`，run 看板带 `job` 与 `jobs`。`cap start --workflow <name>` 把那条流快照进 `runs/<id>/workflow/`，`flow.json` 记步序（`run/flow_state.py`）：run 级能力跑成后框架记它落在流的第几步（记录不是决策，流外的按钮不动），「在等谁」现算（等作业 / 等人按键 / 等人 / 轮到助理 / 走完），`show run` 末尾一行、看板 `flow`。叫醒：`Chat` 端口加 `chat_id`，适配器经 `AI4SCI_CHAT_ID` 传给 agent 按的按钮，作业记下它；跑完 `chat/notify.py` 以「框架」的身份给那段对话发一轮（对话忙就隔 15 秒再试，最多半小时，等不到记回作业），一轮多了 `origin`（人 / 框架），transcript 与 history 照实标。指南：长按钮 `--detach`、开实验带 `--workflow`、不在一轮里干等
- 第 7 颗能力 `cap init` 起任务包（外层 [#60](https://github.com/zephyr4123/TJU-AI4Science/issues/60)）：`ai4sci cap init tasks/<id> --domain --materials --python --lock` 建目录、研究者的文件夹整棵搬进 `data/`（跳过 .git / .venv / __pycache__ / .DS_Store）、写 `env/` 两个文件、`manifest.yaml` 与 `design.md` 放带说明的模板（模板在能力子包里，`{{id}}` `{{domain}}` `{{source}}` 替换），已存在的目录拒绝覆盖。描述符契约加 `creates_target`（唯一一颗目标目录还不存在的能力，CLI 据此不查目录）；`packs.PLACEHOLDER`「待填」进 `intake_problems`，模板没填完发布键不签；`workflows/intake.yaml` 第一步改成它
（外层 [#52](https://github.com/zephyr4123/TJU-AI4Science/issues/52)）：`workflows/*.yaml` 一个一个写预装的拼法（`intake` 接一个新课题、`auto-research` 自动做实验；步骤是能力 `cap`、人按的键 `key` 或纯人的事，`assumes` 声明前提），`contracts/workflows.py` 读文件查形状、能力步骤交给 `check_flow` 核对，`ai4sci flow list` 与 `GET /workflows` 列出来。`capabilities/start/` 开一次实验（`run new` 的能力形态，`cap start <task_dir> [--run-id]`），`contracts.flow` 的桥改认 `start`，流里没写也照旧自动过桥。页面「进度」页（写死五步）换成「工作流」页：现在有几条工作流、几颗能力，从后端读，页面不写死顺序；能力的人话说法在 `ui/web/src/lib/humanize.ts`
- 页面第一版（外层 [#52](https://github.com/zephyr4123/TJU-AI4Science/issues/52)）：`ui/web/` React 19 + Tailwind v4 + shadcn（radix-nova）+ reactbits 两个动效件，Vite 构建成静态文件由 `ai4sci serve` 一并端出（`--ui` 可指定目录，没构建只开接口）；两栏：对话为主（SSE 事件流，助理按的每个按钮翻成人话一行，原始命令与输出点开才看），右边一张看板三个页签，每页是助理写给研究者的一页纸（一句话结论 → 三个大数字 → 几段人话 → 细节折叠 → 键在文末；`lib/humanize.ts` 把状态码、判决、命令翻成句子，有单测）：需求（想解决什么、怎么算好、花多少、**发布键**）、进度（接任务 → 跑基线 → 做实验 → 写分析 → 验证，从真实文件推状态）、结果（比原来好了多少、可信吗、助理的结论、每一轮一句话、**验收键**）。设计口径 `docs/PRODUCT.md` / `docs/DESIGN.md`（impeccable init）。第一版的仪表盘式看板与「摆一串查通不通」按主人意见推翻重做。后端补端点：`GET /tasks[/<id>]`、`POST /tasks/<id>/publish`、`GET /runs[/<id>]`、`POST /runs/<id>/accept`、`GET /flow/check?steps=`，`/chats` 带 `title`（第一句话）、`/chats/<id>` 带 `history`（一轮一条）；`framework/chat/boards.py` 看板读盘、`framework/run/accept.py` 验收记录（`accept.json` 签 best_iter / best_metric / best_commit / 验证结论，内环在跑、只有基线、报告不合约都拒绝，best 变了记录标 stale）与 `ai4sci run accept <id> --by`。`ui/README.md` 写界面层契约：一种界面一个目录、全是同一套端点的客户端，`tui/` 留位置。门禁：`make ui-check`（tsc + oxlint + vitest + 构建）并入 `make check` 与 CI（setup-node 22，依赖只进 `ui/web/node_modules`）。浏览器闭环实测：发布 → `publish.json`、验收 → `accept.json`、流通不通报错、haiku 两轮对话（含 Bash 工具行）
- 协调 agent 服务化第一版（外层 [#51](https://github.com/zephyr4123/TJU-AI4Science/issues/51)）：`backends` 加第二个端口 `Chat`（一句话进、`ChatEvent` 流出：init / text / tool_use / tool_result / denied / done / error，按 session id 续接）与 Claude Code 适配器 `ClaudeCodeChat`（`--resume`、`--append-system-prompt`，隔离位同执行层但保留会话持久化；实测两轮续接记得住）；`framework/chat/`：指南注入（`coordinator/README.md` + 前言，工具只放行 `ai4sci` 与 tasks/ runs/ 的写）、对话落盘 `runs/chats/<id>/`（meta、每轮 message 与原生事件流、transcript、忙锁、半途放弃的轮次留目录不计数）、标准库 HTTP + SSE 服务；`ai4sci chat new|send|list` 与 `ai4sci serve`；环境变量 `AI4SCI_COORDINATOR_MODEL` / `_MAX_TURNS` / `_MAX_BUDGET_USD` / `_TIMEOUT_S`；分层加 `chat` 层（executor 之上、capabilities 之下）
- 发布做成钥匙（外层 [#48](https://github.com/zephyr4123/TJU-AI4Science/issues/48)）：`ai4sci task publish <dir> --by <谁>` 写 `publish.json`（签 manifest.yaml 与 design.md 的 sha256；`contracts/publish.py`），`cap design` / `cap baseline` / `run new` 开门前查它，缺或签的文件改过都退 1 并说怎么办；`design.md` 因此成为任务包必备（`mlp-regression` 补上）。接任务预检 `contracts/headroom.py`（外层 #42 的机器部分）：统计门高度的算式只此一处（内环 `gate` 改调它），manifest 主指标可写 `attainable` 尽头值，基线跑完与 `run new` 都算"基线到尽头有几个门"，门是 0 或不到一个门就停并说清；原来"人看基线决定开不开跑"的停点取消
- 接任务与跑基线升格成能力（外层 [#49](https://github.com/zephyr4123/TJU-AI4Science/issues/49)）：描述符契约加 `level: task`（产物路径相对任务包，入口 `run(task_dir, ports, ...)`，`discover()` 按 level 断言），`capabilities/design/`（`executor/design.py` 的薄壳，参数 `feedback` 可写 `@<文件>`）与 `capabilities/baseline/`（make_run0 + 预检）；`ai4sci cap design|baseline <task_dir>` 从描述符生成，`cap list` 列全五个；领域根可用 `AI4SCI_DOMAINS_ROOT` 覆盖（`packs.default_domains_root`）
- 流通不通检查（外层 [#50](https://github.com/zephyr4123/TJU-AI4Science/issues/50)）：`contracts/flow.py::check_flow` 按描述符对吃吐文件——任务段种子、`run new` 的桥（要 harness/ code/ run_0/）、run 段种子、同一 run 里能力不重复、run 段后不回任务级；`ai4sci flow check <能力>...`（`--json` 给编排看板），不跑
- 裁判文件的契约收紧（外层 #43 #44 #45）：manifest 加可选 `budget.inner_k`（评分内部重复次数，缺省 1）；框架起 harness 时保证给 `AI4SCI_PYTHON` / `AI4SCI_BUDGET_S` / `AI4SCI_INNER_K`（`contracts.env.harness_env`，内环 judge 与新按钮 `ai4sci task baseline` 走同一个函数，后者替代手工 `bash make_run0.sh`）；`task validate` 对 `harness/*.py` 用 ast 抓 `environ.get / getenv` 给保证变量写默认值、对 `launcher.sh` 抓 `${VAR:-x}`，只管这四个变量（`AI4SCI_SEED` 缺省 42 是契约）；分数与 best 完全相同时判决备注改为「持平 delta=0：改动很可能没有生效」并在下一轮提示里点明；设计提示的平台契约段同步；boehm-nll / rahman-nll 的 manifest 登记 inner_k
- 接任务的按钮 `ai4sci task design <dir>`（外层 #41）：读 manifest、协调层写的 `design.md`（产物契约与基线策略）、领域包 skill 正文，起执行层（只放行 `harness/` `code/`）写草稿；回来后框架 `packs.seal_harness`（`*.sh` 加执行位、写 SHA256SUMS）、对 `harness/` 跑 ruff（`--isolated`，规则集与行宽是常数、同时渲染进提示第 7 条）、`validate_task(require_run0=False)`；stdout 一行结论（`next=` 说停点），问题一行一条在 stderr、退 1；`--feedback`（或 `@<文件>`）把问题或人的意见喂回，第二个会话看到现状文件照着改；日志 `runs/design-<id>/executor/session-N/`（提示原文、事件流、stderr）。越界、会话死掉、什么都没写、ruff 不在都是 `DesignFailed`。协调层 README 固定流之二改为「先问三句 → manifest → data/env → design.md → 按钮 → 签字 → make_run0 → validate」，`coordinator/prompts/design-harness.md` 并入 `framework/executor/design_prompt.md`；`tasks/boehm-nll/design.md` 补上作样本
- 任务自带环境（外层 #39，spec R-11）：任务包新增 `env/`（`python-version` + 钉死版本的 `requirements.lock`），`framework/contracts/env.py` 读它、判它、用 uv 建 venv（`uv venv --python X.Y` + `uv pip sync`，uv 进平台 requirements.lock；uv 不在或解释器拉不下来抛 `EnvBuildError`，不退回平台 venv）；`ai4sci task env build <dir>` 建 `tasks/<id>/.venv` 给 `make_run0.sh` 用，`ai4sci run new` 按 `work/env/` 建 `runs/<id>/.venv`（建不出来就删掉半截 run 再报错）；内环提交 harness 时设 `AI4SCI_PYTHON`，`harness/*.sh` 里裸调 `python` / `python3` 由 `task validate` 判不合法；manifest 加必填 `format_version`（只认 `packs.SUPPORTED_FORMAT_VERSIONS`）与可选 `source`（`ai4sci status` 打印）；`mlp-regression` 迁到新契约（run_0 重跑，σ 不变）。A-12 在 CI 里验：夹具 train.py 记下的 `sys.executable` 落在 run 的 `.venv` 下
- 领域包 skill 走 prompt 注入（外层 #39，spec R-12，Q-2 翻案）：`run new` 把领域包的 `prompts/experiment.md` 与全部 `skills/*/SKILL.md` 快照进 `runs/<id>/prompts/`，`run.context.read_domain_extra` 拼成「领域约定」段（skill 去掉 frontmatter），实验与分析两个能力的提示都追加；第一个真领域包 `domains/petab/`（profile、实验追加段、`skills/petab/SKILL.md` 全部 API 在 pypesto 0.7.0 / petab 0.9.0 / libroadrunner 2.10.0 上实测）
- `docs/add-a-task.md`「十分钟接一个任务」：目录、manifest、env、harness 三条硬规矩、三条命令、常见报错对照
- 能力描述符与通用驱动（外层 #35，纲领 P-12）：`framework/contracts/capability.py` 定义 `Capability`（name / level / inputs / outputs / params / needs_executor / needs_compute / criteria）、`Ports`、`CapabilityFailed`；每个能力子包导出 `DESCRIPTOR` 与统一入口 `run(run_dir, ports, **params) -> str`，`capabilities.discover()` 用 pkgutil 扫子包并断言入口签名与描述符一致（没有注册表）；`ai4sci cap list [--json]` 列描述符，`ai4sci cap <name> <run_id>` 的子命令从描述符生成（`--backend` / `--compute` 只在需要时出现，每个 Param 一个选项），失败退 1、用法错退 2；`ai4sci status` 加 `analysis` / `verify` 两行；重跑一个能力把旧目录改名 `<name>_v{n}` 留档；执行层会话泛化为 `executor.session.run_session`，实验内环成为它的薄封装
- 分析能力 `ai4sci cap analysis`（外层 #36，spec R-5）：一次执行层调用，输入 manifest、账本全部行、实验笔记、基线到 best 的 diff（截 20000 字符）、每个 run 的 results.json 指标清单；只许写 `analysis/`，越界 / 会话死掉 / 没写出 / 形状不合约一律 `CapabilityFailed`，文件留着当证据；产物 `analysis/analysis.md` 三节固定（结论 / 数据 / 证伪与未决），数据表 `| run | 指标 | 值 |` 是数字回溯的锚，契约在 `contracts/analysis.py`（整数与百分比不查，行内代码与代码块不查，是写进纲领的 0.2.0 边界）。真跑：sonnet 对 live-20 的 21 轮出 19 行数据表，$0.28、155 s
- 验证能力 `ai4sci cap verify`（外层 #37，spec R-6，A-10）：零模型四项检查——分析存在、数据表每行回溯到那个 run 的 results.json（1% 相对容差，`--tolerance` 可调）、正文里带小数点或指数的数都在数据表里、账本 × git 对账（复用 `memory.ledger.reconcile`）；报告 `verify/report.json` 过 `contracts/schemas/report.schema.json`，PASS 与 FAIL 都写，FAIL 再退 1。CI 里构造编造数字的分析必 FAIL；真跑 live-20 PASS（19 个值、正文 21 个小数全部回溯）
- 协调层入口指南 `coordinator/README.md`（外层 #38，spec R-10）：auto-research 固定流四条命令、每步看什么、什么时候找人、不要连跑
- 执行层适配器 `backends/`（R-1，外层 #20）：`Runner` 端口与 `RunResult`；Claude Code 适配器走 `claude -p --output-format stream-json`，隔离位 `--setting-sources "" --strict-mcp-config --disable-slash-commands`（不加载本机 CLAUDE.md / skill / MCP / plugin / hook，一句 pong 从 $0.46 降到 $0.05），权限 `dontAsk` + `allowedTools` 白名单且绝对路径规则用 `//`，超时 `kill_tree` 逐进程组杀（CLI 的 Bash 子进程自成进程组，只 killpg 自己会留孤儿），`changed_files` 用调用前后 sha256 快照 diff 不采信 CLI 自报，超时拿不到 result 事件时成本填 NaN 不填 0，事件流与 stderr 落盘 `.ai4sci/`。真 CLI 冒烟测试 `AI4SCI_LIVE=1` 才跑
- 任务包契约与 CLI（R-2，外层 #21）：`framework/schemas/manifest.schema.json` 与 `results.schema.json`（没有读取点的字段不进 schema，本轮 `conditions` 未进）；`framework/packs.py` 扫目录发现任务包、逐条校验（schema、id 等于目录名、恰好一个 primary、domain 存在、harness 三件套与 SHA256SUMS 对账、run_0 基线与 repeat_k 次重复与 σ、elapsed 不超预算 1.5 倍）；`ai4sci task validate <dir>` 与 `task list`，退出码 0 / 1 / 2
- 算力端口与本地后端 `compute/`（外层 #23）：`Compute` 协议五个动作（put / submit / wait / cancel / get）与 `Job`、`ExitStatus`；`submit` 立刻返回句柄并把它落盘成 `run_N/job.json`，续跑靠它重新接上或收尸；`ExitStatus.exit_code` 用 `None` 表达"已死但退出码未知"（续跑读回的 job 不是本进程的子进程，填 0 就是把未知讲成成功）；local 后端 `Popen(start_new_session=True)` 起独立进程组、stdout/stderr 落 `.job/`，超时逐进程组杀干净（僵尸不算活着——`killpg(pgid, 0)` 会把没被收走的尸体读成还在跑，改用 ps 查非僵尸成员）；名字对不上报错列出可用名字，绝不静默回退
- 实验内环 runner `framework/loop.py`（外层 #24）：一轮走 revert-to-best → 执行层只改 `code/` → 事后快照 diff 判越界 → runner 提交（作者固定 `ai4sci runner`）→ 快照进 `experiment/runs/run_N/` 起独立进程跑 harness → 六类失败确定性分类（`framework/failures.py`，优先级固定：只读被改 → 超时 → 缺依赖 → 崩溃 → 结果缺失 / 不合 schema / harness 自报 status 不是 ok → 指标 NaN，附一句修复提示喂给下一轮）。崩溃只认 stderr 里的 traceback：真任务包的 launcher 是 `set -euo pipefail`、evaluate 拒收产物时按契约 `SystemExit` 加一句话退出，退出码分不出"假成功"和"跑崩了"，退非 0 而没有 traceback 一律先看产物判 no_results（退非 0 但产物齐全的极端情况仍归 crash）→ 过统计门（delta > `max(accept_sigma×σ, budget.min_delta)`）才 keep，否则先 `refs/attempts/iter-N` 留档再 reset 回 best；新增可选 `budget.min_delta`（缺省 0）兜住 σ=0 的退化，σ 与 min_delta 同时为 0 时 fail-closed 不开跑；改动全被任务包 `.gitignore` 挡住时记 noop 并把原因写进账本 → 账本 `experiment/ledger.tsv` 追加一行并与 git 对账（`framework/ledger.py`，keep 行的 parent 必须接上一条 keep 的 commit、首条接基线）→ checkpoint 原子写；停止条件轮数上限 / 连续 patience 轮不改进（新增 `budget.patience`，缺省 5）/ 同类失败连续 3 次判不可修复 / `budget.max_cost_usd` 用尽，任一触发写 `experiment/stop.json`；`--max-iters` 是**本次增量**不是 run 的总额（上限取 `min(manifest.max_iterations, 已跑轮数 + max_iters)`），配额用完只返回 `batch_exhausted` 且不写 stop，再跑一次接着往下；`loop resume` 读 checkpoint + 账本 + git 三方对账，对不上就抛不猜，被杀在半路的那一轮记 `interrupted` 并回到 best；两个结算尾巴上的崩溃窗口（只剩标记没删 / 账本领先 checkpoint 一行）以账本为准补齐，`loop run` 见到 in-flight 标记直接拒跑并指回 `loop resume`，被 Ctrl-C 打断时先杀掉在飞的 harness 再把异常抛上去；提示模板 `framework/prompts/experiment.md`，账本摘要常数大小（最近 5 行）；CLI 加 `ai4sci run new` / `loop run` / `loop resume` / `status`（`status` 末尾跑一次账本 × git 对账，有问题逐条打 stderr 并退 1）
- 执行层会话没走完（被杀 / 超时 / CLI 崩）记为 `executor_failed` 一轮：改动丢弃、回到 best、下一轮带提示、连续三次判不可修复；此前会因拿不到 result 事件把整个内环炸掉（真跑第 10 轮 kill -9 暴露）
- 实验笔记与续命（外层 #28 #26）：`experiment/notebook.md` 一个 run 一本，runner 每轮追加执行层自述（stream-json 最终 result 文本，截 600 字）+ `git diff --stat` + 裁决，下一轮整本进 prompt，执行层收尾按"假设 / 改动 / 预期"三行自述。真跑第 2 轮与第 5 轮做了同一个改动暴露的缺陷：新会话是为了上下文不膨胀，不是为了失忆。`ai4sci run extend <id> --patience / --max-iterations / --max-cost-usd --reason`：改快照里的 budget、清 stop_reason 与 stop.json、journal.md 记一行，协调层给已停的 run 续命不用手改文件
- 玩具任务 `tasks/mlp-regression/`（R-3，外层 #12 #21）：纯 Python 单隐层 MLP 拟合含噪一维函数，单标量 `val_mse` minimize，一次 0.25 s；harness 只吃 predictions.json 算分，预测缺失 / 长度不对 / NaN 一律退非 0 且不写 results.json；`run_0/` 含基线、三个种子的重复与 σ（0.0036，基线 0.0231），`harness/make_run0.sh` 可复现

### 修复
- `ai4sci run extend` 对「不可修复」的停止无效：内环一起来又从账本尾部数到同样三行失败、当场再停。现在续命在 checkpoint 记 `resumed_after_iter`，不可修复的判定只数续命之后的轮次（真跑 rahman-1 执行层连不上模型三次后续不了，外层 #41）
- `pyproject` 的 package-data 漏了 `capabilities/analysis/prompt.md`，打包安装后分析能力找不到模板；顺带登记 `executor/design_prompt.md`

### 变更
- `ai4sci task design` / `ai4sci task baseline` 删除，改为 `ai4sci cap design` / `ai4sci cap baseline`（外层 [#49](https://github.com/zephyr4123/TJU-AI4Science/issues/49)）；协调层 README 固定流之二改为「四问 → manifest → data/env → design.md → 人发布 → cap design → 核对裁判（人不读代码）→ cap baseline（预检）→ validate」
- `framework/` 按概念拆子包（外层 #30），纯搬家不改行为：`cli/`（一个子命令一个模块，`__init__` 装配 parser，`__main__.py` 接住 `python -m framework.cli`）、`contracts/`（`schemas/*.json` + `packs.py` + 从 `failures` 搬出的 `results.py`）、`run/`（`layout` 路径拼接 / `checkpoint` / `context` 只读上下文 / `lifecycle` 建 run 与续命 / `gitwork`）、`memory/`（`ledger` `notebook`）、`executor/`（`prompting` 组模板 + `session` 起会话并留档日志，模板路径改由能力传入）、`capabilities/experiment/`（`loop` 主循环 / `judge` 裁决与结算 / `gate` 统计门 / `failures` 六类分类 / `prompt.md`）。依赖只许自上而下 `cli → capabilities → executor → memory → run → contracts`，端口 `backends/` `compute/` 不许 import framework，能力之间互不 import——这三条由新增的 `tests/test_layering.py` 用 ast 逐条查（含反向 import 的自证用例）；`pyproject` 的 package-data 跟着 schema 与 prompt.md 的新位置改
- 目录按纲领四层重建：`coordinator/ framework/ backends/ compute/ tools/ domains/ tasks/ runs/ tests/`，原 monorepo 占位目录（apps / packages / workers / db / infra）删除
- 定栈 Python：`pyproject.toml`、`.venv` + `requirements.lock`、ruff（含 BLE 裸 except 门禁）+ pytest 接进 `make check`，CI 装 Python 3.14。框架依赖只有 pyyaml 与 jsonschema，数值库是任务包自己的事

## [0.1.0] - 2026-09-08

### 新增
- 生产代码 monorepo 骨架：`apps/web`、`apps/api`、`packages/core`、`workers/`、`db/`、`infra/`、`tests/` 位置约定
- 变更日志与发布流水线：CHANGELOG 机器校验、`make release` 轮转、tag 触发 CI 出包并建 GitHub Release
- `make check` 门禁入口（lint / test 为占位，定栈后接入）

[Unreleased]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.5.1...HEAD
[1.5.1]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/releases/tag/v0.1.0
