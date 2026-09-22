import { describe, expect, it } from 'vitest'

import type { FlowBrief, WorkspaceRow } from '@/api/types'

import { rowState } from './derive'

const flow = (over: Partial<FlowBrief> = {}): FlowBrief =>
  ({ name: 'reproduce', title: '论文复现', step: 4, total: 6, waiting: 'done', problems: [], ...over })

const row = (over: Partial<WorkspaceRow> = {}): WorkspaceRow => ({
  id: 'w', title: '综述', root: '/x', running: 0, jobs: [], flows: [],
  requirement: { confirmed: true, version: 1, by: 'z', at: 't', dirty: false },
  counts: { literature: 1, design: 2 },
  ...over,
})

describe('项目页上一行工作区', () => {
  it('需求没确认先说需求，别的都不看', () => {
    expect(rowState(row({ requirement: { confirmed: false, version: null, by: null, at: null, dirty: false }, running: 2 })))
      .toMatchObject({ word: '需求未确认', tone: 'warn', mark: 'pending', details: ['产出 3 次'] })
  })
  it('有作业在跑就是运行中；坏流程文件先说有误；没取流程说没取', () => {
    expect(rowState(row({ running: 1 }))).toMatchObject({ word: '运行中', mark: 'running' })
    expect(rowState(row({ flows: [flow({ problems: ['坏了'] })] }))).toMatchObject({ word: '流程文件有误', tone: 'bad', mark: 'failed' })
    expect(rowState(row({ counts: {} }))).toMatchObject({ word: '尚未选定流程', tone: 'neutral', details: [] })
  })
  it('几条流程各在等谁：等人 > 在跑 > 等助理 > 全走完', () => {
    expect(rowState(row({ flows: [flow(), flow({ name: 'b', title: '对照', waiting: 'sign' })] })))
      .toMatchObject({ word: '待确认', tone: 'warn', details: ['论文复现 4 / 6 等 2 条', '产出 3 次'] })
    expect(rowState(row({ flows: [flow({ waiting: 'job' })] }))).toMatchObject({ word: '运行中', mark: 'running' })
    expect(rowState(row({ flows: [flow({ waiting: 'assistant', step: 2 })] }))).toMatchObject({ word: '进行中', details: ['论文复现 2 / 6', '产出 3 次'] })
    expect(rowState(row({ flows: [flow()] }))).toMatchObject({ word: '完成', tone: 'ok', mark: 'done' })
  })
})
