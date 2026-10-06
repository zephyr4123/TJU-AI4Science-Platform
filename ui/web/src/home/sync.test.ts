import { describe, expect, it } from 'vitest'

import { everyLabel, everyOption, syncedLabel } from './sync'

describe('首页的同步', () => {
  const at = new Date(2026, 9, 6, 14, 5).getTime()
  it('上次同步说成多久以前：一分钟内是刚刚，一小时内是几分钟前，再久写钟点；还没同步过是同步中', () => {
    expect(syncedLabel(null, at)).toBe('同步中')
    expect(syncedLabel(at, at + 59_000)).toBe('刚刚同步')
    expect(syncedLabel(at, at + 3 * 60_000)).toBe('3 分钟前同步')
    expect(syncedLabel(at, at + 61 * 60_000)).toBe('14:05 同步')
  })
  it('自动刷新的间隔：0 是不自动，秒与分钟各照说', () => {
    expect(everyLabel(0)).toBe('不自动刷新')
    expect(everyLabel(30)).toBe('自动刷新 30 秒')
    expect(everyLabel(300)).toBe('自动刷新 5 分钟')
    expect(everyOption(10)).toBe('每 10 秒')
  })
})
