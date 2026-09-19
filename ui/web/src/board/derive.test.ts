import { describe, expect, it } from 'vitest'

import type { FlowProgress } from '@/api/types'

import { needsSign } from './derive'

const out = (id: string, signed = false, stale = false) =>
  ({ id, title: 't', status: 'ok' as const, by: 'design', from: [], signed, signed_stale: stale })

const flow = (items: FlowProgress['items']): FlowProgress => ({
  name: 'f', title: 'f', summary: '', stages: [], layout: null, covers: [], remarks: [], problems: [], items,
  step: 0, total: items?.length ?? 0, waiting: 'sign', job: null,
})

describe('等人签的产出', () => {
  it('断点管前一个阶段的产出：没签的、签了又改的都在等', () => {
    const f = flow([
      { kind: 'stage', index: 0, stage: '设计', caps: [], outputs: [out('design/1'), out('design/2', true), out('design/3', true, true)] },
      { kind: 'stop', index: 1, note: '核对', outputs: [], signed: false },
      { kind: 'stage', index: 2, stage: '实验', caps: [], outputs: [out('experiment/1')] },
    ])
    expect([...needsSign([f])].sort()).toEqual(['design/1', 'design/3'])
  })
  it('没有断点就没人在等；坏掉的流没有 items', () => {
    expect(needsSign([flow([{ kind: 'stage', index: 0, stage: '设计', caps: [], outputs: [out('design/1')] }])]).size).toBe(0)
    expect(needsSign([{ ...flow(undefined), items: undefined }]).size).toBe(0)
  })
})
