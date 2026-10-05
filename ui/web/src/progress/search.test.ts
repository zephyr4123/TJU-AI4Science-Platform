import { describe, expect, it } from 'vitest'

import type { ProgressEvent } from './events'
import { searchView } from './search'

const T0 = '2026-10-05T05:23:54+00:00'
let tick = 0
const at = () => `2026-10-05T05:${String(24 + Math.floor(tick / 60)).padStart(2, '0')}:${String(tick++ % 60).padStart(2, '0')}+00:00`
const ev = (fields: Record<string, unknown>): ProgressEvent => ({ at: at(), ...fields })
const paper = (key: string, hop: number, include: boolean, seed = false) =>
  ev({ step: 'screen', hop, paper: key, title: `题目 ${key}`, include, seed })

// 一次检索走到第 1 轮筛选中途：种子、汇集、第 0 轮筛完（收 2 篇）、扩出第 1 轮 3 篇、正在筛
const HALF: ProgressEvent[] = [
  ev({ step: 'seeds' }),
  ev({ step: 'seeds', done: true, seeds: 2, queries: 4 }),
  ev({ step: 'gather' }),
  ev({ step: 'gather', source: 'arXiv', hits: 12, failed: false }),
  ev({ step: 'gather', source: 'Crossref', hits: 0, failed: true }),
  ev({ step: 'gather', done: true, found: 30, admitted: 3, sources: { OpenAlex: 5, Crossref: 0, arXiv: 12, 'Europe PMC': 7 } }),
  ev({ step: 'screen', hop: 0, n: 3 }),
  paper('W2', 0, true), paper('W1', 0, true, true), paper('W3', 0, false),
  ev({ step: 'screen', hop: 0, done: true, included: 2 }),
  ev({ step: 'expand', hop: 1 }),
  ev({ step: 'expand', hop: 1, done: true, admitted: 3 }),
  ev({ step: 'screen', hop: 1, n: 3 }),
]

describe('searchView', () => {
  it('筛选中：前几步完成带数，筛选在跑，正在筛的那一批是虚格、接在最外面', () => {
    const v = searchView(HALF, 'running', T0)
    expect([v.seeds.phase, v.gather.phase, v.screen.phase, v.expand.phase, v.fulltext.phase])
      .toEqual(['done', 'done', 'running', 'done', 'pending'])
    expect([v.seeds.seeds, v.gather.found, v.screen.screened, v.screen.included]).toEqual([2, 30, 3, 2])
    expect(v.screen.since).toBe(HALF.at(-1)!.at)
    // 种子在正中，然后第 0 轮其余的，再是三格虚的
    expect(v.cells.map((c) => [c.key, c.state])).toEqual([
      ['W1', 'in'], ['W2', 'in'], ['W3', 'out'], ['?1-0', 'screening'], ['?1-1', 'screening'], ['?1-2', 'screening']])
    expect(v.rounds).toEqual([{ hop: 0, admitted: 3, screened: 3, included: 2 }, { hop: 1, admitted: 3, screened: 3, included: null }])
    expect(v.ended).toBeNull()
  })

  it('四家检索源：三家各自查完就亮，OpenAlex 等汇集做完；查失败的照记', () => {
    const v = searchView(HALF.slice(0, 5), 'running', T0)
    expect(v.gather.phase).toBe('running')
    expect(v.gather.sources).toEqual([
      { name: 'OpenAlex', hits: null, failed: false, done: false },
      { name: 'Crossref', hits: 0, failed: true, done: true },
      { name: 'arXiv', hits: 12, failed: false, done: true },
      { name: 'Europe PMC', hits: null, failed: false, done: false }])
    expect(searchView(HALF, 'running', T0).gather.sources.every((s) => s.done)).toBe(true)
  })

  it('下原文：每下到一篇，那一格从收录变成有原文', () => {
    const v = searchView([...HALF, paper('W4', 1, true), paper('W5', 1, false), paper('W6', 1, false),
      ev({ step: 'screen', hop: 1, done: true, included: 1 }),
      ev({ step: 'fulltext', n: 3 }), ev({ step: 'fulltext', paper: 'W1', ok: true }), ev({ step: 'fulltext', paper: 'W4', ok: false })], 'running', T0)
    expect(v.fulltext).toMatchObject({ phase: 'running', n: 3, ok: 1 })
    expect(Object.fromEntries(v.cells.map((c) => [c.key, c.state]))).toEqual({
      W1: 'text', W2: 'in', W3: 'out', W4: 'in', W5: 'out', W6: 'out' })
  })

  it('刚开工还没有事件：种子那一步在跑，从产出开的时候算', () => {
    const v = searchView([], 'running', T0)
    expect(v.seeds).toMatchObject({ phase: 'running', since: T0 })
    expect(v.started).toBe(T0)
  })

  it('作业失败：停在哪一步哪一步记失败，没走到的记跳过，虚格不留', () => {
    const v = searchView(HALF, 'failed', T0)
    expect([v.screen.phase, v.fulltext.phase]).toEqual(['failed', 'skipped'])
    expect(v.cells.some((c) => c.state === 'screening')).toBe(false)
    expect(v.ended).toBe(HALF.at(-1)!.at)
  })
})
