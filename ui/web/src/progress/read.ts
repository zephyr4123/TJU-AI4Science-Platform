// 文献精读的进度（外层 #245）：把 `progress.jsonl` 的事件推成面板要画的样子——每篇在哪一堆、原句核对了多少。
// 事件由 `framework/capabilities/literature_read/read.py` 写：开头一行列出要读的每篇与同时几个会话，之后每篇开始读、
// 读完（原句几条、在原文里找到几条）、没读成各一行。
import type { OutputStatus } from '@/api/types'

import type { ProgressEvent } from './events'

/** 一篇在哪：排队、在读、读完、没读成 */
export type PaperState = 'queued' | 'reading' | 'done' | 'failed'

export interface Paper { n: string; title: string; state: PaperState; quotes: number; found: number; why: string }

export interface ReadView {
  sessions: number
  papers: Paper[]
  /** 读完的笔记里一共几条原句、在原文里找到几条 */
  quotes: number
  found: number
  started: string
  ended: string | null
}

export function readView(events: ProgressEvent[], status: OutputStatus, createdAt: string): ReadView {
  const view: ReadView = { sessions: 0, papers: [], quotes: 0, found: 0, started: events[0]?.at ?? createdAt,
                           ended: status === 'running' ? null : events.at(-1)?.at ?? null }
  const byN = new Map<string, Paper>()
  for (const e of events) {
    if (Array.isArray(e.papers)) {
      view.sessions = typeof e.sessions === 'number' ? e.sessions : 0
      view.papers = (e.papers as { n: string; title: string }[]).map((p) => ({ n: String(p.n), title: String(p.title ?? ''),
                                                                               state: 'queued', quotes: 0, found: 0, why: '' }))
      for (const p of view.papers) byN.set(p.n, p)
      continue
    }
    const p = typeof e.paper === 'string' ? byN.get(e.paper) : undefined
    if (!p) continue
    if (e.state === 'reading') p.state = 'reading'
    else if (e.state === 'done') Object.assign(p, { state: 'done', quotes: Number(e.quotes ?? 0), found: Number(e.found ?? 0) })
    else if (e.state === 'failed') Object.assign(p, { state: 'failed', why: String(e.why ?? '') })
  }
  // 作业停了还有在读的：没读完就是没读成（页面不替它说「还在读」）
  if (status !== 'running') {
    for (const p of view.papers) if (p.state === 'reading' || (status === 'failed' && p.state === 'queued')) p.state = 'failed'
  }
  for (const p of view.papers) {
    if (p.state !== 'done') continue
    view.quotes += p.quotes
    view.found += p.found
  }
  return view
}
