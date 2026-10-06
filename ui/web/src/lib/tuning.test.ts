import { describe, expect, it } from 'vitest'

import { thinkingWord } from './tuning'

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
