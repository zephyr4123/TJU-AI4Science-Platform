import { describe, expect, it } from 'vitest'

import type { Capability } from '@/api/types'

import { coverageSentence, groupByStage } from './stages'

const cap = (name: string, stage: string, needs_executor = false): Capability => ({
  name, stage, stage_slug: stage, title: `${name} 的活`, brief: 'b', does: 'd', does_not: 'n', brings: 'b', leaves: 'l',
  stops: 's', params: [], needs_executor, needs_compute: false, continuable: false, used_by: [],
})

describe('按阶段分组', () => {
  it('空阶段占格，顺序跟后端', () => {
    const groups = groupByStage(['文献', '设计', '验证'], [cap('verify', '验证'), cap('design', '设计')])
    expect(groups.map((g) => [g.stage, g.caps.map((c) => c.name)])).toEqual([
      ['文献', []], ['设计', ['design']], ['验证', ['verify']],
    ])
  })
  it('清单外的阶段追加在末尾，不丢能力', () => {
    const groups = groupByStage(['设计'], [cap('x', '写作')])
    expect(groups.map((g) => g.stage)).toEqual(['设计', '写作'])
    expect(groups[1].caps).toHaveLength(1)
  })
  it('经过哪几个阶段', () => {
    expect(coverageSentence(['设计', '实验'])).toBe('设计 → 实验')
    expect(coverageSentence([])).toBe('没有阶段')
  })
})
