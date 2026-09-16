import { describe, expect, it } from 'vitest'

import type { RunSummary, TaskSummary } from '@/api/types'

import { progressOf } from './progress'

const task = (stage: TaskSummary['stage']): TaskSummary => ({
  id: 't', title: 't', question: '', domain: 'generic', metric: null, stage,
  publish: { ok: stage !== 'drafting', state: stage === 'drafting' ? 'missing' : 'ok', by: null, at: null, reason: null },
})
const run = (partial: Partial<RunSummary>): RunSummary => ({
  run_id: 'r', task: 't', title: 't', metric: { name: 'm', direction: 'minimize' }, baseline: 1,
  best_metric: 0.9, best_iter: 1, last_iter: 1, stop_reason: null, updated_at: '2026', cost_usd: 0,
  running: false, analysis: false, verify: null, accept: null, ...partial,
})

describe('progressOf', () => {
  it('没发布：全空，说清什么都没开始', () => {
    const p = progressOf(task('drafting'), [])
    expect(p.states).toEqual(['current', 'todo', 'todo', 'todo', 'todo'])
    expect(p.now).toBe('需求还没发布，什么都还没开始。')
  })
  it('基线跑完没开实验：前两步勾，第三步当前', () => {
    const p = progressOf(task('baselined'), [])
    expect(p.states).toEqual(['done', 'done', 'current', 'todo', 'todo'])
    expect(p.now).toBe('基线跑完，等开实验。')
  })
  it('分析验证都过：五步全勾，验收过就说可以开下一个', () => {
    const r = run({ analysis: true, verify: { status: 'PASS' }, accept: { accepted_at: '', by: 'x', best_iter: 1, best_metric: 0.9, best_commit: 'c', verify: 'PASS', stale: false } })
    const p = progressOf(task('baselined'), [r])
    expect(p.states.every((s) => s === 'done')).toBe(true)
    expect(p.next).toBe('可以开下一个课题了。')
  })
  it('只认自己课题的 run', () => {
    expect(progressOf(task('baselined'), [run({ task: 'other', last_iter: 5 })]).states[2]).toBe('current')
  })
})
