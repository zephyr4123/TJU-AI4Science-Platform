// 各看板共用的小件：状态点、键值行、空态、错误条、骨架。故意不做成"设计系统"，够用为止。

import { AlertCircle } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type Tone = 'neutral' | 'ok' | 'warn' | 'bad' | 'primary'

const DOT: Record<Tone, string> = {
  neutral: 'bg-muted-foreground/50',
  ok: 'bg-ok',
  warn: 'bg-warn',
  bad: 'bg-bad',
  primary: 'bg-primary',
}

const PILL: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground',
  ok: 'bg-ok-soft text-ok',
  warn: 'bg-warn-soft text-warn',
  bad: 'bg-bad-soft text-bad',
  primary: 'bg-accent text-accent-foreground',
}

export function Dot({ tone, pulse = false, className }: { tone: Tone; pulse?: boolean;
                                                           className?: string }) {
  return (
    <span className={cn('inline-block size-2 shrink-0 rounded-full', DOT[tone],
                        pulse && 'animate-pulse', className)} />
  )
}

export function Pill({ tone, children, className }: { tone: Tone; children: ReactNode;
                                                       className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs',
                        'font-medium leading-4', PILL[tone], className)}>
      {children}
    </span>
  )
}

/** 一行"标签 / 值"，看板里的元数据都用它；值默认等宽数字。 */
export function Row({ label, children, mono = true }: { label: string; children: ReactNode;
                                                          mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1 text-sm">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className={cn('min-w-0 truncate text-right', mono && 'font-mono tabular text-[13px]')}>
        {children}
      </dd>
    </div>
  )
}

export function Section({ title, aside, children, className }: {
  title: string; aside?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[13px] font-semibold tracking-tight text-foreground">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  )
}

export function Empty({ title, hint, action }: { title: string; hint?: string;
                                                  action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed p-4">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">{hint}</p>}
      {action}
    </div>
  )
}

export function ErrorNote({ text, className }: { text: string; className?: string }) {
  return (
    <div role="alert"
         className={cn('flex items-start gap-2 rounded-md bg-bad-soft px-3 py-2 text-sm text-bad',
                       className)}>
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span className="whitespace-pre-wrap break-words">{text}</span>
    </div>
  )
}

/** 问题清单：预检、发布前检查、流通不通——都是"一行一条、原样给人看"的。 */
export function Problems({ items, tone = 'bad' }: { items: string[]; tone?: Tone }) {
  if (items.length === 0) return null
  return (
    <ul className={cn('space-y-1 rounded-md px-3 py-2 text-sm',
                      tone === 'bad' ? 'bg-bad-soft text-bad' : 'bg-warn-soft text-warn')}>
      {items.map((item, i) => (
        <li key={i} className="whitespace-pre-wrap break-words leading-relaxed">{item}</li>
      ))}
    </ul>
  )
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2" aria-busy="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-3.5 animate-pulse rounded bg-muted"
             style={{ width: `${88 - (i % 3) * 18}%` }} />
      ))}
    </div>
  )
}
