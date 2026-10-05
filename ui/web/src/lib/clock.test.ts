import { describe, expect, it } from 'vitest'

import { elapsed } from './clock'

describe('elapsed', () => {
  const t0 = '2026-10-05T05:23:54+00:00'
  it('一小时以内分:秒，过了时:分:秒，倒着的算 0', () => {
    expect(elapsed(t0, '2026-10-05T05:24:36+00:00')).toBe('0:42')
    expect(elapsed(t0, '2026-10-05T05:33:54+00:00')).toBe('10:00')
    expect(elapsed(t0, '2026-10-05T06:26:00+00:00')).toBe('1:02:06')
    expect(elapsed(t0, '2026-10-05T05:20:00+00:00')).toBe('0:00')
  })
})
