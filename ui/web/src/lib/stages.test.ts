import { describe, expect, it } from 'vitest'

import type { Capability } from '@/api/types'

import { actorOf, coverageSentence, groupByStage } from './stages'

const cap = (name: string, stage: string, needs_executor = false): Capability => ({
  name, stage, level: 'run', title: name, what: 'w', summary: 's', inputs: [], outputs: [], params: [],
  needs_executor, needs_compute: false, criteria: [], used_by: [],
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
  it('谁来做与覆盖范围', () => {
    expect(actorOf({ needs_executor: true })).toBe('助理')
    expect(actorOf({ needs_executor: false })).toBe('机器')
    expect(coverageSentence(['设计', '实验'])).toBe('覆盖 设计 → 实验')
    expect(coverageSentence([])).toBe('不含能力步骤')
  })
})
