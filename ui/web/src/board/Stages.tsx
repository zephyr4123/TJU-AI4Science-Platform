// 需求确认之后的主页面：七个阶段一格一格，格里列这个阶段的产出（谁产的、读了谁、成没成、签没签）；
// 下面每条流实例一条，走到哪、在等谁。流没走的阶段是空格。产出点开侧滑看目录里的文件、签字。
import { CaretDown } from '@phosphor-icons/react'
import { createElement, useState } from 'react'

import type { FlowOutput, FlowProgress, FlowProgressItem, OutputBrief, StageBoard, WorkspaceDetail } from '@/api/types'
import { Dot, Problems } from '@/components/bits'
import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
import { byWord, outputWord, WAITING_WORD } from '@/lib/humanize'
import { itemIcon, itemLabel, stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { needsSign } from './derive'

export function Stages({ doc, titleOf, onOpen }: { doc: WorkspaceDetail; titleOf: (cap: string) => string | undefined; onOpen: (oid: string) => void }) {
  const waiting = needsSign(doc.flows)
  const running = new Set(doc.jobs.filter((j) => j.effective_status === 'running').map((j) => j.output))
  return (
    <div className="space-y-6">
      <ol className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))]" aria-label="阶段">
        {doc.stages.map((stage, i) => (
          <StageCard key={stage.slug} n={i + 1} stage={stage} waiting={waiting} running={running} onOpen={onOpen} />
        ))}
      </ol>
      {doc.flows.length > 0 && (
        <section className="space-y-3" aria-label="流">
          {doc.flows.map((flow) => <FlowLane key={flow.name} flow={flow} titleOf={titleOf} onOpen={onOpen} />)}
        </section>
      )}
    </div>
  )
}

/** 一个阶段一格：序号（七个阶段的固定序，宋体淡字，像图纸编号）、图标、名字、几次；产出一行一次。没有产出的格淡。 */
function StageCard({ n, stage, waiting, running, onOpen }: {
  n: number; stage: StageBoard; waiting: Set<string>; running: Set<string | null>; onOpen: (oid: string) => void
}) {
  const empty = stage.outputs.length === 0
  return (
    <li>
      <SpotlightCard spotlight="color-mix(in oklab, var(--primary) 10%, transparent)"
                     className={cn('h-full min-h-[9rem] rounded-2xl', empty && 'border-dashed bg-transparent shadow-none')}>
        <div className="relative flex h-full flex-col px-4 pt-3 pb-3">
          <span aria-hidden className={cn('absolute top-2 right-3 font-serif text-[1.5rem] leading-none font-semibold tabular-nums', empty ? 'text-foreground/10' : 'text-foreground/15')}>{n}</span>
          <div className="flex items-center gap-2 pr-6">
            {createElement(stageIcon(stage.name), { weight: 'duotone', 'aria-hidden': true, className: cn('size-5 shrink-0', empty ? 'text-muted-foreground/60' : 'text-primary') })}
            <span className={cn('font-serif text-[1.0625rem] font-semibold', empty && 'text-muted-foreground')}>{stage.name}</span>
            {!empty && <span className="t-label tabular-nums">{stage.outputs.length}</span>}
          </div>
          {!empty && (
            <ul className="mt-2 space-y-1">
              {stage.outputs.map((o) => (
                <li key={o.id}>
                  <OutputRow output={o} sign={waiting.has(o.id)} live={running.has(o.id)} onOpen={() => onOpen(o.id)} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </SpotlightCard>
    </li>
  )
}

function OutputRow({ output, sign, live, onOpen }: { output: OutputBrief; sign: boolean; live: boolean; onOpen: () => void }) {
  const tone = output.status === 'failed' ? 'bad' : live ? 'primary' : sign ? 'warn' : output.signed && !output.signed.stale ? 'ok' : 'neutral'
  return (
    <button type="button" onClick={onOpen}
            className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-accent/60 focus-visible:outline-2 focus-visible:outline-ring">
      <Dot tone={tone} pulse={live} className="mt-1.5" />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="min-w-0 text-[0.875rem] leading-snug">{output.title}</span>
          <span className={cn('shrink-0 text-[0.75rem]', sign ? 'font-semibold text-wait' : 'text-muted-foreground')}>
            {live ? '在跑' : sign ? '等你签' : outputWord(output)}
          </span>
        </span>
        <span className="mt-0.5 block truncate font-mono text-[0.6875rem] text-muted-foreground">
          {output.id.split('/')[1]} · {byWord(output.by)}{output.from.length > 0 && ` ← ${output.from.join(', ')}`}
        </span>
      </span>
    </button>
  )
}

// ── 流：一条一行，展开是一项一格 ─────────────────────────────────────────────
function FlowLane({ flow, titleOf, onOpen }: { flow: FlowProgress; titleOf: (cap: string) => string | undefined; onOpen: (oid: string) => void }) {
  const broken = flow.problems.length > 0 || !flow.items
  const [open, setOpen] = useState(!broken && flow.waiting !== 'done')
  const note = broken ? '坏了' : `${WAITING_WORD[flow.waiting ?? 'assistant']} · ${(flow.step ?? -1) + 1} / ${flow.total ?? flow.stages.length}`
  return (
    <section className="rounded-2xl border bg-card/80 backdrop-blur-sm">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
              className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left transition-colors hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-ring">
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            {flow.waiting === 'job' && <Dot tone="primary" pulse />}
            <span className="truncate font-serif text-[1rem] font-semibold">{flow.title}</span>
            <span className="t-label font-mono">{flow.name}</span>
          </span>
          <span className={cn('mt-0.5 block truncate text-[0.8125rem]', broken ? 'text-bad' : flow.waiting === 'sign' ? 'text-wait' : 'text-muted-foreground')}>{note}</span>
        </span>
        <CaretDown aria-hidden className={cn('size-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="px-4 pt-1 pb-4">
          {broken ? <Problems items={flow.problems} /> : (
            <ol className="flex flex-wrap gap-2">
              {flow.items!.map((item) => <FlowCell key={item.index} item={item} flow={flow} titleOf={titleOf} onOpen={onOpen} />)}
            </ol>
          )}
        </div>
      )}
    </section>
  )
}

function FlowCell({ item, flow, titleOf, onOpen }: { item: FlowProgressItem; flow: FlowProgress; titleOf: (cap: string) => string | undefined; onOpen: (oid: string) => void }) {
  const step = flow.step ?? -1
  const isStop = item.kind === 'stop'
  const done = isStop ? item.signed : item.outputs.some((o) => o.status === 'ok')
  const current = item.index === step + 1
  const state = done ? 'done' : current ? (isStop ? 'sign' : flow.waiting === 'job' ? 'job' : 'now') : 'todo'
  const label = itemLabel(item.kind === 'stage' ? { kind: 'stage', stage: item.stage, caps: item.caps } : { kind: 'stop', note: item.note }, titleOf)
  return (
    <li className={cn('flex items-center gap-2 rounded-xl border px-3 py-2 text-[0.8125rem]',
                      state === 'done' && 'border-ok/40 bg-ok-soft/60 text-ok',
                      state === 'sign' && 'border-wait/50 bg-wait-soft text-wait',
                      state === 'job' && 'border-primary/50 bg-primary/10 text-primary',
                      state === 'now' && 'border-primary/40 text-foreground',
                      state === 'todo' && 'border-dashed text-muted-foreground')}>
      {createElement(itemIcon(item.kind === 'stage' ? { kind: 'stage', stage: item.stage, caps: item.caps } : { kind: 'stop', note: item.note }),
                     { weight: 'duotone', 'aria-hidden': true, className: 'size-4 shrink-0' })}
      <span className="whitespace-nowrap">{label}</span>
      {!isStop && item.outputs.length > 0 && (
        <span className="flex gap-1">
          {item.outputs.map((o: FlowOutput) => (
            <button key={o.id} type="button" onClick={() => onOpen(o.id)} title={o.title}
                    className="rounded-md bg-background/70 px-1.5 font-mono text-[0.6875rem] text-foreground/80 hover:bg-background focus-visible:outline-2 focus-visible:outline-ring">
              {o.id.split('/')[1]}
            </button>
          ))}
        </span>
      )}
    </li>
  )
}
