// 板里的对话视图（工作区页右边那块板、编辑台同一块）：一行头（抽屉、标题、花费、收起）、正文、输入框。
// 还没有对话时是欢迎屏，输入框就是门：第一句先开一段再发，这一轮从按下回车起就在屏上（useConversation）。
import { X } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'

import type { Scope } from '@/api/client'
import { ASSETS } from '@/assets'
import type { Backend, ChatMeta, Tuning } from '@/api/types'
import BlurText from '@/components/BlurText'
import { ErrorNote } from '@/components/bits'
import { Scene } from '@/components/Scene'
import { Button } from '@/components/ui/button'
import { usd } from '@/lib/format'

import { Composer } from './Composer'
import { Transcript } from './Transcript'
import { useConversation } from './useConversation'

interface Copy { headline: string; body: string }

interface Props {
  /** 哪个域的对话：项目（研究助理）或编辑台（流程助理）；端点前缀由它定 */
  scope: Scope
  chatId: string | null
  current: ChatMeta | null
  /** 还没有对话时开一段（带上门里选的哪家、模型与思考深度） */
  create: (tuning: Tuning, backend: string | null) => Promise<ChatMeta>
  /** 每家 agent 的旋钮清单与新对话用的值；这段对话用哪家的就摆哪家的，还没开对话时摆门里选的那家 */
  backends: Backend[] | null
  /** 一轮结束：助理可能运行了命令、改了需求或 run，看板要重读 */
  onTurnDone: () => void
  drawer: ReactNode
  /** 板里的对话：右上角一枚收起 */
  onClose?: () => void
  /** 对话还没开口时的两句引导 */
  intro: { lede: string; body: string }
  /** 还没有对话时的欢迎屏文案 */
  welcome: Copy
}

export function ChatView({ scope, chatId, current, create, backends, onTurnDone, drawer, onClose, intro, welcome }: Props) {
  const conv = useConversation({ scope, chatId, current, backends, create, onTurnDone })
  const t = conv.tuning
  const inChat = chatId !== null || conv.turns.length > 0
  return (
    <div className="relative flex h-full min-w-0 flex-1 flex-col bg-background">
      {/* 没有对话：一张风景铺在整列底下、左边压纸色给字站；有了对话：淡彩的云压到只剩氛围 */}
      <Scene picture={inChat ? ASSETS.chat : ASSETS.welcome} veil={inChat ? 'mist' : 'side'} />
      <header className="relative flex h-12 shrink-0 items-center gap-2 px-3">
        {drawer}
        <span className="min-w-0 flex-1 truncate text-[0.875rem] text-muted-foreground">
          {current?.title ?? (inChat ? '新对话' : '')}
        </span>
        {current && current.cost_usd > 0 && (
          <span className="t-label whitespace-nowrap">{usd(current.cost_usd)}</span>
        )}
        {onClose && (
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="收起对话"><X /></Button>
        )}
      </header>
      {inChat
        ? <Transcript doc={conv.doc} turns={conv.turns} thinking={t.thinking} intro={intro} error={conv.error} />
        : <Welcome copy={welcome} error={conv.error} />}
      <Composer busy={conv.busy} thinking={t.thinking} knobs={t.knobs} tuning={t.tuning} onTune={t.onTune}
                who={chatId || !backends ? undefined : { options: backends, value: t.backendName ?? '', onChange: t.choose }}
                onSend={(text) => void conv.send(text)} />
    </div>
  )
}

/** 还没有对话：一句话说清这一边的助理管什么；门就是下面的输入框，不另设按钮。开不出来的一句写在底下。 */
function Welcome({ copy, error }: { copy: Copy; error: string | null }) {
  const still = useReducedMotion()  // 系统要求减少动效：标题直接出现
  return (
    <div className="relative min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex h-full min-h-[24rem] max-w-[36rem] flex-col justify-center px-6">
        {still
          ? <h2 className="font-serif text-[1.75rem] leading-[1.25] font-semibold tracking-tight text-balance">{copy.headline}</h2>
          : <BlurText text={copy.headline} delay={50} animateBy="words" direction="top"
                      className="font-serif text-[1.75rem] leading-[1.25] font-semibold tracking-tight text-balance" />}
        <p className="t-body mt-5 text-muted-foreground">{copy.body}</p>
        {error && <ErrorNote text={error} className="mt-6" />}
      </div>
    </div>
  )
}
