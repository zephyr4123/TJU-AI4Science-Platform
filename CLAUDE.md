# TJU AI for Science · platform（生产代码仓）

给 agent 与人的约定。读完这份就知道这个仓有哪些规矩、动手前该先读哪份文档。规矩分四层：**协作方式**（怎么领活、怎么交活）、**编码标准**（代码写成什么样）、**质量纪律**（怎么证明做对了）、**红线**（能用命令查的硬规则）。细则按模块放在各自目录的 README 里，这里只放纲领与入口。

## 0. 这是什么、在哪

- 科研全自动化平台的生产代码，Python 包 `ai4sci`（入口 `framework.cli:main`），页面在 `ui/web/`。四层：协调层（人 + 助理）做科研判断，框架是零模型的诚实执行基底，执行层 coding agent 是唯一写代码的，skill 脚本是确定性工具。
- 本仓是**内仓**：外层协作仓 [`tju-ai4science`](https://github.com/zephyr4123/TJU-AI4Science) 把它 clone 到 `platform/`，外层对它的 git 不知情。产品纲领（P-1 到 P-25）、流程细则、未决问题、案例卡都在外层 `docs/`；issue 也开在外层。只 clone 了本仓的人先去外层读 `docs/architecture/README.md`。
- 两种跑法：源码（clone + `make up`）出厂件在仓根、数据根缺省仓根；包（`uv tool install` wheel）出厂件在 `framework/shipped/`、数据根 `~/ai4sci`。分辨只在 `framework/paths.py` 一处。

## 1. 开工前先读哪份

| 要做的事 | 先读 |
|---|---|
| 任何改动 | 本文件；`README.md`（代码侧的地图：系统一眼看、文档索引）；外层 `docs/architecture/README.md`（产品边界与 25 条原则） |
| 改后端（`framework/` `backends/` `compute/`） | `framework/README.md`：分层与依赖方向、技术栈、模式与约定、异常与退出码、环境变量 |
| 写或改测试 | `tests/README.md`：怎么写、夹具、live 门控、门禁各跑什么 |
| 改页面（`ui/web/`） | `ui/README.md`：技术栈、约定、测试政策、浏览器闭环；`docs/DESIGN.md` 视觉与布局；`docs/PRODUCT.md` 给谁用 |
| 加一个能力 / skill / 领域包 | `docs/add-a-capability.md` / `docs/add-a-skill.md` / `docs/add-a-domain.md` |
| 在终端里接一个课题 | `docs/start-a-workspace.md` |
| 改助理的行为 | `coordinator/README.md`（研究助理）、`coordinator/studio.md`（流程助理）与 `framework/chat/guide.py` 的前言**是线上 prompt**，改它们等于改助理的行为；`framework/capabilities/*/prompt.md` 是执行层的 prompt |
| 流程 / 能力 / 断点这些概念 | 外层 `docs/architecture/workflow.md`（细则与词表） |

## 2. 协作方式：issue driven、spec coding

- **每个工作单元一条 issue**，开在外层仓 [zephyr4123/TJU-AI4Science](https://github.com/zephyr4123/TJU-AI4Science/issues)。做之前先有 issue，做的过程中发现、证据、决策随做随写进 issue 评论（贴 commit、贴数字、贴 `文件:行`），不攒总结。会话会压缩、聊天记录会丢，issue 和文档才是可靠的上下文。
- **先对齐再动手**：需求、边界、验收标准先写清（issue 正文或外层 `docs/specs/`），照它干活，做完回来改文档。纲领（外层 `docs/architecture/`）改得慢、要双方认可；spec 和 issue 改得快。现实与文档不一致时先改文档再改代码。
- **issue 的写法**：标题一句人话；标签三根轴——`kind:*`（什么类型，可多选）、`area:*`（哪一层）、`P0/P1/P2`；大活开一条 `kind:umbrella` 母 issue 挂 milestone，叶子用 GitHub sub-issue 挂在它下面，不把几十条平铺在 milestone 上；要人拍板的加 `needs-decision`。
- **commit**：feature 分支上做，一个逻辑单元一个 commit，随做随提；message 用中文、技术名词保留英文、说改了什么和为什么、末尾带 `（#n）` 引用 issue。**不加 `Co-Authored-By`、不加「Generated with」尾注、不加机器人 emoji**。
- **合并与推送**：合到 `main`、push 远端、改写历史之前要项目负责人确认，每次都问；分支内随做随提不用问。`./repos` 的 pull 只 ff-only、push 永不 force。
- **交活**：`make check` 绿才提交；改动写进 `CHANGELOG.md` 的 Unreleased；merge+push 之后把这批 commit 引到的 issue 关掉，评论写做了什么、在哪个 commit。做完不关的 issue 等于没做完的 issue。
- 涉及外层与内仓两边的改动，以外层的一条 issue 为锚，两边 commit 都引它；问「某功能改了哪些仓」查 issue 不查 git log。

## 3. 编码标准

心法：**每一行代码都要有存在的理由，可删的代码就是该删的代码**。按高级工程师的水准写，与语言无关。

- **融入现有代码**：跟随仓里的命名、结构、注释风格；判据是新代码混在旧代码里看不出是后加的。
- **三个清晰**：目录清晰——打开仓库能猜到东西在哪；结构清晰——分层明确，依赖只指向一个方向，画依赖图不出现环（`tests/test_layering.py` 查）；模块清晰——单一职责，每个模块能独立理解、独立测试、独立替换，「独立替换」是最严的一条。
- **设计的张力**：善用设计模式解决对口的问题，不为用而用；不过度设计，只为当前需求实现、为可预见的变化留缝。**有真实的第二个用例才抽象，只有一个用例先写死。**
- **涉及 agent 的一律可替换**：起 agent、连算力的地方先定端口（Protocol）再写第一个适配器，框架只 import 端口；框架里不出现某家 CLI 的名字或参数；换一家就是加一个文件、显式字典里加一行。
- **文件即接口**：能力之间的接口是文件名，不是 schema；一个文件只有一个生产者，格式由生产者定；schema 只在产物要给机器读时才补。
- **一个概念一处读取点**：根目录只在 `framework/paths.py`，按人的两份清单只在 `framework/computes.py` / `framework/agents.py`，环境变量各自只读一次、断言一次。
- **可读性优先**：命名讲人话，函数和文件一眼能读完；注释与 docstring 用中文，写「为什么」不复述「做什么」，引用纲领条目 P-n 与 issue 号。
- **错误处理显式**：失败路径要么处理要么向上抛；空值、越界、并发、超时想在前面；未知的值写 NaN 或空，绝不写 0 冒充；配置非法当场断言或抛，不静默回落。
- **为排查留日志**：关键路径写带上下文的结构化日志（`ai4sci.<模块>`，消息是「事件名 键=值」），错误日志能让三个月后的人定位。
- **性能靠测量**：先正确后优化，优化要有数据。
- **依赖**：成熟库优先，精力留给业务独有逻辑；选型四看——维护活跃度、社区规模、许可证、安全记录；锁文件钉版本（`uv.lock`、`package-lock.json`）；能复用现有 skill、脚本、模式的不重新发明。运行时依赖极少（见 `framework/README.md`），加一个要说清为什么标准库不够。
- **重构要彻底**：不光加不删、不打补丁；旧入口（旧命令、旧参数、旧环境变量、没读取点的字段）逐个删干净并同步文档与测试；旧数据用一次性脚本搬（外层 `scripts/oneoff/`）。内测期没有兼容包袱。
- **破坏性变更可回滚**：数据 schema、对外 API 的不兼容变更要有迁移方案与回滚路径。
- **文档随代码同步**：过期的文档比没有更糟；改了行为的地方文档同步改，改了产品说法的回写外层纲领。
- 反模式：为「以后可能」先造三层抽象；另起一套命名结构与旧代码并存；catch 完什么都不做或只打一行没上下文的日志；凭感觉调性能；手写成熟库已解决的东西；改代码不动文档。

交付前自检：风格与仓一致；依赖方向单一无环；新模块可独立测试；失败路径与边界都写了；关键路径有可定位日志；新依赖过了四看且锁了版本；改了行为的文档同步改了；可删的代码删干净了。

## 4. 质量纪律

心法：**代码好不好由测试说明、由门禁说明、由实际数据说明**；作者自己说「应该没问题」等于什么都没说。

- **测试驱动**：改行为先写一条会失败的测试，亲眼看它红，再实现让它绿。没见过红的测试不知道它测没测到东西。文档、配置、单行修复这类低风险改动按爆炸半径从轻。
- **机器能查的不留给人查**：能被脚本判定的规矩进门禁（ruff、tsc、oxlint、vitest、pytest 里的检查器测试），人的注意力留给意图、抽象、边界。一条规矩没法用一条命令查它有没有被违反，它就只是标语。
- **不用 mock 模型**：框架的正确性不由模型的发挥证明；用剧本后端（`tests/fixtures/scripted_backend.py`）把执行层「这一轮干了什么」变成可枚举的输入。真 CLI、真机器的测试用 `AI4SCI_LIVE=1` / `AI4SCI_LIVE_SSH=<名字>` 门控，CI 不跑。
- **审查产出不是事实**：任何 agent 或工具报出的 finding 都是待验证输出，逐条到代码里核实才能采信、才能动手。
- **排查三条**：未取证不下结论（查代码、查 git log、查日志）；假设必须带验证动作并立刻取证，验不了就标「未验证」；证据穷尽仍不确定就带证据与置信度如实说。
- **什么算验过了**：可复现的命令 + 真实输出；计数型硬数字（「535 过 7 跳」）；正 / 负 / 边界样本各多少；引用带 `文件:行` 与 commit；没触发的场景点名说未触发及原因。「已验证」「应该没问题」不是证据。
- **页面改动必须过浏览器**：改了看得见的东西，用 playwright 在真服务上点一遍、截图看一眼再交，证据存在外层仓根 `.playwright-mcp/`（gitignore）。

## 5. 红线（能用命令查的都进了 `make check`）

1. **框架零模型调用**：`framework/` 下 grep 不到 anthropic / openai / claude_sdk（纲领 P-1）。模型只在 `backends/` 适配器起的子进程里。
2. **不吞异常**：ruff 的 BLE 规则开着，裸 `except` 与不 raise 的 `except Exception` 过不了 lint（P-7）。
3. **依赖方向单向**：`framework/` 内 `cli → capabilities → chat → experiment → executor → workspace → skills → contracts`，`backends/` `compute/` 是端口、不许 import framework，能力子包互不 import（`tests/test_layering.py`）。
4. **密钥与敏感配置只进环境变量**，绝不进代码、不进 argv；ssh 只认密钥，清单里没有 password 字段（`framework/computes.py` 断言）。
5. **环境隔离**：平台一律 `.venv`、uv 管一切（`make venv` = `uv sync --locked`，改依赖 `make lock`）；课题的依赖不进平台 venv，每次实验按 `materials/env/` 自建 venv，harness 只经 `$AI4SCI_PYTHON` 起解释器；skill 脚本 PEP 723 自带依赖；页面依赖只进 `ui/web/node_modules`。
6. **每个改动写 `CHANGELOG.md` 的 Unreleased**；发版只走 `make release VERSION=x.y.z`，不手工打 tag（`make changelog`）。
7. **`make check` 是提交前门禁，与 CI 完全相同**：changelog → ruff → skills（校验 + 预热，唯一联网的一步）→ pytest → `ui-check`（素材不进仓 + tsc + oxlint + vitest + 构建）。门禁命令别接 `| tail`，管道会吞退出码。
8. **跨仓变更以外层 issue 为锚**，commit message 引用它。
9. **`.claude/` 是本机会话产物**，已 gitignore；不读取、不依赖。
10. **素材不进仓**（P-17）：图片 / 视频只写 CDN URL，只在 `ui/web/src/assets.ts`；`git ls-files ui/` 里没有二进制（`make ui-check`）；图标全站一套 Phosphor 内联，品牌标是唯一自绘的 SVG。
11. **页面与文案照词表**（P-21）：一个概念一个词，机器的名字（文件名、能力名、产出 id、参数名）不上屏，翻译在源头（描述符的 `title` `brief`、参数的 `label`）；禁用词与 `font-mono` 由 `ui/web/src/copy.test.ts` 与 `framework/contracts/capability.py` 的 `BANNED_WORDS` 守着。文档、指南、文案用直白的工程语言：命令就是 agent 调用的 tool，「人按」就是人确认，不写「按钮」「裁判」「房间」这类比喻，不造量词。

下面三条是**产品运行时的规矩**，约束的是助理与框架的行为，改相关代码时要守：

12. **助理面前只有 `ai4sci`**（P-14）：协调层放行的命令前缀是 `ai4sci`，执行层只有 `ai4sci skill`（`chat/guide.py::BASH_RULES`、`skills.EXECUTOR_BASH_RULES`）；配置归环境变量与按人的两份清单，命令上不带路径、不挂前缀、不接管道（`tests/test_chat_guide.py` 守着）。agent 需要而没有的动作是平台缺口：加能力，不放行裸命令。
13. **造流程与用流程分权**（P-16）：项目里的研究助理只用流程（`flow take` 取实例、改参数、照着走），编辑台的流程助理只写 `workflows/`；分权靠 `chat/scope.py` 的可写目录与按域分前缀的端点，不靠指南里的「请不要」。
14. **框架只管文件夹怎么摆，不管里面装什么**（P-19 / P-20）：框架认的文件只有 `requirement.md` / `requirement.lock` / `meta.yaml` / `signed.json` / 流程文件 / 描述符；族内约定（`scoring.yaml` 这类）放族包 `framework/experiment/`，不进 `contracts/`。需求确认是唯一内置的门，断点几个、放哪由拼流程的人定。能力是纯函数：`--from` 点名输入，没有「缺省读最新」。阶段主文件按阶段定名（`capabilities.MAIN_FILES`），不按能力定。

## 6. 版本与发布

- 从 0.1.0 起步，0.x 不承诺兼容；正式发布才进入 1.0.0。tag 形如 `vX.Y.Z`。
- 推送 tag 触发 `release.yml`：对账 CHANGELOG → `make check` → `make package` → 建 Release 并附 wheel，0.x 自动标 pre-release。
