import { describe, expect, it } from 'vitest'

import type { SpendCell } from '@/api/types'

import { buckets, ranked, tokens, valueOf } from './usage'

const cell = (over: Partial<SpendCell> = {}): SpendCell => ({ cost_usd: null, unknown: 0, tokens: 0, count: 0, ...over })
const days = (n: number, end = '2026-10-06') => Array.from({ length: n }, (_, i) => {
  const d = new Date(`${end}T00:00:00`)
  d.setDate(d.getDate() - (n - 1 - i))
  const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return { day, ...cell({ cost_usd: 0, tokens: i, count: i % 3 === 0 ? 1 : 0 }) }
})

describe('首页的花费', () => {
  it('token 用万与亿说，不到一万照写', () => {
    expect(tokens(8421)).toBe('8,421')
    expect(tokens(43_069_109)).toBe('4,307 万')
    expect(tokens(145_219_768)).toBe('1.45 亿')
    expect(tokens(0)).toBe('0')
  })
  it('按美元看时报不出的是 null，不当 0；按 token 看都有数', () => {
    expect(valueOf(cell({ cost_usd: null, unknown: 3, tokens: 9 }), 'usd')).toBeNull()
    expect(valueOf(cell({ cost_usd: 1.5 }), 'usd')).toBe(1.5)
    expect(valueOf(cell({ cost_usd: null, tokens: 9 }), 'tokens')).toBe(9)
  })
  it('一个月内一天一根；九十天按周并，最后一根到今天为止', () => {
    expect(buckets(days(30)).map((b) => b.label).slice(-2)).toEqual(['10/5', '10/6'])
    const weeks = buckets(days(90))
    expect(weeks).toHaveLength(13)
    expect(weeks.at(-1)!.label).toBe('9/30 – 10/6')
    expect(weeks.at(-1)!.tokens).toBe(83 + 84 + 85 + 86 + 87 + 88 + 89)
    expect(weeks[0].label).toBe('7/9 – 7/14') // 头一周不满七天：从第一天起
  })
  it('并成一周时美元、未知、token、次数各自加', () => {
    const week = buckets([
      { day: '2026-07-01', ...cell({ cost_usd: 1.25, unknown: 1, tokens: 10, count: 2 }) },
      ...days(40).map((d) => ({ ...d, tokens: 0, count: 0 })),
    ])[0]
    expect(week).toMatchObject({ cost_usd: 1.25, unknown: 1, tokens: 10, count: 2 })
  })
  it('排行露前几名，其余并成一行；按 token 看重新排', () => {
    const rows = [
      { key: 'a', ...cell({ cost_usd: 5, tokens: 1 }) },
      { key: 'b', ...cell({ cost_usd: 3, tokens: 9 }) },
      { key: 'c', ...cell({ cost_usd: null, unknown: 2, tokens: 5 }) },
      { key: 'd', ...cell({ cost_usd: 1, tokens: 2 }) },
    ]
    const usd = ranked(rows, 'usd', 2)
    expect(usd.top.map((r) => r.key)).toEqual(['a', 'b'])
    expect(usd.rest).toMatchObject({ rows: 2, cost_usd: 1, unknown: 2, tokens: 7 })
    const byTokens = ranked(rows, 'tokens', 3)
    expect(byTokens.top.map((r) => r.key)).toEqual(['b', 'c', 'd'])
    expect(byTokens.rest).toMatchObject({ rows: 1, tokens: 1 })
    expect(ranked(rows, 'usd', 9).rest).toBeNull()
  })
})
