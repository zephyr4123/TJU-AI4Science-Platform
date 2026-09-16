import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api } from '@/api/client'
import { streamTurn } from '@/api/sse'
import type { ChatEvent } from '@/api/types'
import BlurText from '@/components/BlurText'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { usd } from '@/lib/format'
import { useResource } from '@/lib/useResource'
import { chatTitle } from '@/sidebar/Sidebar'

import { Composer } from './Composer'
import { outcome, reduceTrace, type TraceItem, type TurnOutcome } from './trace'
import { type Turn, TurnView } from './TurnView'

interface Props {
  /** 换对话时父组件用 key 重建本组件，所以这里的状态天然按对话隔离 */
  chatId: string | null
  boardOpen: boolean
  onToggleBoard: () => void
  onNew: () => void
  /** 一轮结束：助理可能按了按钮、改了任务包或 run，看板要重读 */
  onTurnDone: () => void
}

interface LiveTurn {
  n: number
  message: string
  trace: TraceItem[]
  outcome: TurnOutcome | null
}

type Kept = Record<number, { trace: TraceItem[]; outcome: TurnOutcome }>

export function ChatView({ chatId, boardOpen, onToggleBoard, onNew, onTurnDone }: Props) {
  const doc = useResource(() => (chatId ? api.chat(chatId) : Promise.resolve(null)), [chatId])
  const [live, setLive] = useState<LiveTurn | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)
  // 本次打开页面期间跑过的轮次，按轮号留着它的按钮轨迹；刷新后只剩落盘的问答
  const [kept, setKept] = useState<Kept>({})
  const bottom = useRef<HTMLDivElement>(null)

  const turns = useMemo<Turn[]>(() => {
    const settled: Turn[] = (doc.data?.history ?? []).map((t) => ({
      n: t.turn, message: t.message, reply: t.reply,
      trace: kept[t.turn]?.trace ?? [], outcome: kept[t.turn]?.outcome ?? null, live: false,
    }))
    if (live) {
      settled.push({ n: live.n, message: live.message, reply: null, trace: live.trace,
                     outcome: live.outcome, live: live.outcome === null })
    }
    return settled
  }, [doc.data, kept, live])

  const traceLength = live?.trace.length ?? 0
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [turns.length, traceLength])

  const send = useCallback(async (text: string) => {
    if (!chatId) return
    const n = (doc.data?.history.at(-1)?.turn ?? 0) + 1
    setSendError(null)
    let current: LiveTurn = { n, message: text, trace: [], outcome: null }
    setLive(current)
    try {
      await streamTurn(chatId, text, (event: ChatEvent) => {
        const done = event.kind === 'done' || event.kind === 'error' ? outcome(event) : current.outcome
        current = { ...current, trace: reduceTrace(current.trace, event), outcome: done }
        setLive(current)
      })
    } catch (exc) {
      setSendError(exc instanceof Error ? exc.message : String(exc))
    }
    // 流断了也没有 done：按"没走完"记，不假装成功
    const final = current.outcome ?? { costUsd: null, durationS: 0, failed: true }
    setKept((prev) => ({ ...prev, [n]: { trace: current.trace, outcome: final } }))
    setLive(null)
    await doc.reload()
    onTurnDone()
  }, [chatId, doc, onTurnDone])

  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b px-4">
        <h1 className="truncate text-sm font-semibold tracking-tight">
          {doc.data ? chatTitle(doc.data) : '对话'}
        </h1>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {doc.data && (
            <span className="tabular whitespace-nowrap">{doc.data.history.length} 轮 · 累计 {usd(doc.data.cost_usd)}</span>
          )}
          <Button variant="ghost" size="icon-sm" onClick={onToggleBoard}
                  aria-label={boardOpen ? '收起看板' : '展开看板'}>
            {boardOpen ? <PanelRightClose /> : <PanelRightOpen />}
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6">
          {!chatId && <Welcome onNew={onNew} />}
          {chatId && doc.loading && !doc.data && <Skeleton lines={4} />}
          {chatId && doc.error && <ErrorNote text={doc.error} />}
          {chatId && doc.data && turns.length === 0 && (
            <p className="text-sm leading-relaxed text-muted-foreground">
              这段对话还是空的。先说清三件事：想解决什么问题、数据或模型在哪、什么样的结果算好。
              助理会把它整理成右边「需求」看板上的任务包，你看过再发布。
            </p>
          )}
          <div className="space-y-8">
            {turns.map((turn) => <TurnView key={turn.n} turn={turn} />)}
          </div>
          {sendError && <ErrorNote text={sendError} className="mt-4" />}
          <div ref={bottom} />
        </div>
      </div>

      <Composer disabled={!chatId} busy={live !== null} onSend={(text) => void send(text)} />
    </div>
  )
}

function Welcome({ onNew }: { onNew: () => void }) {
  return (
    <div className="mx-auto max-w-xl py-16">
      <BlurText text="把实验交给助理，你只管两件事：发布需求，验收结果。" delay={60}
                animateBy="words" direction="top"
                className="text-2xl font-semibold tracking-tight text-balance" />
      <p className="mt-4 max-w-prose text-sm leading-relaxed text-muted-foreground">
        对话里说清课题、数据和「怎么算好」，助理整理成任务包；右边看板上按下「发布」，
        它才能接任务、跑基线、开实验。跑完的结果在「结果」看板验收。
      </p>
      <Button className="mt-6" onClick={onNew}>开始一段对话</Button>
    </div>
  )
}
