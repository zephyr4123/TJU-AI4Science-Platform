import { describe, expect, it } from 'vitest'

import type { ProgressEvent } from './events'
import { readView } from './read'

const T0 = '2026-10-05T05:33:43+00:00'
const ev = (sec: number, fields: Record<string, unknown>): ProgressEvent =>
  ({ at: `2026-10-05T05:34:${String(sec).padStart(2, '0')}+00:00`, ...fields })

const EVENTS: ProgressEvent[] = [
  ev(0, { papers: [{ n: '1', title: 'Mem0' }, { n: '2', title: 'A-Mem' }, { n: '3', title: 'Zep' }], sessions: 2 }),
  ev(1, { paper: '1', state: 'reading' }),
  ev(1, { paper: '2', state: 'reading' }),
  ev(20, { paper: '2', state: 'done', quotes: 6, found: 5 }),
  ev(21, { paper: '3', state: 'reading' }),
  ev(30, { paper: '1', state: 'failed', why: '会话没走完（退出码 1）' }),
]

describe('readView', () => {
  it('每篇照最后一行事件落在哪一堆；原句只数读完的', () => {
    const v = readView(EVENTS, 'running', T0)
    expect(v.sessions).toBe(2)
    expect(v.papers.map((p) => [p.n, p.state])).toEqual([['1', 'failed'], ['2', 'done'], ['3', 'reading']])
    expect(v.papers[0].why).toBe('会话没走完（退出码 1）')
    expect([v.quotes, v.found]).toEqual([6, 5])
    expect(v.ended).toBeNull()
  })

  it('还没开头那一行：一篇都不知道，从产出开的时候算', () => {
    const v = readView([], 'running', T0)
    expect(v.papers).toEqual([])
    expect(v.started).toBe(T0)
  })

  it('作业停了：在读的算没读成，失败时排队的也算', () => {
    const queued = [...EVENTS.slice(0, 3)]
    expect(readView(queued, 'failed', T0).papers.map((p) => p.state)).toEqual(['failed', 'failed', 'failed'])
    expect(readView(EVENTS, 'ok', T0).papers.map((p) => p.state)).toEqual(['failed', 'done', 'failed'])
  })

  it('不认识的篇号跳过，不报错', () => {
    const v = readView([...EVENTS, ev(40, { paper: '99', state: 'done', quotes: 1, found: 1 })], 'running', T0)
    expect(v.papers).toHaveLength(3)
  })
})
