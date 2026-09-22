import { describe, expect, it } from 'vitest'

import { day } from './format'

describe('只到天的日期', () => {
  const today = new Date('2026-09-22T10:00:00+08:00')
  it('同一年只写月日，跨年带年，坏值原样', () => {
    expect(day('2026-09-21T04:25:29+00:00', today)).toBe('9月21日')
    expect(day('2025-06-01T04:00:00+00:00', today)).toBe('2025年6月1日')
    expect(day('nope', today)).toBe('nope')
    expect(day(null, today)).toBe('—')
  })
})
