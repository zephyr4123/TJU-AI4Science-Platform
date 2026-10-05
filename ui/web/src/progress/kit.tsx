// 进度面板共用的图元（外层 #242）。每个能力一块定制面板，**只共用这几样**：方块（一步）、连线、六边形（一篇文献）、计时（components/Clock）、
// 悬停的那张小签。版式、用哪几样、中间那张大图，各个能力的面板自己画（SearchPanel / ReadPanel）。
// 状态色照 docs/DESIGN.md：运行中是靛、一圈光慢慢呼吸；完成是素的；失败是红；没到是虚线框。动效在 index.css
// （breathe / wire-flow / cell-in / glimmer），减少动效时全局停住。
import { CaretRight, X } from '@phosphor-icons/react'
import { type CSSProperties, type ReactNode } from 'react'

import { Clock } from '@/components/Clock'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

import type { Phase } from './events'
import { HEX_CLIP } from './hex'

const STATION: Record<Phase, string> = {
  pending: 'border-dashed border-foreground/15 bg-card/40 text-muted-foreground/70',
  skipped: 'border-dashed border-foreground/10 bg-transparent text-muted-foreground/50',
  running: 'border-primary/45 bg-card animate-breathe',
  done: 'border-foreground/10 bg-card',
  failed: 'border-bad/45 bg-bad-soft',
}

/** 一步一个方块：左上一个两字的名，右上运行中走着的表（失败是一枚叉），底下是这一步自己的数或图 */
export function Station({ label, phase, since, children, className, title }: {
  label: string; phase: Phase; since?: string | null; children?: ReactNode; className?: string
  /** 悬停的一句（这一步在做什么） */
  title?: string
}) {
  return (
    <div data-phase={phase} title={title}
         className={cn('relative flex min-w-0 flex-col gap-1 rounded-xl border px-3 pt-2 pb-2.5 transition-[background-color,border-color] duration-300', STATION[phase], className)}>
      <div className="flex items-center gap-2 text-[0.75rem] leading-none">
        <span className={cn('font-medium', phase === 'running' ? 'text-primary' : phase === 'failed' ? 'text-bad' : 'text-muted-foreground')}>{label}</span>
        {phase === 'running' && since && <Clock since={since} className="ml-auto text-[0.6875rem] text-primary/80" />}
        {phase === 'failed' && <X weight="bold" className="ml-auto size-3 text-bad" aria-label="失败" />}
      </div>
      {children}
    </div>
  )
}

/** 方块里的那个数：大的是主数，`of` 是分母（灰小字） */
export function Figure({ value, of, className }: { value: number | null; of?: number | null; className?: string }) {
  return (
    <div className={cn('flex items-baseline gap-0.5 leading-none', className)}>
      <span className="text-[1.0625rem] font-semibold tabular-nums">{value ?? '—'}</span>
      {of != null && <span className="text-[0.75rem] text-muted-foreground tabular-nums">/{of}</span>}
    </div>
  )
}

/** 两步之间的连线，带一个小箭头；下游那一步在跑时虚线顺着方向流 */
export function Wire({ active, vertical = false, className }: { active: boolean; vertical?: boolean; className?: string }) {
  const flow: CSSProperties | undefined = active ? {
    backgroundImage: `repeating-linear-gradient(${vertical ? '180deg' : '90deg'}, var(--primary) 0 4px, transparent 4px 8px)`,
    backgroundSize: vertical ? '2px 8px' : '8px 2px',
  } : undefined
  return (
    <div aria-hidden className={cn('flex shrink-0 items-center', vertical ? 'flex-col' : '', className)}>
      <div style={flow} className={cn(vertical ? 'w-0.5 flex-1' : 'h-0.5 flex-1', !active && 'bg-foreground/12',
                                       active && (vertical ? 'animate-wire-flow-y' : 'animate-wire-flow'))} />
      <svg viewBox="0 0 6 8" className={cn('shrink-0', vertical ? 'h-1.5 w-2 rotate-90' : 'h-2 w-1.5', active ? 'fill-primary' : 'fill-foreground/25')}>
        <path d="M0 0 6 4 0 8z" />
      </svg>
    </div>
  )
}

/** 一篇文献：尖顶六边形（HTML 元素，精读那几堆用；检索的蜂巢是 SVG，同一种形状）。`size` 是宽，高按比例 */
export function Hex({ size, className, style, children }: { size: number; className?: string; style?: CSSProperties; children?: ReactNode }) {
  return (
    <span className={cn('relative inline-block shrink-0', className)}
          style={{ width: size, height: size * 1.1547, clipPath: HEX_CLIP, ...style }}>
      {children}
    </span>
  )
}

/** 悬停在一格上时的小签：题目两行以内，底下一行灰字说它的状态。位置是相对面板的像素（noteAnchor） */
export function HoverNote({ at, title, note }: { at: { x: number; y: number } | null; title: string; note: string }) {
  if (!at) return null
  return (
    <div role="tooltip" style={{ left: at.x, top: at.y }}
         className="pointer-events-none absolute z-10 w-max max-w-[16rem] -translate-x-1/2 -translate-y-[calc(100%+10px)] rounded-lg bg-foreground px-2.5 py-1.5 text-background shadow-lg">
      <p className="line-clamp-2 text-[0.75rem] leading-snug">{title}</p>
      <p className="mt-0.5 text-[0.6875rem] opacity-70">{note}</p>
    </div>
  )
}

/** 收着的「详情」：每行一个名、一句话；面板上只有图，数都在这里 */
export function Details({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <Collapsible className="group/details">
      <CollapsibleTrigger className="inline-flex items-center gap-1 rounded text-[0.75rem] text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
        <CaretRight weight="bold" className="size-3 transition-transform duration-200 group-data-[state=open]/details:rotate-90" />详情
      </CollapsibleTrigger>
      <CollapsibleContent>
        <dl className="mt-2 grid grid-cols-[4.5rem_1fr] gap-x-3 gap-y-1 text-[0.8125rem]">
          {rows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted-foreground">{label}</dt><dd className="min-w-0 break-words">{value}</dd>
            </div>
          ))}
        </dl>
      </CollapsibleContent>
    </Collapsible>
  )
}
