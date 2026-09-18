import { describe, expect, it } from 'vitest'

import { shownValue, storedTuning, thinkingWord } from './tuning'

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

describe('thinkingWord', () => {
  const five = ['low', 'medium', 'high', 'xhigh', 'max'].map((id) => ({ id, label: id, note: '' }))
  it('五档：前两档 thinking，往上 hard / deep / ultra', () => {
    expect(five.map((c) => thinkingWord(c.id, five))).toEqual(
      ['thinking', 'thinking', 'hard thinking', 'deep thinking', 'ultra thinking'])
  })
  it('没选、不在清单、清单只有一档，都是 thinking', () => {
    expect(thinkingWord('', five)).toBe('thinking')
    expect(thinkingWord('zz', five)).toBe('thinking')
    expect(thinkingWord('only', [{ id: 'only', label: '唯一', note: '' }])).toBe('thinking')
  })
})

describe('shownValue', () => {
  it('记着的 > 后端缺省 > 默认', () => {
    expect(shownValue('opus', 'sonnet')).toBe('opus')
    expect(shownValue(null, 'sonnet')).toBe('sonnet')
    expect(shownValue(null, null)).toBe('')
  })
})
