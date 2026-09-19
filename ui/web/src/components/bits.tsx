// 页面零件：状态点、空态、错误条、问题清单、骨架、键按过之后那一行。故意不做成"设计系统"，够用为止。

import { Check, WarningCircle } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type Tone = 'neutral' | 'ok' | 'warn' | 'bad' | 'primary'

const DOT: Record<Tone, string> = {
  neutral: 'bg-muted-foreground/50', ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', primary: 'bg-primary',
}

export function Dot({ tone, pulse = false, className }: { tone: Tone; pulse?: boolean; className?: string }) {
  return <span className={cn('inline-block size-2 shrink-0 rounded-full', DOT[tone], pulse && 'animate-pulse', className)} />
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="space-y-2 py-6">
      <p className="t-lede">{title}</p>
      {hint && <p className="t-body text-muted-foreground">{hint}</p>}
      {action}
    </div>
  )
}

export function ErrorNote({ text, className }: { text: string; className?: string }) {
  return (
    <div role="alert" className={cn('flex items-start gap-2 rounded-md bg-bad-soft px-3 py-2 text-sm text-bad', className)}>
      <WarningCircle className="mt-0.5 size-4 shrink-0" />
      <span className="whitespace-pre-wrap break-words">{text}</span>
    </div>
  )
}

/** 问题清单：一行一条、原样给人看（流的检查、预检）。 */
export function Problems({ items, tone = 'bad' }: { items: string[]; tone?: 'bad' | 'warn' }) {
  if (items.length === 0) return null
  return (
    <ul className={cn('space-y-1 rounded-md px-3 py-2 text-sm', tone === 'bad' ? 'bg-bad-soft text-bad' : 'bg-warn-soft text-warn')}>
      {items.map((item, i) => <li key={i} className="whitespace-pre-wrap break-words leading-relaxed">{item}</li>)}
    </ul>
  )
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-3" aria-busy="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-muted" style={{ width: `${90 - (i % 3) * 20}%` }} />
      ))}
    </div>
  )
}

/** 键按过之后的陈述句：绿底一行。 */
export function DoneBlock({ title, detail }: { title: string; detail: ReactNode }) {
  return (
    <section className="flex items-start gap-3 rounded-xl bg-ok-soft p-5 text-ok">
      <Check className="mt-1 size-5 shrink-0" aria-hidden />
      <div>
        <div className="text-[0.9375rem] font-semibold">{title}</div>
        <div className="mt-0.5 text-sm leading-relaxed opacity-90">{detail}</div>
      </div>
    </section>
  )
}
