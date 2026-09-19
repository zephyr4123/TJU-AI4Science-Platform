import { describe, expect, it } from 'vitest'

import { changedCount, diffLines } from './diff'

describe('行级 diff', () => {
  it('没改就全是 same', () => {
    const ops = diffLines('a\nb', 'a\nb')
    expect(ops.map((o) => o.kind)).toEqual(['same', 'same'])
    expect(changedCount(ops)).toBe(0)
  })
  it('加一行、删一行、改一行', () => {
    const ops = diffLines('# t\n\n## 问题\n\n有。\n', '# t\n\n## 问题\n\n改了。\n\n## 预算\n\n一天。\n')
    expect(ops.filter((o) => o.kind === 'removed').map((o) => o.text)).toEqual(['有。'])
    expect(ops.filter((o) => o.kind === 'added').map((o) => o.text).filter(Boolean)).toEqual(['改了。', '## 预算', '一天。'])
    expect(changedCount(ops)).toBe(6)
  })
  it('空文档', () => {
    expect(diffLines('', 'x')).toEqual([{ kind: 'removed', text: '' }, { kind: 'added', text: 'x' }])
  })
})
