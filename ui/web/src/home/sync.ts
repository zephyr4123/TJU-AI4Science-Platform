// 首页的同步（外层 #256，主人 2026-10-06 照 cc-switch 用量页要的）：上次同步说成多久以前、自动刷新隔多久。

/** 自动刷新的间隔（秒）；0 是不自动 */
export const EVERY = [0, 10, 30, 60, 300] as const
export type Every = (typeof EVERY)[number]

/** 上次同步：一分钟内「刚刚」，一小时内「N 分钟前」，再久写钟点；还没同步过是「同步中」 */
export function syncedLabel(at: number | null, now: number): string {
  if (at === null) return '同步中'
  const minutes = Math.floor((now - at) / 60_000)
  if (minutes < 1) return '刚刚同步'
  if (minutes < 60) return `${minutes} 分钟前同步`
  const t = new Date(at)
  return `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')} 同步`
}

/** 键上写的：「自动刷新 30 秒」 */
export function everyLabel(every: Every): string {
  return every === 0 ? '不自动刷新' : `自动刷新 ${span(every)}`
}

/** 菜单里一项：「每 30 秒」 */
export function everyOption(every: Every): string {
  return every === 0 ? '不自动刷新' : `每 ${span(every)}`
}

function span(seconds: number): string {
  return seconds < 60 ? `${seconds} 秒` : `${seconds / 60} 分钟`
}
