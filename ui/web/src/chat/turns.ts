// 屏上那一列轮次怎么拼（纯函数，有单测）：落盘的轮次从它的事件重放，正在进行的这一轮接在后面。
// 正在进行的那一轮记着它属于哪段对话：还没开出对话时是 null；换到别的对话看，它不该出现。
// 一轮跑完先重读落盘的再撤掉屏上的，中间那一帧两边都有——按轮次去重，人看不到闪。
// 别的进程正在跑的那一轮（作业跑完由作业进程叫醒助理，不经过这页的流，外层 #230）从盘上读来，
// 自己没在发的时候接在后面。
import type { TurnRecord } from '@/api/types'

import { replayTrace, type TraceItem, type TurnOutcome } from './trace'
import type { Turn } from './TurnView'

export interface LiveTurn {
  /** 属于哪段对话；还没开出对话时是 null */
  chatId: string | null
  n: number
  message: string
  trace: TraceItem[]
  outcome: TurnOutcome | null
}

export function assembleTurns(history: readonly TurnRecord[], live: LiveTurn | null, chatId: string | null,
                              running: TurnRecord | null = null): Turn[] {
  const settled: Turn[] = history.map((t) => ({
    n: t.turn, origin: t.origin, message: t.message, reply: t.reply, ...replayTrace(t.events), live: false,
  }))
  const mine = live && (live.chatId === null || live.chatId === chatId) ? live : null
  if (mine) {
    if (!settled.some((t) => t.n === mine.n)) {
      settled.push({ n: mine.n, origin: '人', message: mine.message, reply: null, trace: mine.trace,
                     outcome: mine.outcome, live: mine.outcome === null })
    }
  } else if (running && !settled.some((t) => t.n === running.turn)) {
    settled.push({ n: running.turn, origin: running.origin, message: running.message, reply: null,
                   ...replayTrace(running.events), live: true })
  }
  return settled
}
