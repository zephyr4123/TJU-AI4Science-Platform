import { describe, expect, it } from 'vitest'

import type { FlowItem, FlowState, RunSummary, TaskSummary } from '@/api/types'

import { deriveRunItems, deriveTaskItems, synthesizeFlow, taskPart, waitingSentence } from './derive'

const room = (stage: string, caps: string[] = []): FlowItem =>
  ({ kind: 'room', stage, caps: caps.map((cap) => ({ cap, with: {} })) })
const stop = (note: string, key: 'publish' | 'accept' | null = null): FlowItem => ({ kind: 'stop', key, note })

// 出厂那条：假设 →◆发布 → 设计 →◆核对 → 实验 → 分析 → 验证 →◆验收
const research: FlowItem[] = [
  room('假设'), stop('发布', 'publish'), room('设计'), stop('核对裁判'),
  room('实验', ['auto-research']), room('分析'), room('验证'), stop('验收', 'accept'),
]
const titleOf = (cap: string) => (cap === 'auto-research' ? 'auto-research' : undefined)
const flow = (step: number, waiting: string, rooms = research): FlowState =>
  ({ workflow: 'research', title: '从课题到验证', step, total: rooms.length, rooms,
     next: rooms[step] ?? null, waiting, updated_at: null })
const accepted = { accepted_at: 't', by: '李', best_iter: 1, best_metric: 1, best_commit: 'c', verify: 'PASS', stale: false }

describe('run 的脊柱', () => {
  it('便条说到第几项：前面实心、当前按在等谁、后面虚线', () => {
    expect(deriveRunItems(flow(4, 'job:job-1'), { accept: null }).map((s) => s.state))
      .toEqual(['done', 'done', 'done', 'done', 'running', 'todo', 'todo', 'todo'])
    expect(waitingSentence(deriveRunItems(flow(4, 'job:job-1'), { accept: null }), titleOf)).toBe('auto-research跑着')
    const atAnalysis = deriveRunItems(flow(5, 'assistant'), { accept: null })
    expect(atAnalysis[5].state).toBe('assistant')
    expect(waitingSentence(atAnalysis, titleOf)).toBe('分析间，轮到助理')
  })
  it('停在断点：出厂的两个说等你发布 / 验收，别的说等你确认什么', () => {
    const items = [room('实验'), stop('看一眼结论'), room('分析')]
    const parked = deriveRunItems(flow(1, 'human', items), { accept: null })
    expect(parked.map((s) => s.state)).toEqual(['done', 'wait-human', 'todo'])
    expect(waitingSentence(parked, titleOf)).toBe('等你确认：看一眼结论')
    const before = deriveRunItems(flow(7, 'key:accept'), { accept: null })
    expect(before[7].state).toBe('wait-key')
    expect(waitingSentence(before, titleOf)).toBe('等你验收')
  })
  it('验收签过就算完成，便条不会替人的确认推进', () => {
    const after = deriveRunItems(flow(7, 'key:accept'), { accept: accepted })
    expect(after[7].state).toBe('done')
    expect(waitingSentence(after, titleOf)).toBe('走完了')
  })
  it('没照流的老 run 从文件推一条出来', () => {
    const run = { last_iter: 3, analysis: true, verify: null, job: null, accept: null, updated_at: 't' } as unknown as RunSummary
    const f = synthesizeFlow(run, research, 'research', '从课题到验证')
    expect(f.step).toBe(6)
    expect(f.waiting).toBe('assistant')
    expect(deriveRunItems(f, { accept: null }).map((s) => s.state))
      .toEqual(['done', 'done', 'done', 'done', 'done', 'done', 'assistant', 'todo'])
    const done = { ...run, verify: { status: 'PASS' }, accept: accepted } as unknown as RunSummary
    expect(synthesizeFlow(done, research, 'research', 't').waiting).toBe('done')
  })
})

describe('任务包那一段的脊柱', () => {
  const task = (stage: 'drafting' | 'published' | 'designed' | 'baselined', ok: boolean) =>
    ({ id: 't', stage, publish: { ok, state: ok ? 'ok' : 'missing', by: null, at: null, reason: null } }) as unknown as TaskSummary
  it('任务包那一段到第一间别的房间为止', () => {
    expect(taskPart(research)).toEqual(research.slice(0, 4))
    expect(taskPart([room('假设'), room('写作')])).toEqual([room('假设')])
    expect(taskPart([room('假设'), stop('发布', 'publish'), room('设计')])).toHaveLength(3)
  })
  it('没有任务包时轮到助理起包，其余都是以后的事', () => {
    expect(deriveTaskItems(taskPart(research), null, null).map((s) => s.state))
      .toEqual(['assistant', 'todo', 'todo', 'todo'])
  })
  it('需求填好就等发布；发布后轮到助理写裁判；基线跑完等人核对', () => {
    expect(deriveTaskItems(taskPart(research), task('drafting', false), []).map((s) => s.state))
      .toEqual(['done', 'wait-key', 'todo', 'todo'])
    expect(deriveTaskItems(taskPart(research), task('drafting', false), ['还有待填']).map((s) => s.state)[0]).toBe('assistant')
    expect(deriveTaskItems(taskPart(research), task('published', true), []).map((s) => s.state))
      .toEqual(['done', 'done', 'assistant', 'todo'])
    const baselined = deriveTaskItems(taskPart(research), task('baselined', true), [])
    expect(baselined.map((s) => s.state)).toEqual(['done', 'done', 'done', 'wait-human'])
    expect(waitingSentence(baselined, titleOf)).toBe('等你确认：核对裁判')
  })
})
