import { describe, expect, it } from 'vitest'

import type { FlowState, RunSummary, Workflow } from '@/api/types'

import { deriveIntakeSteps, deriveRunSteps, synthesizeFlow, waitingSentence } from './derive'

const quick: Workflow = {
  name: 'quick-look', title: '快速看一眼', summary: 's', covers: [], remarks: [], problems: [],
  steps: [
    { by: '助理', does: '开一次实验', cap: 'start', key: null, with: {} },
    { by: '助理', does: '跑 3 轮', cap: 'experiment', key: null, with: { max_iters: 3 } },
    { by: '助理', does: '写分析', cap: 'analysis', key: null, with: {} },
    { by: '人', does: '看一眼结论', cap: null, key: null, with: {} },
  ],
}
const auto: Workflow = {
  ...quick, name: 'auto-research', title: '自动做实验',
  steps: [...quick.steps.slice(0, 3),
          { by: '助理', does: '验证', cap: 'verify', key: null, with: {} },
          { by: '人', does: '验收', cap: null, key: 'accept', with: {} }],
}
const flow = (step: number, waiting: string, wf = quick): FlowState =>
  ({ workflow: wf.name, title: wf.title, step, total: wf.steps.length, steps: wf.steps,
     next: wf.steps[step] ?? null, waiting, updated_at: null })

describe('run 的脊柱', () => {
  it('便条说到第几步：前面实心、当前按在等谁、后面虚线', () => {
    const states = deriveRunSteps(flow(1, 'job:job-1'), { accept: null }).map((s) => s.state)
    expect(states).toEqual(['done', 'running', 'todo', 'todo'])
    expect(deriveRunSteps(flow(3, 'human'), { accept: null }).map((s) => s.state))
      .toEqual(['done', 'done', 'done', 'wait-human'])
    expect(waitingSentence(deriveRunSteps(flow(3, 'human'), { accept: null }))).toBe('第 4 步轮到你')
  })
  it('验收键按过就算完成，便条不会替键推进', () => {
    const before = deriveRunSteps(flow(4, 'key:accept', auto), { accept: null })
    expect(before[4].state).toBe('wait-key')
    const after = deriveRunSteps(flow(4, 'key:accept', auto),
      { accept: { accepted_at: 't', by: '李', best_iter: 1, best_metric: 1, best_commit: 'c', verify: 'PASS', stale: false } })
    expect(after[4].state).toBe('done')
    expect(waitingSentence(after)).toBe('这条流走完了')
  })
  it('没照流的老 run 从文件推一条出来', () => {
    const run = { last_iter: 3, analysis: true, verify: null, job: null, updated_at: 't' } as unknown as RunSummary
    const f = synthesizeFlow(run, auto)
    expect(f.step).toBe(3)
    expect(f.waiting).toBe('assistant')
    expect(deriveRunSteps(f, { accept: null }).map((s) => s.state))
      .toEqual(['done', 'done', 'done', 'assistant', 'todo'])
  })
})

describe('需求对齐的脊柱', () => {
  const intake: Workflow = {
    ...quick, name: 'intake', title: '接一个新课题',
    steps: [
      { by: '人', does: '说清楚', cap: null, key: null, with: {} },
      { by: '助理', does: '起任务包', cap: 'init', key: null, with: {} },
      { by: '助理', does: '填模板', cap: null, key: null, with: {} },
      { by: '人', does: '发布', cap: null, key: 'publish', with: {} },
      { by: '助理', does: '接任务', cap: 'design', key: null, with: {} },
      { by: '人', does: '核对', cap: null, key: null, with: {} },
      { by: '助理', does: '跑基线', cap: 'baseline', key: null, with: {} },
    ],
  }
  const task = (stage: 'drafting' | 'published' | 'designed' | 'baselined', ok: boolean) =>
    ({ id: 't', stage, publish: { ok, state: ok ? 'ok' : 'missing', by: null, at: null, reason: null } }) as unknown as import('@/api/types').TaskSummary
  it('没有任务包时轮到人说清楚，其余都是以后的事', () => {
    expect(deriveIntakeSteps(intake, null, null).map((s) => s.state))
      .toEqual(['wait-human', 'todo', 'todo', 'todo', 'todo', 'todo', 'todo'])
  })
  it('模板填完就等发布键；发布后轮到助理接任务；基线跑完全部实心', () => {
    expect(deriveIntakeSteps(intake, task('drafting', false), []).map((s) => s.state))
      .toEqual(['done', 'done', 'done', 'wait-key', 'todo', 'todo', 'todo'])
    expect(deriveIntakeSteps(intake, task('drafting', false), ['还有待填']).map((s) => s.state)[2]).toBe('assistant')
    expect(deriveIntakeSteps(intake, task('published', true), []).map((s) => s.state))
      .toEqual(['done', 'done', 'done', 'done', 'assistant', 'todo', 'todo'])
    expect(deriveIntakeSteps(intake, task('baselined', true), []).every((s) => s.state === 'done')).toBe(true)
  })
})
