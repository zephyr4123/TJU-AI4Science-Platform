import { ArrowLeft, Check, ChevronDown, ClipboardCheck } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/api/client'
import type { LedgerRow, RunDetail, RunSummary } from '@/api/types'
import ClickSpark from '@/components/ClickSpark'
import { Dot, Empty, ErrorNote, Pill, Row, Section, Skeleton, type Tone } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { improvement, metric, seconds, shortHash, usd, when } from '@/lib/format'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { useSigner } from '@/lib/useSigner'

import { SignerField } from './SignerField'

interface Props {
  epoch: number
  selected: string | null
  onSelect: (id: string | null) => void
}

export function RunBoard({ epoch, selected, onSelect }: Props) {
  const list = useResource(api.runs, [epoch])
  if (selected) {
    return <RunDetailView id={selected} epoch={epoch} onBack={() => onSelect(null)}
                          onChanged={list.reload} />
  }
  const ordered = list.data ? [...list.data].sort((a, b) =>
    (b.updated_at ?? '').localeCompare(a.updated_at ?? '')) : null
  return (
    <div className="space-y-3 p-4">
      <p className="text-sm leading-relaxed text-muted-foreground">
        每个 run 是一次实验：从基线出发，助理一轮一轮改，过统计门的才留下。跑完看分析、看验证，
        你觉得数能用就验收。
      </p>
      {list.error && <ErrorNote text={list.error} />}
      {list.loading && !list.data && <Skeleton lines={4} />}
      {ordered?.length === 0 && <Empty title="还没有 run" hint="任务包到「可开跑」后，让助理开实验。" />}
      <ul className="divide-y rounded-lg border">
        {ordered?.map((run) => <RunRow key={run.run_id} run={run} onOpen={() => onSelect(run.run_id)} />)}
      </ul>
    </div>
  )
}

function runTone(run: RunSummary): { tone: Tone; label: string } {
  if (run.running) return { tone: 'warn', label: '跑着' }
  if (run.accept && !run.accept.stale) return { tone: 'ok', label: '已验收' }
  if (run.stop_reason) return { tone: 'neutral', label: `停了：${run.stop_reason}` }
  return { tone: 'primary', label: '可继续' }
}

function RunRow({ run, onOpen }: { run: RunSummary; onOpen: () => void }) {
  const state = runTone(run)
  const delta = improvement(run.baseline, run.best_metric, run.metric.direction)
  return (
    <li>
      <button type="button" onClick={onOpen}
              className="flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors duration-150 hover:bg-muted/60">
        <Dot tone={state.tone} pulse={run.running} className="mt-1.5" />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-sm font-medium">{run.run_id}</span>
            <span className="shrink-0 font-mono text-xs tabular">
              {metric(run.best_metric)}
              {delta !== null && delta > 0 && <span className="text-ok"> ▾{metric(delta)}</span>}
            </span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <span>{run.title}</span><span>·</span>
            <span className="tabular">{run.last_iter} 轮</span><span>·</span>
            <span>{state.label}</span>
          </div>
        </div>
      </button>
    </li>
  )
}

function RunDetailView({ id, epoch, onBack, onChanged }: {
  id: string; epoch: number; onBack: () => void; onChanged: () => Promise<void>
}) {
  const run = useResource(() => api.run(id), [id, epoch])
  return (
    <div className="space-y-5 p-4">
      <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2">
        <ArrowLeft data-icon="inline-start" />全部 run
      </Button>
      {run.error && <ErrorNote text={run.error} />}
      {run.loading && !run.data && <Skeleton lines={6} />}
      {run.data && <RunBody run={run.data} reload={async () => { await run.reload(); await onChanged() }} />}
    </div>
  )
}

function RunBody({ run, reload }: { run: RunDetail; reload: () => Promise<void> }) {
  const delta = improvement(run.baseline, run.best_metric, run.metric.direction)
  const state = runTone(run)
  return (
    <>
      <header>
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold tracking-tight">{run.run_id}</h2>
          <Pill tone={state.tone}>{state.label}</Pill>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{run.title} · 更新于 {when(run.updated_at)}</p>
      </header>

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border">
        <Stat label={`基线 ${run.metric.name}`} value={metric(run.baseline)} />
        <Stat label={`best（第 ${run.best_iter} 轮）`} value={metric(run.best_metric)}
              sub={delta === null ? undefined : delta > 0 ? `改进 ${metric(delta)}` : '没有改进'}
              tone={delta !== null && delta > 0 ? 'ok' : undefined} />
        <Stat label="轮次" value={String(run.last_iter)} sub={run.stop_reason ? `停止：${run.stop_reason}` : undefined} />
        <Stat label="执行层花费" value={usd(run.cost_usd)} />
      </div>

      <AcceptPanel run={run} reload={reload} />

      <Section title="分析与验证">
        <dl className="divide-y rounded-lg border px-3">
          <Row label="分析" mono={false}>{run.analysis ? '已写' : <span className="text-muted-foreground">还没跑</span>}</Row>
          <Row label="验证" mono={false}>
            {run.verify === null ? <span className="text-muted-foreground">还没跑</span>
              : run.verify.status === 'PASS' ? <Pill tone="ok">PASS：数字都能回溯</Pill>
              : run.verify.status === 'FAIL' ? <Pill tone="bad">FAIL：有对不上的数</Pill>
              : <Pill tone="bad">报告不合约</Pill>}
          </Row>
        </dl>
        {run.verify?.status === 'invalid' && run.verify.error && <ErrorNote text={run.verify.error} />}
        {run.analysis_text && (
          <Collapsible>
            <CollapsibleTrigger className="group flex w-full items-center justify-between py-1 text-[13px] font-medium">
              分析全文
              <ChevronDown className="size-4 text-muted-foreground transition-transform duration-150 group-data-[state=open]:rotate-180" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <Markdown text={run.analysis_text} className="mt-2 rounded-lg border px-4 py-3" />
            </CollapsibleContent>
          </Collapsible>
        )}
      </Section>

      <Section title={`账本（${run.ledger.length} 行）`}>
        <Ledger rows={run.ledger} />
      </Section>

      {run.journal.trim() && (
        <Collapsible>
          <CollapsibleTrigger className="group flex w-full items-center justify-between py-1 text-[13px] font-semibold tracking-tight">
            协调记录（journal）
            <ChevronDown className="size-4 text-muted-foreground transition-transform duration-150 group-data-[state=open]:rotate-180" />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <Markdown text={run.journal} className="mt-2 rounded-lg border px-4 py-3" />
          </CollapsibleContent>
        </Collapsible>
      )}
    </>
  )
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: Tone }) {
  return (
    <div className="bg-background px-3 py-2.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-mono text-lg tabular tracking-tight">{value}</div>
      {sub && <div className={cn('text-xs', tone === 'ok' ? 'text-ok' : 'text-muted-foreground')}>{sub}</div>}
    </div>
  )
}

const STATUS_TONE: Record<string, Tone> = {
  keep: 'ok', discard: 'neutral', noop: 'neutral', interrupted: 'warn',
  timeout: 'bad', crash: 'bad', no_results: 'bad', readonly_violated: 'bad', executor_failed: 'bad',
}

function Ledger({ rows }: { rows: LedgerRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">还没跑过一轮。</p>
  return (
    <div className="max-w-full overflow-hidden rounded-lg border">
      {/* 固定列宽、备注截断，整表不横向滚；完整备注与耗时放在悬停提示里 */}
      <Table className="table-fixed text-xs">
        <TableHeader>
          <TableRow>
            <TableHead className="w-9">轮</TableHead>
            <TableHead className="w-[7.5rem]">判决</TableHead>
            <TableHead className="w-16 text-right">指标</TableHead>
            <TableHead>备注</TableHead>
            <TableHead className="w-14 text-right">花费</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...rows].reverse().map((row) => (
            <TableRow key={row.iter}>
              <TableCell className="font-mono tabular">{row.iter}</TableCell>
              <TableCell><Pill tone={STATUS_TONE[row.status] ?? 'neutral'}>{row.status}</Pill></TableCell>
              <TableCell className="text-right font-mono tabular">{metric(row.metric)}</TableCell>
              <TableCell className="truncate text-muted-foreground"
                         title={`${row.note}${row.commit !== '-' ? ` · ${shortHash(row.commit)}` : ''} · 耗时 ${seconds(row.elapsed_s)}`}>
                {row.note}{row.commit !== '-' && <span className="ml-1.5 font-mono opacity-60">· {shortHash(row.commit)}</span>}
              </TableCell>
              <TableCell className="text-right font-mono tabular text-muted-foreground">{usd(row.cost_usd)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function AcceptPanel({ run, reload }: { run: RunDetail; reload: () => Promise<void> }) {
  const [signer, setSigner] = useSigner()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const press = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.accept(run.run_id, signer)
      await reload()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  if (run.accept && !run.accept.stale) {
    return (
      <div className="flex items-start gap-2 rounded-lg bg-ok-soft px-3 py-2.5 text-sm text-ok">
        <Check className="mt-0.5 size-4 shrink-0" />
        <div>
          <div className="font-medium">已验收</div>
          <div className="mt-0.5 text-xs opacity-80">
            {run.accept.by} · {when(run.accept.accepted_at)} · 第 {run.accept.best_iter} 轮 {metric(run.accept.best_metric)}
            {run.accept.verify ? ` · 验证 ${run.accept.verify}` : ' · 未经验证'}
          </div>
        </div>
      </div>
    )
  }

  const cautions: string[] = []
  if (run.accept?.stale) cautions.push(`上次验收（${run.accept.by}，${when(run.accept.accepted_at)}）之后 best 变了，要再看一遍。`)
  if (run.verify === null) cautions.push('验证还没跑：验收的会是没经过回溯检查的数字。让助理先跑验证。')
  else if (run.verify.status !== 'PASS') cautions.push('验证没通过：分析里有对不上的数，别急着验收。')
  if (run.last_iter === 0) cautions.push('一轮都没跑，只有基线，没东西可验收。')

  return (
    <div className="space-y-3 rounded-lg border border-primary/30 bg-accent/40 p-3">
      <div className="flex items-start gap-2">
        <ClipboardCheck className="mt-0.5 size-4 shrink-0 text-primary" />
        <div className="text-sm leading-relaxed">
          <div className="font-medium">验收：这个结果能拿去用了吗</div>
          <p className="text-muted-foreground">看 best 比基线好了多少、分析怎么说、验证过没过。验收签的是这一版 best。</p>
        </div>
      </div>
      {cautions.length > 0 && (
        <ul className="space-y-1 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
          {cautions.map((c) => <li key={c}>{c}</li>)}
        </ul>
      )}
      {error && <ErrorNote text={error} />}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SignerField id="accept-signer" value={signer} onChange={setSigner} />
        <ClickSpark sparkColor="oklch(0.62 0.15 72)" sparkRadius={18} sparkCount={8} duration={420}>
          <Button onClick={press} disabled={busy || run.running || run.last_iter === 0 || !signer.trim()}>
            {busy ? '验收中…' : '验收结果'}
          </Button>
        </ClickSpark>
      </div>
    </div>
  )
}
