// 结果页：一页纸回答三句话——比原来好了多少、可信吗、能拿去用吗。看完署名验收。

import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/api/client'
import type { LedgerRow, RunDetail, RunSummary } from '@/api/types'
import ClickSpark from '@/components/ClickSpark'
import {
  BigNumber, CheckRow, Details, DoneBlock, Dot, Empty, ErrorNote, KeyBlock, Lede, Numbers, Paragraph,
  Skeleton, type Tone,
} from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Button } from '@/components/ui/button'
import { improvement, metric, seconds, shortHash, usd, when } from '@/lib/format'
import { conclusionOf, roundSentence, runVerdict, stopSentence, trustChecks } from '@/lib/humanize'
import { useResource } from '@/lib/useResource'
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
    return <RunPage id={selected} epoch={epoch} onBack={() => onSelect(null)} onChanged={list.reload} />
  }
  const ordered = list.data ? [...list.data].sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '')) : null
  return (
    <div className="space-y-5 px-6 py-4">
      {list.error && <ErrorNote text={list.error} />}
      {list.loading && !list.data && <Skeleton lines={4} />}
      {ordered?.length === 0 && <Empty title="还没有结果。" hint="需求到「可以开实验」之后，让助理开跑。" />}
      {ordered && ordered.length > 0 && (
        <>
          <p className="t-body text-muted-foreground">每次实验从基线出发，助理一轮一轮改，过了噪声门槛的才留下。看完能用就验收。</p>
          <ul className="divide-y">
            {ordered.map((run) => <RunRow key={run.run_id} run={run} onOpen={() => onSelect(run.run_id)} />)}
          </ul>
        </>
      )}
    </div>
  )
}

function rowTone(run: RunSummary): Tone {
  if (run.running) return 'warn'
  if (run.accept && !run.accept.stale) return 'ok'
  return 'neutral'
}

function RunRow({ run, onOpen }: { run: RunSummary; onOpen: () => void }) {
  const delta = improvement(run.baseline, run.best_metric, run.metric.direction)
  const line = run.accept && !run.accept.stale ? '已验收'
    : delta !== null && delta > 0 ? `比原来好了 ${metric(delta)}，${stopSentence(run.stop_reason, run.running)}`
    : stopSentence(run.stop_reason, run.running)
  return (
    <li>
      <button type="button" onClick={onOpen}
              className="-mx-2 flex w-full items-start gap-3 rounded-md px-2 py-3.5 text-left transition-colors duration-150 hover:bg-muted/60">
        <Dot tone={rowTone(run)} pulse={run.running} className="mt-2" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[0.9375rem] font-medium">{run.title}</span>
          <span className="t-label mt-0.5 block">{line}</span>
        </span>
      </button>
    </li>
  )
}

function RunPage({ id, epoch, onBack, onChanged }: {
  id: string; epoch: number; onBack: () => void; onChanged: () => Promise<void>
}) {
  const run = useResource(() => api.run(id), [id, epoch])
  return (
    <div className="px-6 py-4">
      <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2 mb-4">
        <ArrowLeft data-icon="inline-start" />全部结果
      </Button>
      {run.error && <ErrorNote text={run.error} />}
      {run.loading && !run.data && <Skeleton lines={6} />}
      {run.data && <RunSheet run={run.data} reload={async () => { await run.reload(); await onChanged() }} />}
    </div>
  )
}

function RunSheet({ run, reload }: { run: RunDetail; reload: () => Promise<void> }) {
  const delta = improvement(run.baseline, run.best_metric, run.metric.direction)
  const gate = gateOf(run.ledger)
  const verdict = runVerdict(run, delta, gate)
  const rounds = [...run.ledger].reverse()
  return (
    <article className="space-y-8">
      <header className="space-y-3">
        <h2 className="t-label">{run.title} · {run.run_id}</h2>
        <Lede tone={verdict.tone}>{verdict.headline}</Lede>
        <p className="t-body text-muted-foreground">
          {stopSentence(run.stop_reason, run.running)}，共改了 {run.last_iter} 轮，执行层花了 {usd(run.cost_usd)}。
        </p>
      </header>

      <Numbers>
        <BigNumber label={`原来的 ${run.metric.name}`} value={run.baseline} />
        <BigNumber label={`现在（第 ${run.best_iter} 轮）`} value={run.best_metric} />
        <BigNumber label="好了多少" value={delta} tone={delta !== null && delta > 0 ? 'ok' : 'neutral'} />
      </Numbers>

      <Paragraph title="可信吗">
        <ul className="space-y-1.5">
          {trustChecks(run).map((c) => <CheckRow key={c.text} ok={c.ok} text={c.text} />)}
        </ul>
      </Paragraph>

      {run.analysis_text && (
        <Paragraph title="助理的结论">
          <Markdown text={conclusionOf(run.analysis_text)} />
        </Paragraph>
      )}

      <AcceptKey run={run} reload={reload} />

      <Paragraph title="每一轮发生了什么">
        {rounds.length === 0 ? <p className="text-muted-foreground">还没改过一轮。</p> : (
          <ol className="space-y-1">
            {rounds.map((row) => (
              <li key={row.iter} className={row.status === 'keep' ? 'font-medium' : 'text-muted-foreground'}>
                {roundSentence(row, bestBefore(run.ledger, row, run.baseline), run.metric.direction)}
              </li>
            ))}
          </ol>
        )}
      </Paragraph>

      <div className="space-y-3">
        {run.analysis_text && <Details title="分析全文"><Markdown text={run.analysis_text} /></Details>}
        <Details title="账本原表">
          <LedgerTable rows={rounds} />
        </Details>
        {run.journal.trim() && <Details title="协调记录"><Markdown text={run.journal} /></Details>}
      </div>
    </article>
  )
}

/** 这一轮之前的 best：keep 行的「好了多少」要和它比。 */
function bestBefore(rows: LedgerRow[], row: LedgerRow, baseline: number | null): number | null {
  let best = baseline
  for (const r of rows) {
    if (r.iter >= row.iter) break
    if (r.status === 'keep' && r.metric != null) best = r.metric
  }
  return best
}

/** 噪声门槛：账本备注里 `gate=` 的值；没有就 null。 */
function gateOf(rows: LedgerRow[]): number | null {
  for (const r of [...rows].reverse()) {
    const m = /gate=([0-9.eE+-]+)/.exec(r.note)
    if (m) return Number(m[1])
  }
  return null
}

function LedgerTable({ rows }: { rows: LedgerRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">空。</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-left text-muted-foreground">
          <tr>
            <th className="py-1 pr-3 font-medium">轮</th><th className="py-1 pr-3 font-medium">status</th>
            <th className="py-1 pr-3 font-medium text-right">metric</th><th className="py-1 pr-3 font-medium">commit</th>
            <th className="py-1 pr-3 font-medium text-right">耗时</th><th className="py-1 pr-3 font-medium text-right">花费</th>
            <th className="py-1 font-medium">note</th>
          </tr>
        </thead>
        <tbody className="font-mono">
          {rows.map((row) => (
            <tr key={row.iter} className="border-t align-top">
              <td className="py-1 pr-3 tabular">{row.iter}</td><td className="py-1 pr-3">{row.status}</td>
              <td className="py-1 pr-3 text-right tabular">{metric(row.metric)}</td><td className="py-1 pr-3">{shortHash(row.commit === '-' ? null : row.commit)}</td>
              <td className="py-1 pr-3 text-right tabular">{seconds(row.elapsed_s)}</td><td className="py-1 pr-3 text-right tabular">{usd(row.cost_usd)}</td>
              <td className="py-1 whitespace-pre-wrap break-words">{row.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AcceptKey({ run, reload }: { run: RunDetail; reload: () => Promise<void> }) {
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
      <DoneBlock title={`${run.accept.by} 已验收`}
                 detail={<>{when(run.accept.accepted_at)}，签的是第 {run.accept.best_iter} 轮的 {metric(run.accept.best_metric)}{run.accept.verify ? `，验证 ${run.accept.verify}` : '，当时没验证'}。</>} />
    )
  }
  const cautions: string[] = []
  if (run.accept?.stale) cautions.push(`${run.accept.by} 在 ${when(run.accept.accepted_at)} 验收过，之后结果又变了，要再看一遍。`)
  if (run.verify === null) cautions.push('还没验证。验收的会是没和结果文件对过的数字。')
  else if (run.verify.status !== 'PASS') cautions.push('验证没通过。分析里有对不上的数。')
  if (run.last_iter === 0) cautions.push('一轮都没改，只有基线，没东西可验收。')
  if (run.running) cautions.push('实验还在跑，等它停下。')
  const disabled = busy || run.running || run.last_iter === 0 || !signer.trim()
  return (
    <KeyBlock title="验收这个结果"
              hint={cautions.length > 0 ? <ul className="space-y-1">{cautions.map((c) => <li key={c}>{c}</li>)}</ul>
                : '上面三个数和三个勾就是全部依据。你觉得这个结果能拿去用，署名验收。这颗键只有人能按。'}>
      {error && <div className="mb-3"><ErrorNote text={error} /></div>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SignerField id="accept-signer" value={signer} onChange={setSigner} />
        <ClickSpark sparkColor="oklch(0.62 0.15 72)" sparkRadius={20} sparkCount={8} duration={420}>
          <Button size="lg" onClick={press} disabled={disabled}>{busy ? '验收中…' : '验收结果'}</Button>
        </ClickSpark>
      </div>
    </KeyBlock>
  )
}
