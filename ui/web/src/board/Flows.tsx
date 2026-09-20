// 需求确认之后的主页面：一条流程一张表。横向是流程经过的阶段（有什么阶段就几列），纵向是每一列跑过的每一次产出；
// 断点是两列之间的一道线。右上角一句话说在等谁。流程没经过的阶段不出现；不在任何流程里的产出只在最底下一行「其它」。
import { CheckCircle, Signature } from '@phosphor-icons/react'
import { createElement, useState } from 'react'

import { api } from '@/api/client'
import type { FlowOutput, FlowProgress, FlowProgressItem, ResearchStage, WorkspaceDetail } from '@/api/types'
import { Dot, ErrorNote, Problems } from '@/components/bits'
import { useSigner } from '@/lib/useSigner'
import { stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { type NameOf, needsSign, nextStage, type OutputState, outputName, outputState, shortNote, waitingSentence } from './derive'

const STATE_WORD: Record<OutputState, string> = {
  running: '运行中', failed: '失败', pending: '待确认', confirmed: '已确认', done: '完成',
}

/** 一列底下列哪些能力：流程点名的（靛色小片），或没点名时这个阶段能用的（素色小片）；名直接显示、一行 hover */
export interface ColumnCaps { caps: { title: string; brief: string }[]; named: boolean }

export function Flows({ doc, capsOf, onOpen, onChanged }: {
  doc: WorkspaceDetail
  capsOf: (stage: ResearchStage, named: string[]) => ColumnCaps
  onOpen: (oid: string) => void
  onChanged: () => Promise<void>
}) {
  const nameOf: NameOf = (slug) => doc.stages.find((s) => s.slug === slug)?.name ?? slug
  const pending = needsSign(doc.flows)
  const loose = doc.stages.flatMap((s) => s.outputs.filter((o) => o.flow === null))
  return (
    <div className="space-y-6">
      {doc.flows.length === 0 && <p className="t-label">尚未选定流程。与助理说明照哪条流程进行。</p>}
      {doc.flows.map((flow) => (
        <FlowTable key={flow.name} workspace={doc.id} flow={flow} pending={pending} nameOf={nameOf} capsOf={capsOf} onOpen={onOpen} onChanged={onChanged} />
      ))}
      {loose.length > 0 && (
        <section aria-label="其它">
          <h3 className="t-label">其它</h3>
          <ul className="mt-2 flex flex-wrap gap-2">
            {loose.map((o) => (
              <li key={o.id}>
                <button type="button" onClick={() => onOpen(o.id)}
                        className="rounded-lg border bg-card/80 px-3 py-1.5 text-[0.8125rem] hover:bg-accent/60 focus-visible:outline-2 focus-visible:outline-ring">
                  {outputName(o.id, nameOf)} · {o.title}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/** 一条流程一张表：题头（标题 + 在等谁）、一行列（阶段列与断点线交替） */
function FlowTable({ workspace, flow, pending, nameOf, capsOf, onOpen, onChanged }: {
  workspace: string; flow: FlowProgress; pending: Set<string>; nameOf: NameOf
  capsOf: (stage: ResearchStage, named: string[]) => ColumnCaps; onOpen: (oid: string) => void
  onChanged: () => Promise<void>
}) {
  const broken = flow.problems.length > 0 || !flow.items
  const sentence = waitingSentence(flow, pending, nameOf)
  const next = broken ? null : nextStage(flow)
  const runningOutput = flow.job?.output ?? null
  return (
    <section className="rounded-2xl border bg-card/80 p-5 backdrop-blur-sm" aria-label={flow.title}>
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="font-serif text-[1.0625rem] font-semibold">{flow.title}</span>
        <span className="flex items-center gap-3">
          <span className={cn('text-[0.875rem]', broken ? 'text-bad' : flow.waiting === 'sign' ? 'font-semibold text-wait' : flow.waiting === 'job' ? 'text-primary' : 'text-muted-foreground')}>
            {sentence}
          </span>
          {flow.waiting === 'job' && flow.job && <StopKey workspace={workspace} jobId={flow.job.job_id} onChanged={onChanged} />}
        </span>
      </header>
      {broken ? <div className="mt-3"><Problems items={flow.problems} /></div> : (
        <ol className="mt-4 flex items-stretch gap-3 overflow-x-auto pb-1" aria-label="步">
          {flow.items!.map((item) => item.kind === 'stage'
            ? <StageColumn key={item.index} item={item} flow={flow} pending={pending} caps={capsOf(item.stage, item.caps.map((c) => c.cap))}
                           current={item.index === next?.index} runningOutput={runningOutput} onOpen={onOpen} />
            : <StopLine key={item.index} item={item} flow={flow} />)}
        </ol>
      )}
    </section>
  )
}

/** 一列：阶段名、「能力」标签 + 小片、下面一张一张产出；当前那列靛色边框，没到的虚线 */
function StageColumn({ item, flow, pending, caps, current, runningOutput, onOpen }: {
  item: Extract<FlowProgressItem, { kind: 'stage' }>; flow: FlowProgress; pending: Set<string>; caps: ColumnCaps
  current: boolean; runningOutput: string | null; onOpen: (oid: string) => void
}) {
  const step = flow.step ?? -1
  const reached = item.index <= step || item.outputs.length > 0
  const showNext = current && flow.waiting === 'assistant'
  const showRunning = current && flow.waiting === 'job' && !item.outputs.some((o) => o.id === runningOutput)
  return (
    <li className={cn('flex w-[11.5rem] shrink-0 flex-col rounded-xl border p-3',
                      current ? 'border-primary bg-card' : reached ? 'bg-card' : 'border-dashed text-muted-foreground')}>
      <div className="flex items-center gap-1.5">
        {createElement(stageIcon(item.stage), { weight: 'duotone', 'aria-hidden': true, className: cn('size-4 shrink-0', current ? 'text-primary' : reached ? 'text-foreground/70' : 'text-muted-foreground/60') })}
        <span className="font-serif text-[1rem] font-semibold">{item.stage}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        <span className="mr-0.5 text-[0.6875rem] text-muted-foreground">能力</span>
        {caps.caps.length === 0 && <span className="text-[0.6875rem] text-muted-foreground/70">无</span>}
        {caps.caps.map((cap) => (
          <span key={cap.title} title={cap.brief} className={cn('rounded-md px-1.5 py-0.5 text-[0.6875rem] leading-tight',
                                                               caps.named ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground')}>{cap.title}</span>
        ))}
      </div>
      <ul className="mt-2 space-y-1.5">
        {item.outputs.map((o) => <OutputCard key={o.id} output={o} state={outputState(o, pending)} onOpen={() => onOpen(o.id)} />)}
        {showNext && <li className="rounded-lg border border-dashed border-primary/60 px-2.5 py-1.5 text-[0.8125rem] text-primary">下一步</li>}
        {showRunning && <li className="flex items-center gap-2 rounded-lg border border-primary/40 px-2.5 py-1.5 text-[0.8125rem] text-primary"><Dot tone="primary" pulse />运行中</li>}
        {!reached && !showNext && !showRunning && <li className="h-7 rounded-lg border border-dashed border-border/70" aria-hidden />}
      </ul>
    </li>
  )
}

function OutputCard({ output, state, onOpen }: { output: FlowOutput; state: OutputState; onOpen: () => void }) {
  const n = output.id.split('/')[1]
  return (
    <li>
      <button type="button" onClick={onOpen} title={output.title}
              className={cn('flex w-full items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-left text-[0.8125rem] transition-colors hover:bg-accent/60 focus-visible:outline-2 focus-visible:outline-ring',
                            state === 'confirmed' && 'border-ok/40 bg-ok-soft/50 text-ok',
                            state === 'pending' && 'border-wait/50 bg-wait-soft text-wait',
                            state === 'failed' && 'border-bad/40 text-bad',
                            state === 'running' && 'border-primary/40 text-primary',
                            state === 'done' && 'bg-background/60')}>
        <span className="flex items-center gap-2">
          {state === 'running' && <Dot tone="primary" pulse />}
          <span className="tabular-nums">{n}</span>
        </span>
        <span className={cn(state === 'pending' && 'font-semibold')}>{STATE_WORD[state]}</span>
      </button>
    </li>
  )
}

/** 断点：两列之间一道竖线，线上一枚符号（已确认 ✓ 铜绿 / 待确认 琥珀 / 没到 灰），底下两三个字，全句悬停 */
function StopLine({ item, flow }: { item: Extract<FlowProgressItem, { kind: 'stop' }>; flow: FlowProgress }) {
  const step = flow.step ?? -1
  const state = item.signed ? 'signed' : item.index === step + 1 && flow.waiting === 'sign' ? 'pending' : 'todo'
  const label = shortNote(item.note || '确认')
  return (
    <li className="flex w-[4.5rem] shrink-0 flex-col items-center" title={item.note || '确认'} aria-label={`断点：${item.note || '确认'}`}>
      <span className={cn('flex flex-1 flex-col items-center', state === 'signed' ? 'text-ok' : state === 'pending' ? 'text-wait' : 'text-muted-foreground/50')}>
        <span className={cn('w-px flex-1', state === 'signed' ? 'bg-ok/50' : state === 'pending' ? 'bg-wait/60' : 'bg-border')} />
        {state === 'signed'
          ? <CheckCircle weight="fill" className="my-1 size-5" aria-hidden />
          : <Signature weight={state === 'pending' ? 'fill' : 'regular'} className="my-1 size-5" aria-hidden />}
        <span className={cn('w-px flex-1', state === 'signed' ? 'bg-ok/50' : state === 'pending' ? 'bg-wait/60' : 'bg-border')} />
      </span>
      <span className={cn('mt-1 text-center text-[0.6875rem] leading-tight whitespace-nowrap', state === 'pending' ? 'font-semibold text-wait' : state === 'signed' ? 'text-ok' : 'text-muted-foreground')}>{label}</span>
    </li>
  )
}

/** 停一个正在跑的作业：第一下只是拉开保险（变红），第二下才停（外层 #115）。署名与确认键同一个。 */
function StopKey({ workspace, jobId, onChanged }: { workspace: string; jobId: string; onChanged: () => Promise<void> }) {
  const [signer] = useSigner()
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const press = async () => {
    if (!armed) { setArmed(true); return }
    setBusy(true)
    setError(null)
    try {
      await api.stopJob(workspace, jobId, signer.trim() || '研究者')
      await onChanged()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
      setArmed(false)
    }
  }
  return (
    <span className="flex items-center gap-2">
      <button type="button" onClick={press} onBlur={() => setArmed(false)} disabled={busy}
              className={cn('rounded-lg border px-2.5 py-1 text-[0.8125rem] transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                            armed ? 'border-bad bg-bad/10 text-bad' : 'bg-card/80 text-muted-foreground hover:text-foreground')}>
        {busy ? '停止中' : armed ? '确认停止' : '停止'}
      </button>
      {error && <ErrorNote text={error} />}
    </span>
  )
}
