// 首页右栏下半「花费」（外层 #256）：近 7 / 30 / 90 天花了多少。上半横着摆：左边四个数（成本、调用、token、缓存命中），
// 右边按天的柱子；下半四张表换着看（项目、模型、会话、定价，借 cc-switch 用量页的分法），表在面里滚、高度不变，
// 右栏不越拉越长。一块暖调的玻璃（玫红、杏色，与左边项目清单的靛、青对着映衬）；数据只用一种颜色（柱子从玫红渐到杏色），
// 表里只有字与数，不画长短条（主人 2026-10-06：数都写着了，条子说不清是什么）。成本是按 API 公开价折算的：Claude Code
// 自己报，Codex 不报、照「定价」那张表算，订阅账号不是实扣；模型没记的算不出，写「未知」不当 0。换范围时上一份淡着顶住。
import { ChatCenteredText, Info, Lightning } from '@phosphor-icons/react'
import { type ReactNode, useState } from 'react'

import type { SpendCell, SpendPrice, SpendSession, Spending as SpendingDoc } from '@/api/types'
import { Aurora } from '@/components/Aurora'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { money, when } from '@/lib/format'
import { useEdgeFade } from '@/lib/useEdgeFade'
import type { Resource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { type Bucket, buckets, hitRate, type Metric, perMillion, type Range, RANGES, sorted, tokens, valueOf } from './usage'

const FOOTNOTE = '按 API 公开价折算：Claude Code 自己报，Codex 照「定价」那张表算；订阅账号不是实扣'

export function Spending({ usage, range, onRange, metric, onMetric, onOpenProject, onOpenWorkspace }: {
  usage: Resource<SpendingDoc>
  range: Range
  onRange: (r: Range) => void
  metric: Metric
  onMetric: (m: Metric) => void
  onOpenProject: (id: string) => void
  onOpenWorkspace: (project: string, workspace: string) => void
}) {
  // 换范围时新的那份还没回来：上一份淡着顶住（不闪骨架）；记上一份用渲染时更新的 state（React 的「记住上一次」写法）
  const [held, setHeld] = useState<SpendingDoc | null>(usage.data)
  if (usage.data && usage.data !== held) setHeld(usage.data)
  const doc = usage.data ?? held
  const stale = !usage.data && held !== null
  return (
    <Aurora tone="warm" className="h-full">
      <section aria-label="花费" className="px-5 pt-4 pb-4">
        <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h2 className="mr-auto font-serif text-[1.0625rem] font-semibold">花费</h2>
          <Segmented label="看法" value={metric} onChange={onMetric}
                     options={[{ value: 'usd', label: '成本' }, { value: 'tokens', label: 'token' }]} />
          <Segmented label="时间范围" value={range} onChange={onRange}
                     options={RANGES.map((r) => ({ value: r, label: `${r} 天` }))} />
        </header>
        {usage.error && !doc && <ErrorNote text={usage.error} className="mt-4" />}
        {!doc && !usage.error && <div className="mt-4"><Skeleton lines={6} /></div>}
        {doc && (
          <div className={cn('transition-opacity duration-200', stale && 'opacity-55')}>
            <div className="mt-4 grid gap-x-7 gap-y-4 sm:grid-cols-[15rem_minmax(0,1fr)]">
              <Figures doc={doc} />
              {doc.total.count === 0
                ? <p className="self-center text-[0.875rem] text-muted-foreground">近 {doc.days} 天没有调用</p>
                : <Columns bars={buckets(doc.by_day)} metric={metric} />}
            </div>
            {doc.total.count > 0 && <Sheets doc={doc} metric={metric} onOpenProject={onOpenProject} onOpenWorkspace={onOpenWorkspace} />}
          </div>
        )}
      </section>
    </Aurora>
  )
}

/** 看法的读法：成本两位小数；token 用万与亿 */
function say(value: number, metric: Metric): string {
  return metric === 'usd' ? money(value) : tokens(value)
}

/** 一格的成本：算不出写「未知」（淡字），不当 $0 */
function Cost({ cell }: { cell: SpendCell }) {
  return cell.cost_usd === null
    ? <span className="text-muted-foreground" title="模型没记，算不出">未知</span>
    : <span>{money(cell.cost_usd)}</span>
}

/** 左边四个数，两行两列：成本（有算不出的另写几次）、调用（对话与运行各几次）、token、缓存命中 */
function Figures({ doc }: { doc: SpendingDoc }) {
  const total = doc.total
  const rate = hitRate(total)
  return (
    <dl className="grid grid-cols-2 content-start gap-x-4 gap-y-4">
      <Figure label={<span className="flex items-center gap-1" title={FOOTNOTE}>成本<Info className="size-3.5 cursor-help" aria-label={FOOTNOTE} /></span>}
              value={total.cost_usd === null ? '—' : money(total.cost_usd)}
              note={total.unknown > 0 ? `${total.unknown} 次算不出` : '折算'} />
      <Figure label="调用" value={total.count.toLocaleString('zh-CN')} unit="次"
              note={doc.by_kind.map((k) => `${k.title} ${k.count}`).join(' · ')} />
      <Figure label="token" value={tokens(total.tokens)} />
      <Figure label="缓存命中" value={rate === null ? '—' : `${Math.round(rate * 100)}`} unit={rate === null ? undefined : '%'} />
    </dl>
  )
}

function Figure({ label, value, unit, note }: { label: ReactNode; value: string; unit?: string; note?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.75rem] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate text-[1.375rem] leading-tight font-semibold tracking-tight tabular">
        {value}{unit && <span className="ml-0.5 text-[0.8125rem] font-medium text-muted-foreground">{unit}</span>}
      </dd>
      {note && <dd className="mt-0.5 truncate text-[0.6875rem] text-muted-foreground tabular">{note}</dd>}
    </div>
  )
}

/** 按天（或按周）的柱子：一个系列一种颜色；悬停那根亮、别的淡，右上角读出那天的数；有调用却算不出成本的那天柱脚一个灰点 */
function Columns({ bars, metric }: { bars: Bucket[]; metric: Metric }) {
  const [hover, setHover] = useState<number | null>(null)
  const values = bars.map((b) => valueOf(b, metric) ?? 0)
  const max = Math.max(...values, 0)
  const labelled = bars.length <= 7 ? bars.map((_, i) => i) : [0, Math.floor((bars.length - 1) / 2), bars.length - 1]
  const shown = hover === null ? null : bars[hover]
  return (
    <figure aria-label={`按${bars.length > 31 ? '周' : '天'}的${metric === 'usd' ? '成本' : ' token'}`}>
      {/* 头一行：左边纵轴的顶（最高那根是多少），右边悬停那根的读数——写在卡里，不浮出去被卡的圆角裁掉 */}
      <div className="flex h-4 items-baseline justify-between gap-3 text-[0.6875rem] tabular">
        <span className="text-muted-foreground">{max > 0 ? say(max, metric) : ''}</span>
        {shown && <Readout bucket={shown} metric={metric} />}
      </div>
      <div className="flex h-[7.5rem] items-end gap-[2px] border-b border-foreground/10 pt-1" onMouseLeave={() => setHover(null)}>
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
      <div className="relative mt-1.5 h-4 text-[0.6875rem] text-muted-foreground tabular">
        {labelled.map((i) => <Tick key={i} label={bars[i].label} at={(i + 0.5) / bars.length} edge={bars.length > 7 && (i === 0 ? 'start' : i === bars.length - 1 ? 'end' : null)} />)}
      </div>
      <table className="sr-only">
        <tbody>{bars.map((b) => <tr key={b.label}><th>{b.label}</th><td>{b.cost_usd === null ? '未知' : money(b.cost_usd)}</td><td>{tokens(b.tokens)} token</td></tr>)}</tbody>
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

/** 悬停那根的读数：哪天（哪周）、这种看法的数、几次调用、几次算不出 */
function Readout({ bucket, metric }: { bucket: Bucket; metric: Metric }) {
  const v = valueOf(bucket, metric)
  return (
    <span aria-live="polite" className="flex min-w-0 items-center gap-1.5 truncate text-foreground/80">
      <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-spend" />
      <span className="font-medium">{bucket.label}</span>
      <span>{bucket.count === 0 ? '没有调用' : say(v ?? 0, metric)}</span>
      {bucket.count > 0 && <span className="text-muted-foreground">· {bucket.count} 次{metric === 'usd' && bucket.unknown > 0 ? `，${bucket.unknown} 次算不出` : ''}</span>}
    </span>
  )
}

type Sheet = 'projects' | 'models' | 'sessions' | 'pricing'

/** 下半四张表换着看，表头一排字签；表在固定高的面里滚（换签不改卡的高，两栏才齐） */
function Sheets({ doc, metric, onOpenProject, onOpenWorkspace }: {
  doc: SpendingDoc; metric: Metric
  onOpenProject: (id: string) => void
  onOpenWorkspace: (project: string, workspace: string) => void
}) {
  const [sheet, setSheet] = useState<Sheet>('projects')
  const tabs: [Sheet, string, number | null][] = [
    ['projects', '项目', doc.by_project.length], ['models', '模型', doc.by_model.length],
    ['sessions', '会话', doc.sessions.length], ['pricing', '定价', null],
  ]
  return (
    <Tabs value={sheet} onValueChange={(v) => setSheet(v as Sheet)} className="mt-5 gap-3">
      <TabsList variant="line" className="h-7 gap-5 p-0">
        {tabs.map(([value, label, n]) => (
          <TabsTrigger key={value} value={value}
                       className="flex-none px-0 text-[0.8125rem] after:rounded-full after:bg-spend group-data-horizontal/tabs:after:bottom-[-3px] data-active:font-semibold">
            {label}{n !== null && <span className="font-normal text-muted-foreground tabular">{n}</span>}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="projects"><Projects rows={sorted(doc.by_project, metric)} onOpen={onOpenProject} /></TabsContent>
      <TabsContent value="models"><Models rows={sorted(doc.by_model, metric)} /></TabsContent>
      <TabsContent value="sessions"><Sessions rows={doc.sessions} onOpenProject={onOpenProject} onOpenWorkspace={onOpenWorkspace} /></TabsContent>
      <TabsContent value="pricing"><Pricing rows={doc.pricing} /></TabsContent>
    </Tabs>
  )
}

function Projects({ rows, onOpen }: { rows: SpendingDoc['by_project']; onOpen: (id: string) => void }) {
  return (
    <Grid label="按项目" cols={FOUR} head={['项目', '调用', 'token', '成本']} content={rows}>
      {rows.map((p) => (
        <Row key={p.id ?? ''} cols={FOUR} onClick={p.id ? () => onOpen(p.id!) : undefined} name={p.title}>
          <Lead>{p.title}</Lead>
          <Num minor>{p.count}</Num><Num>{tokens(p.tokens)}</Num><Num><Cost cell={p} /></Num>
        </Row>
      ))}
    </Grid>
  )
}

function Models({ rows }: { rows: SpendingDoc['by_model'] }) {
  return (
    <Grid label="按模型" cols={FOUR} head={['模型', '缓存命中', 'token', '成本']} content={rows}>
      {rows.map((m) => {
        const rate = hitRate(m)
        return (
          <Row key={`${m.backend}/${m.model}`} cols={FOUR}>
            <Lead kicker={m.backend_title}>{m.model_title}</Lead>
            <Num minor>{rate === null ? '—' : `${Math.round(rate * 100)}%`}</Num><Num>{tokens(m.tokens)}</Num><Num><Cost cell={m} /></Num>
          </Row>
        )
      })}
    </Grid>
  )
}

/** 最近的会话：一段对话、一次运行各一行；名字底下一行淡字是几时、几轮、在哪（长的放最后，截断也只截它）。点运行进那个工作区，点对话进那个项目 */
function Sessions({ rows, onOpenProject, onOpenWorkspace }: {
  rows: SpendSession[]
  onOpenProject: (id: string) => void
  onOpenWorkspace: (project: string, workspace: string) => void
}) {
  return (
    <Grid label="最近的会话" cols={SESSION} head={['会话', '模型', 'token', '成本']} content={rows}>
      {rows.map((s) => {
        const run = s.kind === 'run'
        const open = run && s.project && s.workspace ? () => onOpenWorkspace(s.project!, s.workspace!)
          : !run && s.project ? () => onOpenProject(s.project!) : undefined
        const where = run ? s.workspace_title ?? s.project_title : s.project_title
        const name = s.title ?? '对话'
        return (
          <Row key={s.key} cols={SESSION} onClick={open} name={name}>
            <span role="cell" className="flex min-w-0 items-start gap-2">
              {run
                ? <Lightning weight="fill" aria-label="运行" className="mt-[3px] size-3.5 shrink-0 text-spend/80" />
                : <ChatCenteredText weight="fill" aria-label="对话" className="mt-[3px] size-3.5 shrink-0 text-muted-foreground/70" />}
              <span className="min-w-0">
                <span className="block truncate">{name}</span>
                <span className="block truncate text-[0.6875rem] text-muted-foreground tabular">
                  {when(s.at)} · {s.count} {run ? '次' : '轮'} · {where}
                </span>
              </span>
            </span>
            <Num minor muted>{s.model_title}</Num>
            <Num>{tokens(s.tokens)}</Num><Num><Cost cell={s} /></Num>
          </Row>
        )
      })}
    </Grid>
  )
}

/** 两家的定价表：每百万 token 的公开价；底下一句说它怎么用 */
function Pricing({ rows }: { rows: SpendPrice[] }) {
  return (
    <Grid label="定价（每百万 token）" cols={FOUR} head={['模型 · 每百万 token', '输入', '命中缓存', '输出']} minor={2} content={rows}
          foot="API 公开价。Claude Code 自己报成本；Codex 不报，照这张表折算">
      {rows.map((p) => (
        <Row key={`${p.backend}/${p.model}`} cols={FOUR}>
          <Lead kicker={p.backend_title}>{p.model_title}</Lead>
          <Num>{perMillion(p.input)}</Num><Num minor>{perMillion(p.cached)}</Num><Num>{perMillion(p.output)}</Num>
        </Row>
      ))}
    </Grid>
  )
}

// 表的列：名字占剩下的，数字列定宽右对齐；窄屏收起第二列（次要的那列），名字才不被挤成两个字
const FOUR = 'grid-cols-[minmax(0,1fr)_4.5rem_4.5rem] sm:grid-cols-[minmax(0,1fr)_4.25rem_4.5rem_4.5rem]'
const SESSION = 'grid-cols-[minmax(0,1fr)_4.5rem_4.5rem] sm:grid-cols-[minmax(0,1fr)_6.5rem_4.5rem_4.5rem]'

/** 一张表：表头一行淡字，表身在固定高的面里滚，哪头还有那头渐隐；不画分隔线，行与行靠留白分。`minor` 是窄屏收起的那列 */
function Grid({ label, cols, head, minor = 1, content, foot, children }: {
  label: string; cols: string; head: string[]; minor?: number; content: unknown; foot?: string; children: ReactNode
}) {
  const fade = useEdgeFade<HTMLDivElement>(content)
  return (
    <div role="table" aria-label={label} className="text-[0.8125rem]">
      <div role="row" className={cn('grid gap-x-3 px-2 pb-1 text-[0.6875rem] text-muted-foreground', cols)}>
        {head.map((h, i) => (
          <span role="columnheader" key={h} className={cn(i > 0 && 'text-right', i === minor && 'max-sm:hidden')}>{h}</span>
        ))}
      </div>
      <div role="rowgroup" {...fade} className="h-[12.5rem] overflow-y-auto overscroll-contain [scrollbar-width:thin]">
        {children}
        {foot && <p className="px-2 pt-2 pb-1 text-[0.6875rem] leading-relaxed text-muted-foreground">{foot}</p>}
      </div>
    </div>
  )
}

/** 一行：能点的整行都是点的地方（名字那格前面一枚透明的键铺满整行），鼠标在哪行哪行垫一层淡底 */
function Row({ cols, onClick, name, children }: { cols: string; onClick?: () => void; name?: string; children: ReactNode }) {
  return (
    <div role="row" className={cn('relative grid items-center gap-x-3 rounded-lg px-2 py-1.5 tabular', cols,
                                  onClick && 'hover:bg-foreground/[0.04] has-focus-visible:ring-2 has-focus-visible:ring-ring/60')}>
      {onClick && <button type="button" onClick={onClick} aria-label={`打开 ${name}`} className="absolute inset-0 rounded-lg outline-none" />}
      {children}
    </div>
  )
}

/** 名字那格：前面可以带一个淡的出处（哪家，窄屏收起——模型名自己看得出是哪家），名字过长截断 */
function Lead({ kicker, children }: { kicker?: string; children: ReactNode }) {
  return (
    <span role="cell" className="min-w-0 truncate">
      {kicker && <span className="text-muted-foreground max-sm:hidden">{kicker} · </span>}{children}
    </span>
  )
}

/** 数字那格：右对齐；`minor` 是窄屏收起的那列（与表头的 `minor` 对上） */
function Num({ minor, muted, children }: { minor?: boolean; muted?: boolean; children: ReactNode }) {
  return <span role="cell" className={cn('truncate text-right', muted ? 'text-muted-foreground' : 'text-foreground/85', minor && 'max-sm:hidden')}>{children}</span>
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
