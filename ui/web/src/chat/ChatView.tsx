import { SidebarSimple } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api, type Scope } from '@/api/client'
import { ASSETS } from '@/assets'
import { streamTurn } from '@/api/sse'
import type { Backend, ChatEvent, ChatMeta, Tuning } from '@/api/types'
import BlurText from '@/components/BlurText'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Scene } from '@/components/Scene'
import { Button } from '@/components/ui/button'
import { usd } from '@/lib/format'
import { type Pick, shownValue, storedTuning, thinkingWord } from '@/lib/tuning'
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
  /** 还没有对话时在输入框里打的第一句：对话一建好就发出去 */
  autoSend: string | null
  onAutoSent: () => void
  /** 没有对话时按下回车：开一段（带上门里选的模型与思考深度），第一句话由 autoSend 带回来 */
  onStart: (text: string, tuning: Tuning) => void
  /** 后端的两个旋钮清单；还没拿到就先不摆 */
  knobs: Backend | null
  /** 一轮结束：助理可能运行了命令、改了需求或 run，看板要重读 */
  onTurnDone: () => void
  drawer: ReactNode
  /** 对话还没开口时的两句引导 */
  intro: { lede: string; body: string }
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

export function ChatView({ scope, chatId, current, boardOpen, onToggleBoard, autoSend, onAutoSent, onStart, onTurnDone,
                           knobs, drawer, intro, welcome }: Props) {
  const doc = useResource(() => (chatId ? api.chat(scope, chatId) : Promise.resolve(null)), [chatId])
  const [live, setLive] = useState<LiveTurn | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)
  // 输入框上这次改过的旋钮；没碰过就沿用对话上记的，随每条消息发出去（外层 #86）
  const [pick, setPick] = useState<Pick>({})
  const tuning = storedTuning(pick, current)
  // 助理想着时那个词：按实际用的深度（记着的，或后端缺省）在清单里的位置
  const thinking = thinkingWord(shownValue(tuning.effort, knobs?.effort ?? null), knobs?.efforts ?? [])
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
      await streamTurn(scope, chatId, text, tuning, (event: ChatEvent) => {
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
  }, [chatId, doc, onTurnDone, scope, tuning])

  // 门里带进来的第一句：对话建好、本视图挂上来，就替它发出去。只发一次——send 的身份会随取数变，靠 ref 拦住重放
  const opened = useRef(false)
  useEffect(() => {
    if (!autoSend || !chatId || opened.current) return
    opened.current = true
    queueMicrotask(() => { onAutoSent(); void send(autoSend) })
  }, [autoSend, chatId, onAutoSent, send])

  return (
    <div className="relative flex h-full min-w-0 flex-1 flex-col bg-background">
      {/* 没有对话：一张风景铺在整列底下、左边压纸色给字站；有了对话：淡彩的云压到只剩氛围 */}
      <Scene picture={chatId ? ASSETS.chat : ASSETS.welcome} veil={chatId ? 'mist' : 'side'} />
      <header className="relative flex h-12 shrink-0 items-center gap-2 px-3">
        {drawer}
        <span className="min-w-0 flex-1 truncate text-[0.875rem] text-muted-foreground">
          {current?.title ?? (chatId ? '新对话' : '')}
        </span>
        {current && current.cost_usd > 0 && (
          <span className="t-label whitespace-nowrap">{usd(current.cost_usd)}</span>
        )}
        {onToggleBoard && (
          <Button variant="ghost" size="icon-sm" onClick={onToggleBoard} aria-label={boardOpen ? '收起看板' : '展开看板'}>
            <SidebarSimple weight={boardOpen ? 'fill' : 'regular'} className="-scale-x-100" />
          </Button>
        )}
      </header>

      <div className="relative min-h-0 flex-1 overflow-y-auto">
        {!chatId && <Welcome copy={welcome} />}
        {chatId && (
          <div className="mx-auto max-w-[44rem] px-6 pt-8">
            {doc.loading && !doc.data && <Skeleton lines={4} />}
            {doc.error && <ErrorNote text={doc.error} />}
            {doc.data && turns.length === 0 && (
              <div className="space-y-3 py-6">
                <p className="t-lede">{intro.lede}</p>
                <p className="t-body text-muted-foreground">{intro.body}</p>
              </div>
            )}
            <div className="space-y-10">
              {turns.map((turn) => <TurnView key={turn.n} turn={turn} thinking={thinking} />)}
            </div>
            {sendError && <ErrorNote text={sendError} className="mt-4" />}
            {/* 滚动锚点自带一段空档：最后一句和输入框之间要有呼吸，滚到底时这段也在视野里 */}
            <div ref={bottom} className="h-20" />
          </div>
        )}
      </div>

      <Composer busy={live !== null || autoSend !== null} thinking={thinking} knobs={knobs} tuning={tuning}
                onTune={(next) => setPick(next)}
                onSend={(text) => (chatId ? void send(text) : onStart(text, tuning))} />
    </div>
  )
}

/** 还没有对话：一句话说清这一边的助理管什么；门就是下面的输入框，不另设按钮。 */
function Welcome({ copy }: { copy: Copy }) {
  const still = useReducedMotion()  // 系统要求减少动效：标题直接出现
  return (
    <div className="relative mx-auto flex h-full min-h-[24rem] max-w-[36rem] flex-col justify-center px-6">
      {still
        ? <h2 className="font-serif text-[1.75rem] leading-[1.25] font-semibold tracking-tight text-balance">{copy.headline}</h2>
        : <BlurText text={copy.headline} delay={50} animateBy="words" direction="top"
                    className="font-serif text-[1.75rem] leading-[1.25] font-semibold tracking-tight text-balance" />}
      <p className="t-body mt-5 text-muted-foreground">{copy.body}</p>
    </div>
  )
}
