// 一页纸的零件：结论句、大数字、可信度勾、细节折叠、空态、错误条、骨架。故意不做成"设计系统"，够用为止。

import { AlertCircle, Check, ChevronDown, Minus, X } from 'lucide-react'
import type { ReactNode } from 'react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

export type Tone = 'neutral' | 'ok' | 'warn' | 'bad' | 'primary'

const TEXT: Record<Tone, string> = {
  neutral: 'text-foreground', ok: 'text-ok', warn: 'text-warn', bad: 'text-bad', primary: 'text-primary',
}
const DOT: Record<Tone, string> = {
  neutral: 'bg-muted-foreground/50', ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', primary: 'bg-primary',
}

/** 一页纸的第一句：结论。 */
export function Lede({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <p className={cn('t-lede', tone !== 'neutral' && TEXT[tone])}>{children}</p>
}

export function Dot({ tone, pulse = false, className }: { tone: Tone; pulse?: boolean; className?: string }) {
  return <span className={cn('inline-block size-2 shrink-0 rounded-full', DOT[tone], pulse && 'animate-pulse', className)} />
}

/** 大数字：四位有效数字够读（精确值在细节层）；null 显示 `missing`。
 *  不做数字滚动：科研数字在到位前的每一帧都是错的，淡入就够。 */
export function BigNumber({ label, value, unit, tone = 'neutral', missing = '—' }: {
  label: string; value: number | null; unit?: string; tone?: Tone; missing?: string
}) {
  const shown = value === null ? null : Number(value.toPrecision(4))
  return (
    <div className="min-w-0 animate-in fade-in duration-300">
      <div className={cn('t-big flex items-baseline gap-1 truncate', TEXT[tone])}>
        {shown === null ? <span className="text-muted-foreground">{missing}</span> : <span>{shown}</span>}
        {unit && shown !== null && <span className="text-base font-normal text-muted-foreground">{unit}</span>}
      </div>
      <div className="t-label mt-1.5">{label}</div>
    </div>
  )
}

/** 三个大数字并排；不到三个也用它。 */
export function Numbers({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-3 gap-4">{children}</div>
}

export function Paragraph({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-[0.9375rem] font-semibold tracking-tight">{title}</h3>
      <div className="t-body text-foreground/90">{children}</div>
    </section>
  )
}

/** 可信度勾：ok 打勾、false 打叉、null 是「还没做」。 */
export function CheckRow({ ok, text }: { ok: boolean | null; text: string }) {
  const Icon = ok === true ? Check : ok === false ? X : Minus
  const tone = ok === true ? 'text-ok' : ok === false ? 'text-bad' : 'text-muted-foreground'
  return (
    <li className="flex items-start gap-2.5 text-[0.9375rem] leading-relaxed">
      <Icon className={cn('mt-1 size-4 shrink-0', tone)} aria-hidden />
      <span className={ok === null ? 'text-muted-foreground' : undefined}>{text}</span>
    </li>
  )
}

/** 细节折叠：工程师翻得到，研究者不必看。 */
export function Details({ title, children, defaultOpen = false }: {
  title: string; children: ReactNode; defaultOpen?: boolean
}) {
  return (
    <Collapsible defaultOpen={defaultOpen} className="border-t pt-3">
      <CollapsibleTrigger className="group flex w-full items-center justify-between py-1 text-left text-[0.9375rem] font-medium text-muted-foreground hover:text-foreground">
        {title}
        <ChevronDown className="size-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-3">{children}</CollapsibleContent>
    </Collapsible>
  )
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
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span className="whitespace-pre-wrap break-words">{text}</span>
    </div>
  )
}

/** 问题清单：一行一条、原样给人看（发布前检查、预检）。 */
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

/** 键所在的区块：主色浅底，署名 + 键，说明一句。 */
export function KeyBlock({ title, hint, children }: { title: string; hint: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl bg-accent/70 p-5">
      <h3 className="text-[0.9375rem] font-semibold tracking-tight text-accent-foreground">{title}</h3>
      <div className="t-body mt-1 text-accent-foreground/85">{hint}</div>
      <div className="mt-4">{children}</div>
    </section>
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
