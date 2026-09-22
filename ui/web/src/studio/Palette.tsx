// 画布左边一根梯子：七个研究阶段按顺序竖排成方块（顺序本身就是信息），底下一块断点（拖进去写一句要人确认什么）。
// 拖进画布落在哪就插在哪；点一下加到末尾（键盘也走得通）。流程库另在右上角：一个弹层，点一条载入画布（存回去就是覆盖它）。
import { Books, CaretDown, Signature, Trash } from '@phosphor-icons/react'
import { createElement, useState } from 'react'

import { api } from '@/api/client'
import type { Workflow } from '@/api/types'
import HoldButton from '@/components/reactbits/HoldButton'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { type Seed, SEED_MIME } from './model'

export function Ladder({ stages, onAdd }: { stages: string[]; onAdd: (seed: Seed) => void }) {
  const tile = (seed: Seed, icon: typeof Signature, label: string, tone: 'stage' | 'stop') => (
    <li key={label}>
      <button type="button" draggable onClick={() => onAdd(seed)} title={label}
              onDragStart={(e) => { e.dataTransfer.setData(SEED_MIME, JSON.stringify(seed)); e.dataTransfer.effectAllowed = 'copy' }}
              className={cn('flex size-[3.25rem] cursor-grab flex-col items-center justify-center gap-0.5 rounded-xl border transition-[transform,border-color,background-color] active:cursor-grabbing hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-ring',
                            tone === 'stage'
                              ? 'border-transparent bg-transparent text-foreground hover:border-primary/40 hover:bg-card'
                              : 'border-wait/40 bg-wait-soft/70 text-wait hover:border-wait')}>
        {createElement(icon, { weight: 'duotone', 'aria-hidden': true, className: cn('size-[1.375rem]', tone === 'stage' && 'text-primary') })}
        <span className={cn('text-[0.6875rem] leading-none', tone === 'stage' && 'font-serif font-semibold')}>{label}</span>
      </button>
    </li>
  )
  return (
    <div className="rounded-2xl border bg-card/85 p-1.5 shadow-sm backdrop-blur-sm">
      <ol aria-label="阶段" className="space-y-0.5">{stages.map((stage) => tile({ kind: 'stage', stage }, stageIcon(stage), stage, 'stage'))}</ol>
      <span aria-hidden className="my-1.5 block h-px bg-border" />
      <ul aria-label="断点">{tile({ kind: 'stop', note: '' }, Signature, '断点', 'stop')}</ul>
    </div>
  )
}

export function Library({ workflows, onLoad, onRemoved }: {
  workflows: Workflow[]; onLoad: (wf: Workflow) => void
  /** 删了库里的一条之后（清单要重读）；出厂的两条没有删 */
  onRemoved: () => void
}) {
  const [open, setOpen] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const remove = (name: string) => {
    setFailed(null)
    api.removeWorkflow(name).then(onRemoved).catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button"
                className="flex h-8 items-center gap-1.5 rounded-full border bg-card/85 px-3 text-[0.8125rem] shadow-sm backdrop-blur-sm transition-colors hover:border-primary/50 focus-visible:outline-2 focus-visible:outline-ring">
          <Books weight="duotone" aria-hidden className="size-4 text-primary" />流程库
          <CaretDown className={cn('size-3 text-muted-foreground transition-transform', open && 'rotate-180')} aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[17rem] p-1.5">
        {workflows.length === 0 && <p className="px-2 py-1.5 text-[0.8125rem] text-muted-foreground">空</p>}
        {failed && <p className="px-2 py-1.5 text-[0.75rem] text-bad">{failed}</p>}
        <ul className="max-h-[22rem] space-y-0.5 overflow-y-auto">
          {workflows.map((wf) => (
            <li key={wf.name} className="group/row flex items-center gap-1 rounded-lg pr-1 transition-colors hover:bg-accent/60">
              <button type="button" onClick={() => { onLoad(wf); setOpen(false) }} title={wf.problems[0] ?? wf.summary}
                      className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left focus-visible:outline-2 focus-visible:outline-ring">
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-serif text-[0.9375rem] font-semibold">{wf.title}</span>
                  <span className="block truncate text-[0.6875rem] text-muted-foreground">{wf.stages.length} 项{wf.shipped ? '，出厂' : ''}</span>
                </span>
                {wf.problems.length > 0 && <span role="img" aria-label="有问题" className="size-2 shrink-0 rounded-full bg-bad" />}
              </button>
              {/* 出厂的两条是平台的底，没有删；人存的悬停出「删除」，按住才算 */}
              {!wf.shipped && (
                <span className="shrink-0 opacity-0 transition-opacity group-focus-within/row:opacity-100 group-hover/row:opacity-100">
                  <HoldButton holdTime={800} doneLabel={<Trash weight="fill" className="size-3.5" />} className="px-2" onHold={() => remove(wf.name)}>
                    <Trash className="size-3.5" aria-label={`删除 ${wf.title}`} />
                  </HoldButton>
                </span>
              )}
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
