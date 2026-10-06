// 首页右栏下半「花费」（外层 #256）：近 7 / 30 / 90 天花了多少，按天、按项目、按模型。
// 一块暖调的玻璃（玫红、杏色，与左边项目清单的靛、青对着映衬）；数据只用一种颜色（玫红，柱子从玫红渐到杏色），
// 不画多色系列：每张图都是一个系列，排行是长短，不靠颜色分。两种看法——折算美元 / token：Claude Code 报的是按 API 价
// 折算的美元（订阅账号不是实扣），Codex 不报美元只报 token，所以按美元看时 Codex 那几格不画、写「未报美元」，
// 那天有调用却没报的在柱脚点一个灰点；按 token 看两家都在。换范围时上一份淡着顶住，不闪骨架。
import { Info } from '@phosphor-icons/react'
import { useState } from 'react'

import type { Spending as SpendingDoc, SpendCell } from '@/api/types'
import { Aurora } from '@/components/Aurora'
import { ErrorNote, Skeleton } from '@/components/bits'
import type { Resource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { type Bucket, buckets, type Metric, type Range, RANGES, ranked, tokens, valueOf } from './usage'

const FOOTNOTE = 'Claude Code 报的是按 API 价折算的美元，订阅账号不是实扣；Codex 不报美元，只算 token'

export function Spending({ usage, range, onRange, metric, onMetric, onOpenProject }: {
  usage: Resource<SpendingDoc>
  range: Range
  onRange: (r: Range) => void
  metric: Metric
  onMetric: (m: Metric) => void
  onOpenProject: (id: string) => void
}) {
  // 换范围时新的那份还没回来：上一份淡着顶住（不闪骨架）；记上一份用渲染时更新的 state（React 的「记住上一次」写法）
  const [held, setHeld] = useState<SpendingDoc | null>(usage.data)
  if (usage.data && usage.data !== held) setHeld(usage.data)
  const doc = usage.data ?? held
  const stale = !usage.data && held !== null
  return (
    <Aurora tone="warm" className="h-full">
      <section aria-label="花费" className="px-5 pt-4 pb-5">
        <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h2 className="mr-auto font-serif text-[1.0625rem] font-semibold">花费</h2>
          <Segmented label="看法" value={metric} onChange={onMetric}
                     options={[{ value: 'usd', label: '美元' }, { value: 'tokens', label: 'token' }]} />
          <Segmented label="时间范围" value={range} onChange={onRange}
                     options={RANGES.map((r) => ({ value: r, label: `${r} 天` }))} />
        </header>
        {usage.error && !doc && <ErrorNote text={usage.error} className="mt-4" />}
        {!doc && !usage.error && <div className="mt-4"><Skeleton lines={6} /></div>}
        {doc && (
          <div className={cn('transition-opacity duration-200', stale && 'opacity-55')}>
            {/* 上半横着摆：左边一共多少与拆分，右边按天的柱子；下半两栏：按项目、按模型（主人 2026-10-06：横纵结合，别越拉越长） */}
            <div className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-[10.5rem_minmax(0,1fr)]">
              <Headline doc={doc} metric={metric} />
              {doc.total.count === 0
                ? <p className="self-center text-[0.875rem] text-muted-foreground">近 {doc.days} 天没有调用</p>
                : <Columns bars={buckets(doc.by_day)} metric={metric} />}
            </div>
            {doc.total.count > 0 && (
              <div className="mt-5 grid gap-x-6 gap-y-5 border-t border-foreground/[0.07] pt-4 sm:grid-cols-2">
                <Ranking title="按项目" metric={metric} n={4}
                         rows={doc.by_project.map((p) => ({ ...p, key: p.id ?? '', name: p.title, onClick: p.id ? () => onOpenProject(p.id!) : undefined }))} />
                <Ranking title="按模型" metric={metric} n={4}
                         rows={doc.by_model.map((m) => ({ ...m, key: `${m.backend}/${m.model}`, name: m.model_title, kicker: m.backend_title }))} />
              </div>
            )}
          </div>
        )}
      </section>
    </Aurora>
  )
}

/** 看法的读法：美元两位小数；token 用万与亿 */
function say(value: number, metric: Metric): string {
  return metric === 'usd' ? `$${value.toFixed(2)}` : tokens(value)
}

/** 左边一列：一共多少（大数）与三行拆分——对话、运行、几次没报美元 */
function Headline({ doc, metric }: { doc: SpendingDoc; metric: Metric }) {
  const total = valueOf(doc.total, metric)
  const facts: [string, string][] = doc.by_kind.map((k) => {
    const v = valueOf(k, metric)
    return [k.title, v === null ? '未报' : say(v, metric)]
  })
  if (metric === 'usd' && doc.total.unknown > 0) facts.push(['未报美元', `${doc.total.unknown} 次`])
  return (
    <div>
      <p className="flex items-center gap-1 text-[0.75rem] text-muted-foreground" title={FOOTNOTE}>
        近 {doc.days} 天{metric === 'usd' ? '（折算）' : ' token'}
        <Info className="size-3.5 cursor-help" aria-label={FOOTNOTE} />
      </p>
      <p className="mt-1 text-[1.875rem] leading-tight font-semibold tracking-tight">{total === null ? '—' : say(total, metric)}</p>
      <dl className="mt-3 space-y-1 text-[0.75rem]">
        {facts.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="text-foreground/80 tabular">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/** 按天（或按周）的柱子：一个系列一种颜色；悬停那根亮、别的淡，右上角读出那天的数；有调用却没报美元的那天柱脚一个灰点 */
function Columns({ bars, metric }: { bars: Bucket[]; metric: Metric }) {
  const [hover, setHover] = useState<number | null>(null)
  const values = bars.map((b) => valueOf(b, metric) ?? 0)
  const max = Math.max(...values, 0)
  const labelled = bars.length <= 7 ? bars.map((_, i) => i) : [0, Math.floor((bars.length - 1) / 2), bars.length - 1]
  const shown = hover === null ? null : bars[hover]
  return (
    <figure aria-label={`按${bars.length > 31 ? '周' : '天'}的${metric === 'usd' ? '折算美元' : ' token'}`}>
      {/* 头一行：左边纵轴的顶（最高那根是多少），右边悬停那根的读数——写在卡里，不浮出去被卡的圆角裁掉 */}
      <div className="flex h-4 items-baseline justify-between gap-3 text-[0.6875rem] tabular">
        <span className="text-muted-foreground">{max > 0 ? say(max, metric) : ''}</span>
        {shown && <Readout bucket={shown} metric={metric} />}
      </div>
      <div className="relative">
        <div className="flex h-28 items-end gap-[2px] border-b border-foreground/10 pt-1" onMouseLeave={() => setHover(null)}>
          {bars.map((b, i) => {
            const v = values[i]
            const silent = metric === 'usd' && b.count > 0 && v === 0
            return (
              <div key={b.label} className="relative flex h-full flex-1 items-end justify-center" onMouseEnter={() => setHover(i)}>
                {v > 0 && (
                  <div className={cn('w-full max-w-[18px] rounded-t-[4px] transition-[height,opacity] duration-500 ease-out motion-reduce:transition-none',
                                     hover !== null && hover !== i && 'opacity-40')}
                       style={{ height: `${Math.max(2, (v / max) * 100)}%`,
                                background: 'linear-gradient(to top, var(--spend), color-mix(in oklab, var(--spend-glow) 80%, var(--spend)))' }} />
                )}
                {silent && <span aria-hidden="true" className="mb-0.5 size-1 rounded-full bg-muted-foreground/50" />}
              </div>
            )
          })}
        </div>
      </div>
      <div className="relative mt-1.5 h-4 text-[0.6875rem] text-muted-foreground tabular">
        {labelled.map((i) => <Tick key={i} label={bars[i].label} at={(i + 0.5) / bars.length} edge={bars.length > 7 && (i === 0 ? 'start' : i === bars.length - 1 ? 'end' : null)} />)}
      </div>
      <table className="sr-only">
        <tbody>{bars.map((b) => <tr key={b.label}><th>{b.label}</th><td>{b.cost_usd === null ? '未报' : `$${b.cost_usd.toFixed(2)}`}</td><td>{tokens(b.tokens)} token</td></tr>)}</tbody>
      </table>
    </figure>
  )
}

/** 横轴上一个刻度：标在那根柱子正下方；只标头、中、尾时，头尾贴着两边对齐，不出界 */
function Tick({ label, at, edge }: { label: string; at: number; edge: 'start' | 'end' | null | false }) {
  if (edge === 'start') return <span className="absolute top-0 left-0 whitespace-nowrap">{label}</span>
  if (edge === 'end') return <span className="absolute top-0 right-0 whitespace-nowrap">{label}</span>
  return <span className="absolute top-0 -translate-x-1/2 whitespace-nowrap" style={{ left: `${at * 100}%` }}>{label}</span>
}

/** 悬停那根的读数：哪天（哪周）、这种看法的数、几次调用、几次没报美元 */
function Readout({ bucket, metric }: { bucket: Bucket; metric: Metric }) {
  const v = valueOf(bucket, metric)
  return (
    <span aria-live="polite" className="flex min-w-0 items-center gap-1.5 truncate text-foreground/80">
      <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-spend" />
      <span className="font-medium">{bucket.label}</span>
      <span>{bucket.count === 0 ? '没有调用' : metric === 'tokens' ? `${tokens(bucket.tokens)} token` : `$${(v ?? 0).toFixed(2)}`}</span>
      {bucket.count > 0 && <span className="text-muted-foreground">· {bucket.count} 次{metric === 'usd' && bucket.unknown > 0 ? `，${bucket.unknown} 次未报` : ''}</span>}
    </span>
  )
}

interface Ranked extends SpendCell { key: string; name: string; kicker?: string; onClick?: () => void }

/** 一张排行：名字与数一行，底下一根细条（长短就是多少，一种颜色）；露前几名，其余并成一行。按美元看时没报的写「未报美元」不画条 */
function Ranking({ title, rows, metric, n }: { title: string; rows: Ranked[]; metric: Metric; n: number }) {
  const { top, rest } = ranked(rows, metric, n)
  const max = Math.max(...rows.map((r) => valueOf(r, metric) ?? 0), 0)
  const lines = [...top.map((r) => ({ ...r, muted: false })),
                 ...(rest ? [{ ...rest, key: '其余', name: `其余 ${rest.rows} 个`, muted: true }] : [])]
  return (
    <section className="min-w-0">
      <h3 className="text-[0.8125rem] font-semibold text-foreground/85">{title}</h3>
      <ul className="mt-2 space-y-2.5">
        {lines.map((r) => {
          const v = valueOf(r, metric)
          const body = (
            <>
              <span className="flex items-baseline justify-between gap-3 text-[0.8125rem]">
                <span className={cn('min-w-0 truncate', r.muted && 'text-muted-foreground')}>
                  {'kicker' in r && r.kicker && <span className="text-muted-foreground">{r.kicker} · </span>}{r.name}
                </span>
                <span className={cn('shrink-0 tabular', v === null ? 'text-[0.75rem] text-muted-foreground' : 'text-foreground/80')}>
                  {v === null ? '未报美元' : say(v, metric)}
                </span>
              </span>
              <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-foreground/[0.06]">
                {v !== null && v > 0 && (
                  <span className="block h-full rounded-full transition-[width] duration-500 ease-out motion-reduce:transition-none"
                        style={{ width: `${Math.max(1.5, (v / max) * 100)}%`,
                                 background: 'linear-gradient(90deg, var(--spend), color-mix(in oklab, var(--spend-glow) 80%, var(--spend)))' }} />
                )}
              </span>
            </>
          )
          const click = 'onClick' in r ? r.onClick : undefined
          return (
            <li key={r.key}>
              {click
                ? <button type="button" onClick={click} className="block w-full rounded-md text-left outline-none hover:[&_span.truncate]:text-primary focus-visible:ring-2 focus-visible:ring-ring/60">{body}</button>
                : <div>{body}</div>}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/** 一排小片（范围、看法）：选中的那片抬起来（白底、细投影），其余淡字 */
function Segmented<T extends string | number>({ label, value, options, onChange }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex shrink-0 rounded-full bg-foreground/[0.05] p-0.5 ring-1 ring-inset ring-foreground/[0.06]">
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={o.value === value} onClick={() => onChange(o.value)}
                className={cn('rounded-full px-2.5 py-0.5 text-[0.75rem] transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/60',
                              o.value === value ? 'bg-card font-medium text-foreground shadow-[0_1px_2px_rgb(0_0_0/0.08)]' : 'text-muted-foreground hover:text-foreground')}>
          {o.label}
        </button>
      ))}
    </div>
  )
}
