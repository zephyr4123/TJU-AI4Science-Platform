import { describe, expect, it } from 'vitest'

import type { TurnRecord } from '@/api/types'

import { assembleTurns, type LiveTurn } from './turns'

const record = (turn: number): TurnRecord => ({ turn, origin: '人', message: `第 ${turn} 句`, reply: '好', events: [] })
const live = (over: Partial<LiveTurn> = {}): LiveTurn => ({ chatId: 'c1', n: 2, message: '正在问', trace: [], outcome: null, ...over })

describe('屏上的轮次', () => {
  it('落盘的在前、进行中的接在后面，没落盘就是 live', () => {
    const turns = assembleTurns([record(1)], live(), 'c1')
    expect(turns.map((t) => [t.n, t.live])).toEqual([[1, false], [2, true]])
    expect(turns[1].message).toBe('正在问')
  })
  it('还没开出对话的那一句（chatId 为 null）在哪段都显示；别段对话的那一轮不显示', () => {
    expect(assembleTurns([], live({ chatId: null, n: 1 }), null)).toHaveLength(1)
    expect(assembleTurns([], live({ chatId: null, n: 1 }), 'c9')).toHaveLength(1)
    expect(assembleTurns([record(1)], live({ chatId: 'c1' }), 'c2')).toHaveLength(1)
  })
  it('别的进程正在跑的那一轮（作业跑完叫醒助理）接在后面，标着谁开的口、是 live；跑完落盘就不重复', () => {
    const running: TurnRecord = { turn: 2, origin: '框架', message: '作业跑完了', reply: '', events: [
      { kind: 'tool_use', text: '', tool: 'Bash', tool_input: { command: 'ls' } } as never] }
    const turns = assembleTurns([record(1)], null, 'c1', running)
    expect(turns.map((t) => [t.n, t.origin, t.live])).toEqual([[1, '人', false], [2, '框架', true]])
    expect(turns[1].trace).toHaveLength(1)
    expect(assembleTurns([record(1), record(2)], null, 'c1', running).map((t) => t.n)).toEqual([1, 2])
  })
  it('自己发的这一轮在跑时，同一轮不再从盘上摆第二遍', () => {
    const running: TurnRecord = { turn: 2, origin: '人', message: '正在问', reply: '', events: [] }
    expect(assembleTurns([record(1)], live(), 'c1', running).map((t) => t.n)).toEqual([1, 2])
  })
  it('落盘之后同一轮不重复', () => {
    const turns = assembleTurns([record(1), record(2)], live({ outcome: { cost_usd: 0, duration_s: 1, error: null, exit_code: 0 } as never }), 'c1')
    expect(turns.map((t) => t.n)).toEqual([1, 2])
    expect(turns.every((t) => !t.live)).toBe(true)
  })
})
