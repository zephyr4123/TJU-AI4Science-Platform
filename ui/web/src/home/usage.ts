// 首页右栏「花费」的纯函数（外层 #256）：两种看法（折算成本 / token）各取哪个数、按天还是按周画柱、表怎么排、
// 钱、token、缓存命中率与定价怎么念。成本算不出（模型没记）是 null，不当 0：按成本看时那一格不画、写「未知」。

import type { SpendCell } from '@/api/types'

export type Metric = 'usd' | 'tokens'

/** 右栏能看的时间范围（天） */
export const RANGES = [7, 30, 90] as const
export type Range = (typeof RANGES)[number]

/** 一格按这种看法的数：按成本看，一次都没算出是 null */
export function valueOf(cell: SpendCell, metric: Metric): number | null {
  return metric === 'usd' ? cell.cost_usd : cell.tokens
}

/** token 用中文的万与亿念：8,421 / 4,307 万 / 1.45 亿 */
export function tokens(n: number): string {
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`
  if (n >= 1e4) return `${Math.round(n / 1e4).toLocaleString('zh-CN')} 万`
  return n.toLocaleString('zh-CN')
}

/** 定价（每百万 token）：至少两位小数，细到三位的照写（$0.125） */
export function perMillion(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 3 })}`
}

/** 缓存命中率：读进去的里头命中缓存的占几成；一个 token 都没读过是 null */
export function hitRate(cell: SpendCell): number | null {
  return cell.input_tokens > 0 ? cell.cached_tokens / cell.input_tokens : null
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

/** 表的次序：按这种看法从多到少（按成本看时算不出的垫底），一样再按 token */
export function sorted<T extends SpendCell>(rows: T[], metric: Metric): T[] {
  return [...rows].sort((a, b) => {
    const x = valueOf(a, metric)
    const y = valueOf(b, metric)
    if (x === null || y === null) return x === y ? b.tokens - a.tokens : x === null ? 1 : -1
    return y - x || b.tokens - a.tokens
  })
}

/** 几格加起来：成本只加算得出的（一格都没算出是 null），未知、token、次数照加 */
function sum(cells: SpendCell[]): SpendCell {
  const known = cells.filter((c) => c.cost_usd !== null)
  const add = (pick: (c: SpendCell) => number) => cells.reduce((s, c) => s + pick(c), 0)
  return {
    cost_usd: known.length ? known.reduce((s, c) => s + (c.cost_usd ?? 0), 0) : null,
    unknown: add((c) => c.unknown),
    tokens: add((c) => c.tokens),
    input_tokens: add((c) => c.input_tokens),
    cached_tokens: add((c) => c.cached_tokens),
    count: add((c) => c.count),
  }
}

/** 2026-10-06 → 10/6 */
function short(day: string): string {
  const [, m, d] = day.split('-')
  return `${Number(m)}/${Number(d)}`
}
