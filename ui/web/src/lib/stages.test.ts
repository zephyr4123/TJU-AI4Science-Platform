import { describe, expect, it } from 'vitest'

import { coverageSentence } from './stages'

describe('阶段', () => {
  it('经过哪几个阶段', () => {
    expect(coverageSentence(['设计', '实验'])).toBe('设计 → 实验')
    expect(coverageSentence([])).toBe('没有阶段')
  })
})
