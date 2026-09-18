# Design

视觉系统（2026-09-17 第三版，外层 [#64](https://github.com/zephyr4123/TJU-AI4Science/issues/64)）。第一版仪表盘被否，第二版一页纸白底琥珀，这一版给页面一个性格：实验记录本。

## Scene

给不写代码的研究者用的科研工作台。页面头号任务一句话：现在做到哪一步、在等谁、数字可不可信。世界观来自实验记录本和裁判——账本、基线、统计门、验证、两颗人按的键。视觉从这儿长，不从 SaaS 模板长。

## Color strategy

五个颜色都是信息，不是装饰。一眼分得出三种状态：助理在跑（靛）、等你（琥珀）、可信（铜绿）。

| Token | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--background` 纸 | `#F5F6F8` | `#171A20` | 工作面，冷白不是奶油色 |
| `--foreground` 墨 | `#1C2230` | `#E6E8EE` | 正文与标题，蓝黑墨水 |
| `--primary` 靛 | `#2F4BC9` | `#8FA3F5` | 助理在动、可点的东西、流程线、发送键 |
| `--ok` 铜绿 | `#1F7A6D` | `#5FC2B0` | 只给「验证通过、可信」 |
| `--wait` 琥珀 | `#B8741A` | `#E2A751` | 只给「等你按键」：两颗键、等人的那一步 |
| `--muted-foreground` | `#5B6270` | `#9AA1AE` | 次要文字（对纸面 ≥ 4.5:1） |
| `--card` | `#FFFFFF` | `#1E222A` | 顶栏、脊柱上填实的模块、输入框 |
| `--grid` | `#E1E4EA` | `#242932` | 脊柱那一列的方格纸 |

深色跟系统偏好，`data-theme` 可强制。`--bad` 只给出错，配文字与图标一起出现，不单靠颜色。

## Typography

两族，分工清楚：

- **思源宋体（Noto Serif SC Variable）**：只给助理那句结论（`.t-lede`）、脊柱上每一步的标题（`.t-step`）、Markdown 里的标题、顶栏名字。期刊味，和实验记录本对味。
- **IBM Plex Sans Variable + 系统中文**：正文、界面、数字（全局 `tabular-nums`）。命令与文件名用 IBM Plex Mono，因为它们真是命令。

| 角色 | 尺寸 / 行高 / 字重 |
|---|---|
| 一句话结论 `.t-lede` | 1.25rem / 1.45 / 600 宋体 |
| 步骤标题 `.t-step` | 1rem / 1.4 / 600 宋体 |
| 大数字 `.t-big` | 1.75rem / 1 / 500，等宽数字 |
| 正文 `.t-body` | 0.9375rem / 1.65 / 400，行长 ≤ 68ch |
| 标签 `.t-label` | 0.8125rem / 1.4，`--muted-foreground` |

不做的：全大写小标签、中点串元信息（写成一句话）、给标题里某个词单独上色。

## Layout

顶栏一条（左端一枚玻璃标记 + 名字、带封面小图的工作区切换、主页面 / 编辑台胶囊；底下铺当前工作区的封面糊成一抹颜色，换工作区顶栏就换色，编辑台铺库的横幅，门口那一屏是纸），下面两块看板以可写目录划界（[#58](https://github.com/zephyr4123/TJU-AI4Science/issues/58)）；页面先认工作区（[#70](https://github.com/zephyr4123/TJU-AI4Science/issues/70)）：

- **主页面**（改实例）：没有工作区时是「新建工作区」那一屏（起名 + 一句标题，底下铺一段循环视频：浅色云雾、深色光线汇聚，纱幕压到字能读）；有了工作区还没对话是欢迎屏（一张配图铺在整列底下，玻璃输入框浮在上面，打字回车就开一段）；有了对话就是这个工作区的对话（左，内容列 ≤ 44rem）与右边 **流程脊柱**——当前 run 照的那条流，一步一个模块，编号是真序列，每一步左侧一枚阶段图标（能力按阶段，发布键盖章、验收键签名，人开口、助理提笔）；模块的实心程度来自盘上真实的文件（没产出虚线框，产出了实心，作业在跑有微光边，等你按键用琥珀）。没有 run 时脊柱就是需求对齐（起任务包 → 填需求 → 发布 → 接任务 → 核对 → 跑基线）。两颗键在脊柱末尾。这一列铺极淡的方格纸（`.paper-grid`）。全页放胆的只有两处画面：门口那一屏的视频、欢迎屏的配图，一有内容画面就让位。
- **对话抽屉**：顶上是这个工作区的封面（编辑台是库的横幅），字站在脚下压成纸色的那一段；清单逐条浮现，当前那段的气泡图标填实。
- **编辑台**（改库）：左边造流助理的对话（窄一列，库才是主角），右边顶上一条库的横幅（白架子上的玻璃器皿），下面工作流墙（一流一卡：名字、覆盖的几段各一枚图标、一句话、几步），下面七段能力货架（空的留空位）+ 拼流台（点能力进来，通不通当场说，存成文件）。

对齐：全部左对齐；数字右对齐成列。

## Components

shadcn（radix-nova 预设）作基础件。reactbits 只用在承担信息的地方，从 registry 捞来改装、走 tokens：PillNav（顶栏胶囊，去掉 logo 与路由）、ElectricBorder（正在跑的那一步）、CountUp（结果三个大数字）、SpotlightCard（工作流墙）、SpecularButton / StarBorder（发布、验收两颗键，全页只有它们有这种质感）、ShinyText（作业跑着时的状态字）、GlassSurface（输入框的壳，跟 `data-theme`）、RotatingText（输入框里轮换的提示语）、Folder（新建工作区那只文件夹）、GlassIcon（顶栏那枚标记，GlassIcons 只留一枚）、AnimatedList（工作区清单与对话清单逐条浮现）。`components/Band` 是自家的：一张图 + 一层纱幕，顶栏（wash，糊成颜色）、抽屉与库（foot，脚下压纸色）都用它。图标 Phosphor（regular；看板开着那颗用 fill），全站一套，`components.json` 的 `iconLibrary` 也是它，shadcn 再生成的件不会带回 lucide。

## Motion

只回应动作：模块填上、作业跑完、键按下、助理逐字说话（流式）。150–250ms，ease-out。无页面加载编排，不给每张卡加 hover 阴影。`prefers-reduced-motion` 下全部退化为直接出现：CSS 动画归零，JS 驱动的（逐字浮现、电光边、闪字、火花、胶囊鼓圆、提示语轮换）在组件里按 `useReducedMotion` 换成静态。视频背景只在门口那一屏：循环无缝、无声、`playsInline`，首帧就是海报所以起播不跳；减少动效或省流量（`saveData`）不拉视频只给海报，加载失败也停在海报。

## 窄屏

64rem 以下：脊柱收进右侧抽屉（顶栏那颗键拉出来），编辑台改成上对话下库，顶栏只留切换胶囊与两个页签。文件夹那一屏只剩填空句子，视频照铺。

## 素材

除了图标用 SVG 内联，图片与视频一律走自己 CDN 的 URL，仓里不放二进制（纲领 P-17，外层 [#75](https://github.com/zephyr4123/TJU-AI4Science/issues/75)）。URL 只写在 `ui/web/src/assets.ts`；`make ui-check` 查 `git ls-files ui/` 里没有 png / jpg / mp4。

CDN：`https://media.zephyrxiang.com/ai4science/v1/`（腾讯云 COS + CDN，`Cache-Control: immutable`，内容变了换文件名不复用；referer 白名单含 localhost）。来源站的文件先下到本机、处理好、再推桶——境外源站当背景加载不出来等于没有。

| 用途 | 文件 | 来源 | 作者 | 许可 | 处理 |
|---|---|---|---|---|---|
| 门口背景（浅色） | `video/door-light.mp4`、`image/door-light.jpg` | motionsites「Vectrus Energy」的背景片 | motionsites（AI 生成） | 站上没有许可条款页，prompt 原文要求原样引用其 URL；镜像是主人（终身会员）的决定 | 取前 6.5 秒，末尾 1 秒淡回开头，5.5 秒无缝循环；H.264 CRF 24、无音轨、faststart；首帧出海报 |
| 门口背景（深色） | `video/door-dark.mp4`、`image/door-dark.jpg` | motionsites「Neural Pathway」的背景片 | 同上 | 同上 | 末尾 0.7 秒淡回开头，9.4 秒循环；其余同上 |
| 欢迎屏配图 | `image/welcome-2400.jpg`、`image/welcome-1200.jpg` | Pexels 7722915 | Tara Winstead | Pexels 许可：可免费商用、不强制署名 | 缩到 2400 / 1200 宽，JPEG |
| 工作区封面（六张，按名字稳定地挑） | `image/cover-<key>-800.jpg`、`-240.jpg` | microscope：Pexels 18952655；petri：10188003；crystal：11434879；chalk：22690751；flask：7722958；notebook：159746 | indra projects；Ron Lach；Alina Vilchenko；Vitaly Gariev；Tara Winstead；Pixabay | 同上 | 居中裁成 8:5，800 与 240 宽 |
| 库的横幅（编辑台、造流助理抽屉） | `image/studio-2000.jpg`、`-1000.jpg` | Pexels 3735704 | Polina Tankilevitch | 同上 | 竖图取中段裁成 20:7 |

再加素材照这张表补一行。找素材用 stock-images / iconify / motionsites 这几个 MCP，别让模型手绘。
