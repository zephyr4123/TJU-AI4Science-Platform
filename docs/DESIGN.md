# Design

视觉系统的种子（pre-implementation seed，随第二版页面一起定；实现落地后用 `/impeccable document` 回扫）。

## Scene

白天的实验室办公室，笔记本屏幕，日光灯或窗光，读者是要在三十秒内判断"能不能用"的研究者。浅色。

## Color strategy

Restrained：纯白工作面 + 一个琥珀主色（≤ 10% 面积，只给两颗键、当前选中、关键数字的正向变化）+ 偏冷的灰做侧栏与分隔。暖意由主色与字重带，不进底色。

| Token | OKLCH | 用途 |
|---|---|---|
| `--background` | 1 0 0 | 工作面 |
| `--foreground` | 0.17 0.01 80 | 正文 |
| `--muted-foreground` | 0.45 0.01 260 | 次要文字（对白底 ≥ 4.5:1） |
| `--primary` | 0.55 0.13 72 | 两颗键、选中、正向数字 |
| `--accent` | 0.955 0.03 80 | 键所在区块的底色 |
| `--sidebar` | 0.975 0.004 250 | 对话列表、看板底 |
| `--ok` / `--warn` / `--bad` | 0.5 0.13 150 / 0.6 0.13 70 / 0.55 0.2 27 | 状态语义，配文字与图标一起出现 |

## Typography

一族：Geist Variable（拉丁与数字）+ 系统中文（PingFang SC / Noto Sans SC）回退。产品界面不做显示字体。固定 rem 阶梯，比例 1.2：

| 角色 | 尺寸 / 行高 / 字重 |
|---|---|
| 一句话结论 | 1.375rem / 1.35 / 600，`text-wrap: balance` |
| 三个大数字 | 2.25rem / 1 / 600，等宽数字（`tabular-nums`） |
| 正文 | 0.9375rem / 1.6 / 400，行长 ≤ 68ch |
| 标签、元信息 | 0.8125rem / 1.4 / 400，颜色 `--muted-foreground` |
| 等宽（命令、文件名，只在展开层） | 0.8125rem，`--font-mono` |

## Layout

两栏：对话（主，占剩余宽度，内容列 ≤ 44rem 居中）+ 看板（右，30rem，白底带左分隔线）。对话列表收成左侧抽屉。看板顶部三个页签：需求 / 进度 / 结果。看板内部是单列文档流：结论 → 数字 → 段落 → 细节折叠 → 键。间距节奏：段落间 1.5rem，节间 2.5rem，键前 2rem。不用卡片套卡片；分组靠间距与一条 1px 分隔线。

## Components

shadcn（radix-nova 预设）作基础件；reactbits 只用在承担信息的地方：阶段进度 Stepper、大数字 CountUp、逐轮列表 AnimatedList、欢迎屏一个安静的背景。图标 lucide，单一图标集。

## Motion

150–250ms，ease-out；只表达状态变化（键按下、数字到位、列表逐条进入、流式回复）。无页面加载编排。`prefers-reduced-motion` 下全部退化为直接出现。
