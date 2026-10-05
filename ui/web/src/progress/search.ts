// 文献检索的进度（外层 #244）：把 `progress.jsonl` 的事件推成面板要画的样子——每一步在不在跑、各几个数，蜂巢里每一格。
// 事件由 `framework/capabilities/literature_search/loop.py` 写：每一步开始一行、做完一行带数；筛完每篇一行；下原文每篇一行。
// 执行层那一段（写种子、每轮筛选）中途没有动静：只知道「在这一步、从几点起」，正在筛的那一批画成虚格，不猜筛到哪一篇。
import type { OutputStatus } from '@/api/types'

import type { Phase, ProgressEvent } from './events'

/** 蜂巢一格：筛选中（虚格）、未收录、收录、有原文 */
export type CellState = 'screening' | 'out' | 'in' | 'text'

export interface Cell { key: string; title: string; hop: number; state: CellState; seed: boolean }
export interface Source { name: string; hits: number | null; failed: boolean; done: boolean }
export interface Round { hop: number; admitted: number | null; screened: number | null; included: number | null }
interface Step { phase: Phase; since: string | null }

export interface SearchView {
  seeds: Step & { seeds: number | null; queries: number | null }
  gather: Step & { found: number | null; sources: Source[] }
  screen: Step & { screened: number; included: number }
  expand: Step & { hop: number | null }
  fulltext: Step & { n: number | null; ok: number }
  rounds: Round[]
  cells: Cell[]
  started: string
  ended: string | null
}

/** 四家检索源，与 `literature_search/gather.py` 同序：OpenAlex 在主线程查（汇集做完才知道），另三家各自查完报一行 */
export const SOURCES = ['OpenAlex', 'Crossref', 'arXiv', 'Europe PMC']

const num = (v: unknown): number | null => (typeof v === 'number' ? v : null)

export function searchView(events: ProgressEvent[], status: OutputStatus, createdAt: string): SearchView {
  const step = (): Step => ({ phase: 'pending', since: null })
  const view: SearchView = {
    seeds: { ...step(), seeds: null, queries: null },
    gather: { ...step(), found: null, sources: SOURCES.map((name) => ({ name, hits: null, failed: false, done: false })) },
    screen: { ...step(), screened: 0, included: 0 },
    expand: { ...step(), hop: null },
    fulltext: { ...step(), n: null, ok: 0 },
    rounds: [],
    cells: [],
    started: events[0]?.at ?? createdAt,
    ended: status === 'running' ? null : events.at(-1)?.at ?? null,
  }
  const cells = new Map<string, Cell>()
  let batch: { hop: number; n: number } | null = null
  const round = (hop: number): Round => {
    let r = view.rounds.find((x) => x.hop === hop)
    if (!r) { r = { hop, admitted: null, screened: null, included: null }; view.rounds.push(r) }
    return r
  }
  const source = (name: string): Source => {
    let s = view.gather.sources.find((x) => x.name === name)
    if (!s) { s = { name, hits: null, failed: false, done: false }; view.gather.sources.push(s) }
    return s
  }

  for (const e of events) {
    const done = e.done === true
    if (e.step === 'seeds') {
      if (done) Object.assign(view.seeds, { phase: 'done', seeds: num(e.seeds), queries: num(e.queries) })
      else Object.assign(view.seeds, { phase: 'running', since: e.at })
    } else if (e.step === 'gather') {
      if (typeof e.source === 'string') {
        Object.assign(source(e.source), { hits: num(e.hits), failed: e.failed === true, done: true })
      } else if (done) {
        view.gather.phase = 'done'
        view.gather.found = num(e.found)
        for (const [name, hits] of Object.entries((e.sources ?? {}) as Record<string, unknown>)) {
          Object.assign(source(name), { hits: num(hits), done: true })
        }
        round(0).admitted = num(e.admitted)
      } else Object.assign(view.gather, { phase: 'running', since: e.at })
    } else if (e.step === 'screen') {
      const hop = num(e.hop) ?? 0
      if (typeof e.paper === 'string') {
        cells.set(e.paper, { key: e.paper, title: String(e.title ?? ''), hop, seed: e.seed === true,
                             state: e.include === true ? 'in' : 'out' })
      } else if (done) {
        batch = null
        view.screen.phase = 'done'
        round(hop).included = num(e.included)
      } else {
        batch = { hop, n: num(e.n) ?? 0 }
        Object.assign(view.screen, { phase: 'running', since: e.at })
        round(hop).screened = batch.n
      }
    } else if (e.step === 'expand') {
      const hop = num(e.hop) ?? 0
      if (done) {
        view.expand.phase = 'done'
        round(hop).admitted = num(e.admitted)
      } else Object.assign(view.expand, { phase: 'running', since: e.at, hop })
    } else if (e.step === 'fulltext') {
      if (typeof e.paper === 'string') {
        const cell = cells.get(e.paper)
        if (e.ok === true) {
          view.fulltext.ok += 1
          if (cell) cell.state = 'text'
        }
      } else if (done) {
        view.fulltext.phase = 'done'
        view.fulltext.ok = num(e.ok) ?? view.fulltext.ok
      } else Object.assign(view.fulltext, { phase: 'running', since: e.at, n: num(e.n) })
    }
  }

  // 第 0 轮的种子放正中，其余按轮次、按筛完的先后往外排；正在筛的那一批接在最外面，画成虚格
  const real = [...cells.values()].sort((a, b) => a.hop - b.hop || Number(b.seed) - Number(a.seed))
  view.cells = batch
    ? [...real, ...Array.from({ length: batch.n }, (_, i): Cell => ({ key: `?${batch!.hop}-${i}`, title: '', hop: batch!.hop, state: 'screening', seed: false }))]
    : real
  view.screen.screened = real.length
  view.screen.included = real.filter((c) => c.state !== 'out').length
  view.rounds.sort((a, b) => a.hop - b.hop)

  if (status === 'running' && events.length === 0) Object.assign(view.seeds, { phase: 'running', since: createdAt })
  if (status !== 'running') {
    for (const s of [view.seeds, view.gather, view.screen, view.expand, view.fulltext]) {
      if (s.phase === 'running') s.phase = status === 'failed' ? 'failed' : 'done'
      else if (s.phase === 'pending') s.phase = 'skipped'
    }
    view.cells = view.cells.filter((c) => c.state !== 'screening')
  }
  return view
}
