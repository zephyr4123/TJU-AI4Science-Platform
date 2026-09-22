// 一段对话的正文：一轮一轮往下排，最后一句和输入框之间留一段呼吸；新一轮或新事件来了滚到底。
// 板里的对话视图与项目页整屏的对话共用。
import { useEffect, useRef } from 'react'

import type { ChatDoc } from '@/api/types'
import { ErrorNote, Skeleton } from '@/components/bits'
import type { Resource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { type Turn, TurnView } from './TurnView'

export function Transcript({ doc, turns, thinking, intro, error, className }: {
  doc: Resource<ChatDoc | null>
  turns: Turn[]
  thinking: string
  /** 对话还没开口时的两句引导 */
  intro: { lede: string; body: string }
  error: string | null
  className?: string
}) {
  const bottom = useRef<HTMLDivElement>(null)
  const last = turns.at(-1)
  const traceLength = last?.live ? last.trace.length : 0
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [turns.length, traceLength])
  return (
    <div className={cn('relative min-h-0 flex-1 overflow-y-auto', className)}>
      <div className="mx-auto max-w-[44rem] px-6 pt-8">
        {doc.loading && !doc.data && turns.length === 0 && <Skeleton lines={4} />}
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
        {error && <ErrorNote text={error} className="mt-4" />}
        {/* 滚动锚点自带一段空档：最后一句和输入框之间要有呼吸，滚到底时这段也在视野里 */}
        <div ref={bottom} className="h-20" />
      </div>
    </div>
  )
}
