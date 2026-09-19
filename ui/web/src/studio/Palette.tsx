// 画布顶上那一条：七个阶段、三种断点、库。拖进画布落在哪就插在哪；点一下加到末尾（键盘也走得通）。
// 库是一个弹层：点一条载入画布（名字照旧，存回去要勾「覆盖同名」）。
import { Books, CaretDown, HandPalm, Signature, Stamp } from '@phosphor-icons/react'
import { createElement, type ReactNode, useState } from 'react'

import type { Workflow } from '@/api/types'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { type Seed, SEED_MIME } from './model'

const STOPS: { note: string; icon: typeof HandPalm; label: string }[] = [
  { note: '发布', icon: Stamp, label: '发布' }, { note: '验收', icon: Signature, label: '验收' }, { note: '', icon: HandPalm, label: '断点' },
]

const CHIP = 'flex h-8 shrink-0 items-center gap-1.5 rounded-lg border px-2 text-[0.8125rem] transition-colors focus-visible:outline-2 focus-visible:outline-ring'

export function Palette({ stages, workflows, onAdd, onLoad }: {
  stages: string[]; workflows: Workflow[]; onAdd: (seed: Seed) => void; onLoad: (wf: Workflow) => void
}) {
  const chip = (seed: Seed, icon: typeof HandPalm, label: string, tone: 'stage' | 'stop') => (
    <li key={label}>
      <button type="button" draggable onClick={() => onAdd(seed)}
              onDragStart={(e) => { e.dataTransfer.setData(SEED_MIME, JSON.stringify(seed)); e.dataTransfer.effectAllowed = 'copy' }}
              className={cn(CHIP, 'cursor-grab active:cursor-grabbing',
                            tone === 'stage' ? 'bg-card hover:border-primary/50 hover:bg-accent/40' : 'border-wait/50 bg-wait-soft text-wait hover:border-wait')}>
        {createElement(icon, { weight: 'duotone', 'aria-hidden': true, className: cn('size-4', tone === 'stage' && 'text-primary') })}
        <span className={cn(tone === 'stage' && 'font-serif font-semibold')}>{label}</span>
      </button>
    </li>
  )
  return (
    <div className="flex items-center gap-3 overflow-x-auto [scrollbar-width:none]">
      <Group label="阶段">{stages.map((stage) => chip({ kind: 'stage', stage }, stageIcon(stage), stage, 'stage'))}</Group>
      <span aria-hidden className="h-5 w-px shrink-0 bg-border" />
      <Group label="断点">{STOPS.map((s) => chip({ kind: 'stop', note: s.note }, s.icon, s.label, 'stop'))}</Group>
      <span aria-hidden className="h-5 w-px shrink-0 bg-border" />
      <Library workflows={workflows} onLoad={onLoad} />
    </div>
  )
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return <ul aria-label={label} className="flex shrink-0 gap-1.5">{children}</ul>
}

function Library({ workflows, onLoad }: { workflows: Workflow[]; onLoad: (wf: Workflow) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={cn(CHIP, 'bg-card hover:border-primary/50 hover:bg-accent/40')}>
          <Books weight="duotone" aria-hidden className="size-4" />库 {workflows.length}
          <CaretDown className={cn('size-3 text-muted-foreground transition-transform', open && 'rotate-180')} aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[16rem] p-1.5">
        {workflows.length === 0 && <p className="px-2 py-1.5 text-[0.8125rem] text-muted-foreground">空</p>}
        <ul className="max-h-[22rem] space-y-0.5 overflow-y-auto">
          {workflows.map((wf) => (
            <li key={wf.name}>
              <button type="button" onClick={() => { onLoad(wf); setOpen(false) }} title={wf.problems[0] ?? wf.summary}
                      className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-accent/60 focus-visible:outline-2 focus-visible:outline-ring">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.875rem] font-medium">{wf.title}</span>
                  <span className="block truncate font-mono text-[0.6875rem] text-muted-foreground">{wf.name} · {wf.stages.length} 项</span>
                </span>
                {wf.problems.length > 0 && <span role="img" aria-label="有问题" className="size-2 shrink-0 rounded-full bg-bad" />}
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
