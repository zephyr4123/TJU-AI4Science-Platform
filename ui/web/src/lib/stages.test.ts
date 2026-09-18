import { describe, expect, it } from 'vitest'

import type { Capability } from '@/api/types'

import { actorOf, coverageSentence, groupByStage, itemLabel } from './stages'

const cap = (name: string, stage: string, needs_executor = false): Capability => ({
  name, stage, level: 'run', title: `${name} 的活`, does: 'd', does_not: 'n', brings: 'b', leaves: 'l', stops: 's',
  params: [], needs_executor, needs_compute: false, used_by: [],
})

describe('按房间分组', () => {
  it('空房间占格，顺序跟后端', () => {
    const groups = groupByStage(['文献', '设计', '验证'], [cap('verify', '验证'), cap('design', '设计')])
    expect(groups.map((g) => [g.stage, g.caps.map((c) => c.name)])).toEqual([
      ['文献', []], ['设计', ['design']], ['验证', ['verify']],
    ])
  })
  it('清单外的房间追加在末尾，不丢能力', () => {
    const groups = groupByStage(['设计'], [cap('x', '写作')])
    expect(groups.map((g) => g.stage)).toEqual(['设计', '写作'])
    expect(groups[1].caps).toHaveLength(1)
  })
  it('谁来做与走过哪几间', () => {
    expect(actorOf({ needs_executor: true })).toBe('助理')
    expect(actorOf({ needs_executor: false })).toBe('机器')
    expect(coverageSentence(['设计', '实验'])).toBe('设计 → 实验')
    expect(coverageSentence([])).toBe('没有房间')
  })
  it('一项的名字：房间带点名的能力标题，断点写要确认什么', () => {
    const title = (name: string) => (name === 'verify' ? '核对数字' : undefined)
    expect(itemLabel({ kind: 'room', stage: '验证', caps: [] }, title)).toBe('验证')
    expect(itemLabel({ kind: 'room', stage: '验证', caps: [{ cap: 'verify', with: {} }, { cap: 'x', with: {} }] }, title))
      .toBe('验证：核对数字、x')
    expect(itemLabel({ kind: 'stop', key: 'publish', note: '发布' }, title)).toBe('发布')
    expect(itemLabel({ kind: 'stop', key: null, note: '看一眼' }, title)).toBe('看一眼')
    expect(itemLabel({ kind: 'stop', key: null, note: '' }, title)).toBe('等你确认')
  })
})
