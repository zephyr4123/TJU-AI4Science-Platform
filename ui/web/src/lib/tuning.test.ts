import { describe, expect, it } from 'vitest'

import { shownValue, storedTuning } from './tuning'

describe('storedTuning', () => {
  it('没碰过就沿用对话上记的；没有对话就是缺省', () => {
    expect(storedTuning({}, { model: 'opus', effort: 'high' })).toEqual({ model: 'opus', effort: 'high' })
    expect(storedTuning({}, null)).toEqual({ model: null, effort: null })
  })
  it('这次改过的压过记的，改回缺省（null）也算改过', () => {
    expect(storedTuning({ effort: 'low' }, { model: 'opus', effort: 'high' })).toEqual({ model: 'opus', effort: 'low' })
    expect(storedTuning({ model: null }, { model: 'opus', effort: 'high' })).toEqual({ model: null, effort: 'high' })
  })
})

describe('shownValue', () => {
  it('记着的 > 后端缺省 > 默认', () => {
    expect(shownValue('opus', 'sonnet')).toBe('opus')
    expect(shownValue(null, 'sonnet')).toBe('sonnet')
    expect(shownValue(null, null)).toBe('')
  })
})
