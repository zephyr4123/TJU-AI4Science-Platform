import { describe, expect, it } from 'vitest'

import type { SpendCell } from '@/api/types'

import { buckets, hitRate, money, perMillion, sorted, tokens, valueOf } from './usage'

const cell = (over: Partial<SpendCell> = {}): SpendCell => ({ cost_usd: null, unknown: 0, tokens: 0, input_tokens: 0, cached_tokens: 0, count: 0, ...over })
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
  it('按成本看时算不出的是 null，不当 0；按 token 看都有数', () => {
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
  it('并成一周时成本、未知、token、次数各自加', () => {
    const week = buckets([
      { day: '2026-07-01', ...cell({ cost_usd: 1.25, unknown: 1, tokens: 10, input_tokens: 8, cached_tokens: 6, count: 2 }) },
      ...days(40).map((d) => ({ ...d, tokens: 0, count: 0 })),
    ])[0]
    expect(week).toMatchObject({ cost_usd: 1.25, unknown: 1, tokens: 10, input_tokens: 8, cached_tokens: 6, count: 2 })
  })
  it('表按这种看法从多到少排；按成本看时算不出的垫底，再按 token', () => {
    const rows = [
      { key: 'a', ...cell({ cost_usd: 5, tokens: 1 }) },
      { key: 'b', ...cell({ cost_usd: 3, tokens: 9 }) },
      { key: 'c', ...cell({ cost_usd: null, unknown: 2, tokens: 5 }) },
      { key: 'd', ...cell({ cost_usd: 1, tokens: 2 }) },
    ]
    expect(sorted(rows, 'usd').map((r) => r.key)).toEqual(['a', 'b', 'd', 'c'])
    expect(sorted(rows, 'tokens').map((r) => r.key)).toEqual(['b', 'c', 'd', 'a'])
  })
  it('成本两位小数，不到一分写「<$0.01」；缓存命中率是命中的占读进去的，没读过是 null', () => {
    expect(money(92.7086)).toBe('$92.71')
    expect(money(0.004)).toBe('<$0.01')
    expect(money(0)).toBe('$0.00')
    expect(hitRate(cell({ input_tokens: 200, cached_tokens: 180 }))).toBeCloseTo(0.9)
    expect(hitRate(cell())).toBeNull()
  })
  it('定价至少两位小数，细到三位的照写', () => {
    expect(perMillion(2)).toBe('$2.00')
    expect(perMillion(0.1)).toBe('$0.10')
    expect(perMillion(0.125)).toBe('$0.125')
  })
})
