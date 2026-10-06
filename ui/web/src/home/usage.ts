// 首页右栏「花费」的纯函数（外层 #256）：两种看法（折算美元 / token）各取哪个数、按天还是按周画柱、排行露几名、
// token 怎么念。美元报不出（Codex 订阅）是 null，不当 0：按美元看时那一格不画、写「未报」。

import type { SpendCell } from '@/api/types'

export type Metric = 'usd' | 'tokens'

/** 右栏能看的时间范围（天） */
export const RANGES = [7, 30, 90] as const
export type Range = (typeof RANGES)[number]

/** 一格按这种看法的数：按美元看，一次都没报过是 null */
export function valueOf(cell: SpendCell, metric: Metric): number | null {
  return metric === 'usd' ? cell.cost_usd : cell.tokens
}

/** token 用中文的万与亿念：8,421 / 4,307 万 / 1.45 亿 */
export function tokens(n: number): string {
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`
  if (n >= 1e4) return `${Math.round(n / 1e4).toLocaleString('zh-CN')} 万`
  return n.toLocaleString('zh-CN')
}

export interface Bucket extends SpendCell { label: string }

/** 柱子：一个月以内一天一根（「10/6」）；更长按周并，从今天往回七天一根，头一根不满七天就从第一天起（「9/30 – 10/6」） */
export function buckets(days: (SpendCell & { day: string })[]): Bucket[] {
  if (days.length <= 31) return days.map((d) => ({ ...d, label: short(d.day) }))
  const out: Bucket[] = []
  for (let end = days.length; end > 0; end -= 7) {
    const week = days.slice(Math.max(0, end - 7), end)
    out.unshift({ ...sum(week), label: `${short(week[0].day)} – ${short(week.at(-1)!.day)}` })
  }
  return out
}

/** 排行：按这种看法从多到少（按美元看时没报过的垫底、再按 token），露前 `n` 个，其余并成一行（`rows` 是并了几个） */
export function ranked<T extends SpendCell>(rows: T[], metric: Metric, n: number): { top: T[]; rest: (SpendCell & { rows: number }) | null } {
  const sorted = [...rows].sort((a, b) => {
    const x = valueOf(a, metric)
    const y = valueOf(b, metric)
    if (x === null || y === null) return x === y ? b.tokens - a.tokens : x === null ? 1 : -1
    return y - x || b.tokens - a.tokens
  })
  const rest = sorted.slice(n)
  return { top: sorted.slice(0, n), rest: rest.length ? { ...sum(rest), rows: rest.length } : null }
}

/** 几格加起来：美元只加报了的（一格都没报过是 null），未知、token、次数照加 */
function sum(cells: SpendCell[]): SpendCell {
  const known = cells.filter((c) => c.cost_usd !== null)
  return {
    cost_usd: known.length ? known.reduce((s, c) => s + (c.cost_usd ?? 0), 0) : null,
    unknown: cells.reduce((s, c) => s + c.unknown, 0),
    tokens: cells.reduce((s, c) => s + c.tokens, 0),
    count: cells.reduce((s, c) => s + c.count, 0),
  }
}

/** 2026-10-06 → 10/6 */
function short(day: string): string {
  const [, m, d] = day.split('-')
  return `${Number(m)}/${Number(d)}`
}
