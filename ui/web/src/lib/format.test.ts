import { describe, expect, it } from 'vitest'

import { bytes, day } from './format'

describe('只到天的日期', () => {
  const today = new Date('2026-09-22T10:00:00+08:00')
  it('同一年只写月日，跨年带年，坏值原样', () => {
    expect(day('2026-09-21T04:25:29+00:00', today)).toBe('9月21日')
    expect(day('2025-06-01T04:00:00+00:00', today)).toBe('2025年6月1日')
    expect(day('nope', today)).toBe('nope')
    expect(day(null, today)).toBe('—')
  })
})

describe('大小', () => {
  it('B、KB、MB、GB 各一档，一位小数（GB 是依赖缓存，外层 #263）', () => {
    expect(bytes(512)).toBe('512 B')
    expect(bytes(1536)).toBe('1.5 KB')
    expect(bytes(5 * 1024 ** 2)).toBe('5.0 MB')
    expect(bytes(2.25 * 1024 ** 3)).toBe('2.3 GB')
  })
})
