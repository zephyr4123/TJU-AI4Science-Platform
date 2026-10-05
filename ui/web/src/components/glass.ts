// 玻璃材质（外层 #242 #249）：卡片色压到六成、背后糊 28px 提饱和 1.8、一圈亮边 `--glass-rim`（深浅两套在 index.css）。
// 顶上那道高光 `--glass-shine` 与投影写在各自的 shadow 里——Tailwind 的 ring 与 shadow 同走 box-shadow，拆不开。
// 产出悬浮窗（GlassDialog）与首页的项目清单两处用。
export const GLASS = 'bg-[color-mix(in_oklab,var(--card)_62%,transparent)] ring-1 ring-[var(--glass-rim)] backdrop-blur-[28px] backdrop-saturate-[1.8]'
