// 编辑台的库那一半（外层 #58 #68 #74 #98）：上面是工作流墙（一流一卡），下面是七间房的货架 + 拼流台。
// 拼流就是排房间、往房间里挂能力、房间之间插断点（纲领 P-18）：点货架上的房间名加一间，点能力挂进去，
// 边拼边问后端有没有问题（POST /workflows/check），存成 workflows/<name>.yaml。三张清单都从后端读，页面不写死。
// 左边那位造流助理每说完一轮 epoch 加一，墙就重读——它可能刚存了一条。
import { ArrowDown, ArrowUp, CaretDown, HandPalm, X } from '@phosphor-icons/react'
import { createElement, type ReactNode, useState } from 'react'

import { api } from '@/api/client'
import { ASSETS } from '@/assets'
import type { Capability, DraftItem, FlowItem, Workflow, WorkflowDraft } from '@/api/types'
import { Band } from '@/components/Band'
import { Empty, ErrorNote, Problems, Skeleton } from '@/components/bits'
import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { LEVEL_COPY } from '@/lib/humanize'
import { actorOf, coverageSentence, groupByStage, itemIcon, itemLabel, stageIcon } from '@/lib/stages'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

/** 拼流台上的一项：与后端的 FlowItem 同形，只是断点还没分出是不是出厂的那两个（那是后端按「发布」「验收」认的） */
type BenchItem = { kind: 'room'; stage: string; caps: string[] } | { kind: 'stop'; note: string }
interface Draft { name: string; title: string; summary: string; items: BenchItem[] }
const EMPTY: Draft = { name: '', title: '', summary: '', items: [] }

/** 五栏的标题，顺序与后端 `COLUMNS` 一致 */
const COLUMNS: [keyof Pick<Capability, 'does' | 'does_not' | 'brings' | 'leaves' | 'stops'>, string][] = [
  ['does', '干什么'], ['does_not', '不干什么'], ['brings', '要带什么进来'], ['leaves', '留下什么'], ['stops', '什么时候停'],
]

export function Studio({ epoch }: { epoch: number }) {
  const stages = useResource(api.stages, [])
  const workflows = useResource(api.workflows, [epoch])
  const catalog = useResource(api.capabilities, [])
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const loading = [stages, workflows, catalog].some((r) => r.loading && !r.data)
  const titles = new Map<string, string>()
  for (const cap of catalog.data ?? []) titles.set(cap.name, cap.title)
  const titleOf = (name: string) => titles.get(name)

  /** 点货架上的能力：最后一项是同一间就挂进去，否则新开一间 */
  const hang = (cap: Capability) => setDraft((d) => {
    const last = d.items[d.items.length - 1]
    if (last && last.kind === 'room' && last.stage === cap.stage) {
      if (last.caps.includes(cap.name)) return d
      return { ...d, items: [...d.items.slice(0, -1), { ...last, caps: [...last.caps, cap.name] }] }
    }
    return { ...d, items: [...d.items, { kind: 'room', stage: cap.stage, caps: [cap.name] }] }
  })
  const addRoom = (stage: string) => setDraft((d) => ({ ...d, items: [...d.items, { kind: 'room', stage, caps: [] }] }))

  return (
    <div>
      <Band picture={ASSETS.studio} veil="foot" className="h-44">
        <header className="mx-auto flex h-full max-w-[76rem] flex-col justify-end px-8 pb-5">
          <h1 className="font-serif text-[1.5rem] font-semibold">库</h1>
          <p className="t-body mt-1 text-muted-foreground">排房间，挂能力，插断点，存进库。</p>
        </header>
      </Band>
      <div className="mx-auto max-w-[76rem] space-y-12 px-8 py-8">
      {stages.error && <ErrorNote text={stages.error} />}
      {workflows.error && <ErrorNote text={workflows.error} />}
      {catalog.error && <ErrorNote text={catalog.error} />}
      {loading && <Skeleton lines={6} />}

      {workflows.data && (
        <section className="space-y-4">
          <h2 className="t-lede">工作流 {workflows.data.length}</h2>
          {workflows.data.length === 0 && <Empty title="还没有工作流" />}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {workflows.data.map((wf) => (
              <WorkflowCard key={wf.name} workflow={wf} titleOf={titleOf}
                            onLoad={() => setDraft(fromWorkflow(wf))} />
            ))}
          </div>
        </section>
      )}

      {catalog.data && stages.data && (
        <section className="grid gap-8 lg:grid-cols-[1fr_24rem]">
          <div className="min-w-0 space-y-4">
            <h2 className="t-lede">七间房 · 能力 {catalog.data.length}</h2>
            <p className="t-body text-muted-foreground">点房间名加一间；点能力挂进最后一间。</p>
            <ol className="flex gap-3 overflow-x-auto pb-2">
              {groupByStage(stages.data, catalog.data).map(({ stage, caps }) => (
                <li key={stage} className="w-[12rem] shrink-0 space-y-2">
                  <button type="button" onClick={() => addRoom(stage)} title={`加一间${stage}`}
                          className="flex w-full items-center gap-1.5 rounded-lg px-1 py-1 text-left font-serif text-[0.9375rem] font-semibold transition-colors hover:bg-accent/40">
                    <StageMark stage={stage} className="text-primary" />{stage}
                  </button>
                  {caps.length === 0
                    ? <p className="rounded-xl border border-dashed px-3 py-4 text-[0.8125rem] text-muted-foreground">这一间还没有能力</p>
                    : caps.map((cap) => <CapChip key={cap.name} cap={cap} onHang={() => hang(cap)} />)}
                </li>
              ))}
            </ol>
          </div>
          <Bench draft={draft} setDraft={setDraft} titleOf={titleOf} stages={stages.data}
                 onSaved={() => void workflows.reload()} />
        </section>
      )}
      </div>
    </div>
  )
}

/** 一间的图标：货架的标题、能力卡、工作流卡上走过的几间都用它 */
function StageMark({ stage, className }: { stage: string; className?: string }) {
  return createElement(stageIcon(stage), { weight: 'duotone', 'aria-label': stage, className: cn('size-4 shrink-0', className) })
}

// ── 工作流墙 ──────────────────────────────────────────────────────────────
function WorkflowCard({ workflow, titleOf, onLoad }: { workflow: Workflow; titleOf: (cap: string) => string | undefined; onLoad: () => void }) {
  return (
    <SpotlightCard spotlight="color-mix(in oklab, var(--primary) 14%, transparent)" className="flex flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-serif text-[1.0625rem] font-semibold">{workflow.title}</h3>
        <span className="flex shrink-0 gap-1 pt-1 text-primary">
          {workflow.covers.map((stage) => <StageMark key={stage} stage={stage} />)}
        </span>
      </div>
      <p className="mt-0.5 font-mono text-[0.75rem] text-muted-foreground">{workflow.name}</p>
      <p className="mt-2 text-[0.875rem] leading-relaxed">{workflow.summary}</p>
      <p className="t-label mt-2">{coverageSentence(workflow.covers)}</p>
      <ol className="mt-3 space-y-1 text-[0.8125rem] text-muted-foreground">
        {workflow.rooms.map((item, i) => (
          <li key={i} className="flex items-center gap-2">
            {createElement(itemIcon(item), { className: 'size-3.5 shrink-0', 'aria-hidden': true })}
            <span className={cn('min-w-0 truncate', item.kind === 'stop' && 'text-wait')}>
              {item.kind === 'stop' ? `停：${itemLabel(item, titleOf)}` : itemLabel(item, titleOf)}
            </span>
          </li>
        ))}
      </ol>
      {workflow.remarks.map((remark) => <p key={remark} className="mt-2 text-[0.8125rem] text-wait">{remark}</p>)}
      <Problems items={workflow.problems} />
      <div className="mt-4 flex justify-end">
        <Button variant="outline" size="sm" onClick={onLoad}>照着拼</Button>
      </div>
    </SpotlightCard>
  )
}

/** 货架上的一颗能力：点标题挂进拼流台，点箭头展开五栏。 */
function CapChip({ cap, onHang }: { cap: Capability; onHang: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl border bg-card">
      <div className="flex items-start">
        <button type="button" onClick={onHang}
                className="flex min-w-0 flex-1 items-start gap-2 rounded-l-xl px-3 py-2.5 text-left transition-colors hover:bg-accent/40">
          <StageMark stage={cap.stage} className="mt-1 text-muted-foreground" />
          <span className="min-w-0">
            <span className="block text-[0.9375rem] font-medium">{cap.title}</span>
            <span className="mt-0.5 block text-[0.75rem] text-muted-foreground">{actorOf(cap)}，{LEVEL_COPY[cap.level]}</span>
          </span>
        </button>
        <button type="button" aria-label={open ? '收起说明' : '展开说明'} aria-expanded={open} onClick={() => setOpen((v) => !v)}
                className="grid size-9 shrink-0 place-items-center rounded-r-xl text-muted-foreground hover:bg-accent/40 hover:text-foreground">
          <CaretDown className={cn('size-3.5 transition-transform duration-200', open && 'rotate-180')} />
        </button>
      </div>
      {open && (
        <dl className="space-y-2 border-t px-3 py-2.5 text-[0.75rem] leading-relaxed">
          {COLUMNS.map(([key, label]) => (
            <div key={key}>
              <dt className="font-medium text-foreground">{label}</dt>
              <dd className="text-muted-foreground">{cap[key]}</dd>
            </div>
          ))}
          {cap.params.length > 0 && (
            <div>
              <dt className="font-medium text-foreground">参数</dt>
              <dd className="font-mono text-muted-foreground">{cap.params.map((p) => p.name).join(' · ')}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  )
}

// ── 拼流台 ────────────────────────────────────────────────────────────────
function Bench({ draft, setDraft, titleOf, stages, onSaved }: {
  draft: Draft; setDraft: (f: (d: Draft) => Draft) => void; titleOf: (cap: string) => string | undefined
  stages: string[]; onSaved: () => void
}) {
  const doc = toDraft(draft)
  const key = JSON.stringify(doc.rooms)
  const check = useResource(() => (draft.items.length ? api.checkWorkflow(doc) : Promise.resolve(null)), [key])
  const [busy, setBusy] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const update = (i: number, patch: Partial<BenchItem>) =>
    setDraft((d) => ({ ...d, items: d.items.map((s, j) => (j === i ? ({ ...s, ...patch } as BenchItem) : s)) }))
  const remove = (i: number) => setDraft((d) => ({ ...d, items: d.items.filter((_, j) => j !== i) }))
  const move = (i: number, dir: -1 | 1) => setDraft((d) => {
    const items = [...d.items]
    const j = i + dir
    if (j < 0 || j >= items.length) return d
    ;[items[i], items[j]] = [items[j], items[i]]
    return { ...d, items }
  })
  const unhang = (i: number, cap: string) => setDraft((d) => ({
    ...d, items: d.items.map((s, j) => (j === i && s.kind === 'room' ? { ...s, caps: s.caps.filter((c) => c !== cap) } : s)),
  }))
  const addStop = (text: string) => setDraft((d) => ({ ...d, items: [...d.items, { kind: 'stop', note: text }] }))

  const save = async () => {
    setBusy(true)
    setNote(null)
    try {
      const saved = await api.saveWorkflow({ ...doc, overwrite })
      setNote({ ok: true, text: `已存：${saved.name}` })
      onSaved()
    } catch (exc) {
      setNote({ ok: false, text: exc instanceof Error ? exc.message : String(exc) })
    } finally {
      setBusy(false)
    }
  }
  const problems = check.data?.problems ?? []
  const canSave = draft.name.trim() !== '' && draft.title.trim() !== '' && draft.summary.trim() !== ''
    && draft.items.length > 0 && problems.length === 0 && !busy

  return (
    <aside className="self-start rounded-2xl border bg-card p-5 lg:sticky lg:top-6">
      <h2 className="font-serif text-[1.0625rem] font-semibold">拼流台</h2>
      <div className="mt-3 space-y-2">
        <Input value={draft.name} placeholder="名字（小写英文、连字符）" aria-label="工作流名字"
               className="bg-card font-mono" onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
        <Input value={draft.title} placeholder="标题" aria-label="工作流标题" className="bg-card"
               onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} />
        <Input value={draft.summary} placeholder="一句话说明" aria-label="工作流说明" className="bg-card"
               onChange={(e) => setDraft((d) => ({ ...d, summary: e.target.value }))} />
      </div>
      <ol className="mt-4 space-y-2">
        {draft.items.length === 0 && (
          <li className="rounded-xl border border-dashed px-3 py-4 text-[0.8125rem] text-muted-foreground">
            从左边点房间或能力。
          </li>
        )}
        {draft.items.map((item, i) => (
          <li key={i} className={cn('flex items-start gap-2 rounded-xl border px-3 py-2', item.kind === 'stop' ? 'border-wait/60 bg-wait-soft' : 'bg-card')}>
            <span className="mt-1 w-4 shrink-0 text-right text-[0.8125rem] font-semibold tabular">{item.kind === 'stop' ? '◆' : i + 1}</span>
            <div className="min-w-0 flex-1">
              {item.kind === 'room' ? (
                <>
                  <div className="flex items-center gap-1.5 text-[0.875rem] font-medium"><StageMark stage={item.stage} className="text-primary" />{item.stage}</div>
                  {item.caps.length === 0
                    ? <p className="mt-0.5 text-[0.75rem] text-muted-foreground">不点名，助理看着办</p>
                    : (
                      <ul className="mt-1 flex flex-wrap gap-1">
                        {item.caps.map((cap) => (
                          <li key={cap} className="flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-[0.75rem]">
                            {titleOf(cap) ?? cap}
                            <button type="button" aria-label={`去掉 ${titleOf(cap) ?? cap}`} onClick={() => unhang(i, cap)}
                                    className="text-muted-foreground hover:text-foreground"><X className="size-3" /></button>
                          </li>
                        ))}
                      </ul>
                    )}
                </>
              ) : (
                <>
                  <div className="flex items-center gap-1.5 text-[0.875rem] font-medium text-wait"><HandPalm className="size-4" />断点</div>
                  <input value={item.note} aria-label={`第 ${i + 1} 项要人确认什么`} placeholder="要人确认什么（「发布」「验收」是出厂的两个）"
                         onChange={(e) => update(i, { note: e.target.value })}
                         className="w-full bg-transparent text-[0.8125rem] outline-none placeholder:text-muted-foreground focus-visible:underline" />
                </>
              )}
            </div>
            <span className="flex shrink-0 gap-0.5">
              <IconButton label="上移" onClick={() => move(i, -1)}><ArrowUp /></IconButton>
              <IconButton label="下移" onClick={() => move(i, 1)}><ArrowDown /></IconButton>
              <IconButton label="去掉" onClick={() => remove(i)}><X /></IconButton>
            </span>
          </li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => addStop('')}>加断点</Button>
        <Button variant="outline" size="sm" onClick={() => addStop('发布')}>发布</Button>
        <Button variant="outline" size="sm" onClick={() => addStop('验收')}>验收</Button>
      </div>
      <div className="mt-4 space-y-1.5 text-[0.8125rem]">
        {draft.items.length > 0 && check.data && (
          <p className={cn(problems.length ? 'text-bad' : 'text-ok')}>
            {problems.length ? '有问题' : `没问题，${coverageSentence(check.data.covers)}`}
          </p>
        )}
        {check.data?.remarks.map((r) => <p key={r} className="text-wait">{r}</p>)}
        <Problems items={problems} />
        {check.error && <ErrorNote text={check.error} />}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <label className="flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground">
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          覆盖同名
        </label>
        <Button onClick={() => void save()} disabled={!canSave}>{busy ? '保存中' : '保存'}</Button>
      </div>
      {note && <p className={cn('mt-3 text-[0.8125rem] leading-relaxed', note.ok ? 'text-ok' : 'text-bad')}>{note.text}</p>}
      <p className="mt-3 text-[0.75rem] text-muted-foreground">{stages.length} 间房任意排，房间之间不接管子。</p>
    </aside>
  )
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" aria-label={label} onClick={onClick}
            className="grid size-6 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground [&_svg]:size-3.5">
      {children}
    </button>
  )
}

/** 拼流台 → 文件同形的 JSON：不点名的房间一个名字、点名的一个清单、断点一个词或「断点: 一句话」。 */
function toDraft(draft: Draft): WorkflowDraft {
  const rooms: DraftItem[] = draft.items.map((item) => {
    if (item.kind === 'stop') return item.note.trim() ? { 断点: item.note.trim() } : '断点'
    return item.caps.length ? { [item.stage]: item.caps } : item.stage
  })
  return { name: draft.name.trim(), title: draft.title.trim(), summary: draft.summary.trim(), rooms }
}

function fromWorkflow(wf: Workflow): Draft {
  return {
    name: `${wf.name}-2`, title: wf.title, summary: wf.summary,
    items: wf.rooms.map(fromItem),
  }
}

function fromItem(item: FlowItem): BenchItem {
  if (item.kind === 'stop') return { kind: 'stop', note: item.note }
  // 参数在页面上还没有位置：照着拼时只带名字，参数由取走的研究助理改（P-15）
  return { kind: 'room', stage: item.stage, caps: item.caps.map((c) => c.cap) }
}
