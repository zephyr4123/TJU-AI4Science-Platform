import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { useReducedMotion } from 'motion/react'
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api, type Scope } from '@/api/client'
import { streamTurn } from '@/api/sse'
import type { ChatEvent, ChatMeta } from '@/api/types'
import BlurText from '@/components/BlurText'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Button } from '@/components/ui/button'
import Waves from '@/components/Waves'
import { usd } from '@/lib/format'
import { useResource } from '@/lib/useResource'

import { Composer } from './Composer'
import { outcome, reduceTrace, type TraceItem, type TurnOutcome } from './trace'
import { type Turn, TurnView } from './TurnView'

interface Copy { headline: string; body: string }

interface Props {
  /** 哪个域的对话：工作区（研究助理）或编辑台（造流助理）；端点前缀由它定 */
  scope: Scope
  /** 换对话时父组件用 key 重建本组件，所以这里的状态天然按对话隔离 */
  chatId: string | null
  current: ChatMeta | null
  /** 有看板可收的页面才给这两个 */
  boardOpen?: boolean
  onToggleBoard?: () => void
  onNew: () => void
  /** 一轮结束：助理可能运行了命令、改了需求或 run，看板要重读 */
  onTurnDone: () => void
  drawer: ReactNode
  /** 对话还没开口时的两句引导 */
  intro: { lede: string; body: string }
  /** 输入框里的提示 */
  placeholder: string
  /** 还没有对话时的欢迎屏文案 */
  welcome: Copy
}

interface LiveTurn {
  n: number
  message: string
  trace: TraceItem[]
  outcome: TurnOutcome | null
}

type Kept = Record<number, { trace: TraceItem[]; outcome: TurnOutcome }>

export function ChatView({ scope, chatId, current, boardOpen, onToggleBoard, onNew, onTurnDone, drawer,
                           intro, placeholder, welcome }: Props) {
  const doc = useResource(() => (chatId ? api.chat(scope, chatId) : Promise.resolve(null)), [chatId])
  const [live, setLive] = useState<LiveTurn | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)
  // 本次打开页面期间跑过的轮次，按轮号留着它做过什么；刷新后只剩落盘的问答
  const [kept, setKept] = useState<Kept>({})
  const bottom = useRef<HTMLDivElement>(null)

  const turns = useMemo<Turn[]>(() => {
    const settled: Turn[] = (doc.data?.history ?? []).map((t) => ({
      n: t.turn, origin: t.origin, message: t.message, reply: t.reply,
      trace: kept[t.turn]?.trace ?? [], outcome: kept[t.turn]?.outcome ?? null, live: false,
    }))
    if (live) {
      settled.push({ n: live.n, origin: '人', message: live.message, reply: null, trace: live.trace,
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
    let currentTurn: LiveTurn = { n, message: text, trace: [], outcome: null }
    setLive(currentTurn)
    try {
      await streamTurn(scope, chatId, text, (event: ChatEvent) => {
        const done = event.kind === 'done' || event.kind === 'error' ? outcome(event) : currentTurn.outcome
        currentTurn = { ...currentTurn, trace: reduceTrace(currentTurn.trace, event), outcome: done }
        setLive(currentTurn)
      })
    } catch (exc) {
      setSendError(exc instanceof Error ? exc.message : String(exc))
    }
    // 流断了也没有 done：按"没走完"记，不假装成功
    const final = currentTurn.outcome ?? { costUsd: null, durationS: 0, failed: true }
    setKept((prev) => ({ ...prev, [n]: { trace: currentTurn.trace, outcome: final } }))
    setLive(null)
    await doc.reload()
    onTurnDone()
  }, [chatId, doc, onTurnDone, scope])

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-background">
      <header className="flex h-11 shrink-0 items-center gap-2 px-3">
        {drawer}
        <span className="min-w-0 flex-1 truncate text-[0.875rem] text-muted-foreground">
          {current?.title ?? (chatId ? '新对话' : '')}
        </span>
        {current && current.cost_usd > 0 && (
          <span className="t-label whitespace-nowrap">{usd(current.cost_usd)}</span>
        )}
        {onToggleBoard && (
          <Button variant="ghost" size="icon-sm" onClick={onToggleBoard} aria-label={boardOpen ? '收起看板' : '展开看板'}>
            {boardOpen ? <PanelRightClose /> : <PanelRightOpen />}
          </Button>
        )}
      </header>

      <div className="relative min-h-0 flex-1 overflow-y-auto">
        {!chatId && <Welcome copy={welcome} onNew={onNew} />}
        {chatId && (
          <div className="mx-auto max-w-[44rem] px-6 py-8">
            {doc.loading && !doc.data && <Skeleton lines={4} />}
            {doc.error && <ErrorNote text={doc.error} />}
            {doc.data && turns.length === 0 && (
              <div className="space-y-3 py-6">
                <p className="t-lede">{intro.lede}</p>
                <p className="t-body text-muted-foreground">{intro.body}</p>
              </div>
            )}
            <div className="space-y-10">
              {turns.map((turn) => <TurnView key={turn.n} turn={turn} />)}
            </div>
            {sendError && <ErrorNote text={sendError} className="mt-4" />}
            <div ref={bottom} />
          </div>
        )}
      </div>

      <Composer disabled={!chatId} busy={live !== null} placeholder={placeholder} onSend={(text) => void send(text)} />
    </div>
  )
}

/** 还没有对话：一句话说清这一边的助理管什么；背景是安静的波纹，动的是线不是字。 */
function Welcome({ copy, onNew }: { copy: Copy; onNew: () => void }) {
  const still = useReducedMotion()  // 系统要求减少动效：没有波纹，标题直接出现
  return (
    <div className="relative h-full min-h-[24rem]">
      {/* Waves 自带一个跟随光标的小圆点，这里不需要，藏掉 */}
      {!still && (
        <Waves lineColor="oklch(0.9 0.02 80)" backgroundColor="transparent" waveSpeedX={0.01} waveSpeedY={0.004}
               waveAmpX={28} waveAmpY={14} xGap={14} yGap={36} className="[&>div]:hidden" />
      )}
      <div className="relative mx-auto flex h-full max-w-[36rem] flex-col justify-center px-6">
        {still
          ? <h2 className="text-[1.75rem] leading-[1.25] font-semibold tracking-tight text-balance">{copy.headline}</h2>
          : <BlurText text={copy.headline} delay={50} animateBy="words"
                      direction="top" className="text-[1.75rem] leading-[1.25] font-semibold tracking-tight text-balance" />}
        <p className="t-body mt-5 text-muted-foreground">{copy.body}</p>
        <div className="mt-8">
          <Button size="lg" onClick={onNew}>开始对话</Button>
        </div>
      </div>
    </div>
  )
}
