// 编辑台：改「库」的地方（外层 #58 #68）。上面是工作流墙（一流一卡），下面是七段能力货架 + 拼流台：
// 点货架上的能力进拼流台，通不通当场问后端，存成 workflows/<name>.yaml。三张清单都从后端读，页面不写死。
import { ArrowDown, ArrowUp, X } from 'lucide-react'
import { type ReactNode, useState } from 'react'

import { api } from '@/api/client'
import type { Capability, Workflow, WorkflowDraft } from '@/api/types'
import { Empty, ErrorNote, Problems, Skeleton } from '@/components/bits'
import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { LEVEL_COPY } from '@/lib/humanize'
import { actorOf, coverageSentence, groupByStage } from '@/lib/stages'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

type DraftStep = WorkflowDraft['steps'][number]
interface Draft { name: string; title: string; summary: string; steps: DraftStep[] }
const EMPTY: Draft = { name: '', title: '', summary: '', steps: [] }

export function Studio() {
  const stages = useResource(api.stages, [])
  const workflows = useResource(api.workflows, [])
  const catalog = useResource(api.capabilities, [])
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const loading = [stages, workflows, catalog].some((r) => r.loading && !r.data)
  const titles = new Map<string, string>()
  for (const cap of catalog.data ?? []) titles.set(cap.name, cap.title)

  return (
    <div className="mx-auto max-w-[76rem] space-y-12 px-8 py-8">
      <header>
        <h1 className="font-serif text-[1.375rem] font-semibold">编辑台</h1>
        <p className="t-body mt-1 text-muted-foreground">
          这里改的是库：平台是一盒能力，工作流是预装好的拼法。拼一条自己的，存成文件，主页面就能照着跑。
        </p>
      </header>
      {stages.error && <ErrorNote text={stages.error} />}
      {workflows.error && <ErrorNote text={workflows.error} />}
      {catalog.error && <ErrorNote text={catalog.error} />}
      {loading && <Skeleton lines={6} />}

      {workflows.data && (
        <section className="space-y-4">
          <h2 className="t-lede">工作流墙：{workflows.data.length} 条</h2>
          {workflows.data.length === 0 && <Empty title="还没有工作流。" hint="workflows/ 目录里一个文件一条。" />}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {workflows.data.map((wf) => (
              <WorkflowCard key={wf.name} workflow={wf} titles={titles}
                            onLoad={() => setDraft(fromWorkflow(wf))} />
            ))}
          </div>
        </section>
      )}

      {catalog.data && stages.data && (
        <section className="grid gap-8 lg:grid-cols-[1fr_24rem]">
          <div className="min-w-0 space-y-4">
            <h2 className="t-lede">七段货架：{catalog.data.length} 颗能力</h2>
            <p className="t-body text-muted-foreground">
              每颗能力属于做科研的某一段，段只是标签不定先后。点一颗，它就进右边的拼流台。
            </p>
            <ol className="flex gap-3 overflow-x-auto pb-2">
              {groupByStage(stages.data, catalog.data).map(({ stage, caps }) => (
                <li key={stage} className="w-[10.5rem] shrink-0 space-y-2">
                  <h3 className="font-serif text-[0.9375rem] font-semibold">{stage}</h3>
                  {caps.length === 0
                    ? <p className="rounded-xl border border-dashed px-3 py-4 text-[0.8125rem] text-muted-foreground">还没有这一段的能力</p>
                    : caps.map((cap) => (
                      <CapChip key={cap.name} cap={cap}
                               onClick={() => setDraft((d) => ({ ...d, steps: [...d.steps, capStep(cap)] }))} />
                    ))}
                </li>
              ))}
            </ol>
          </div>
          <Bench draft={draft} setDraft={setDraft} titles={titles}
                 onSaved={() => void workflows.reload()} />
        </section>
      )}
    </div>
  )
}

// ── 工作流墙 ──────────────────────────────────────────────────────────────
function WorkflowCard({ workflow, titles, onLoad }: { workflow: Workflow; titles: Map<string, string>; onLoad: () => void }) {
  return (
    <SpotlightCard spotlight="color-mix(in oklab, var(--primary) 14%, transparent)" className="flex flex-col p-5">
      <h3 className="font-serif text-[1.0625rem] font-semibold">{workflow.title}</h3>
      <p className="mt-0.5 font-mono text-[0.75rem] text-muted-foreground">{workflow.name}</p>
      <p className="mt-2 text-[0.875rem] leading-relaxed">{workflow.summary}</p>
      <p className="t-label mt-2">{coverageSentence(workflow.covers)}，{workflow.steps.length} 步</p>
      <ol className="mt-3 space-y-1 text-[0.8125rem] text-muted-foreground">
        {workflow.steps.map((step, i) => (
          <li key={i} className="flex gap-2">
            <span className="w-4 shrink-0 text-right tabular">{i + 1}</span>
            <span className="min-w-0 truncate">
              {step.by === '人' ? '你' : '助理'}{step.key ? `按${step.key === 'publish' ? '发布' : '验收'}键` : ''}
              {step.cap ? `：${titles.get(step.cap) ?? step.cap}` : `：${step.does}`}
            </span>
          </li>
        ))}
      </ol>
      {workflow.remarks.map((remark) => <p key={remark} className="mt-2 text-[0.8125rem] text-wait">{remark}</p>)}
      <Problems items={workflow.problems} />
      <div className="mt-4 flex justify-end">
        <Button variant="outline" size="sm" onClick={onLoad}>照这条拼</Button>
      </div>
    </SpotlightCard>
  )
}

function CapChip({ cap, onClick }: { cap: Capability; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
            className="block w-full rounded-xl border bg-card px-3 py-2.5 text-left transition-colors hover:border-primary/60 hover:bg-accent/40">
      <span className="block text-[0.9375rem] font-medium">{cap.title}</span>
      <span className="mt-0.5 block text-[0.75rem] text-muted-foreground">{actorOf(cap)}，{LEVEL_COPY[cap.level]}</span>
    </button>
  )
}

// ── 拼流台 ────────────────────────────────────────────────────────────────
function Bench({ draft, setDraft, titles, onSaved }: {
  draft: Draft; setDraft: (f: (d: Draft) => Draft) => void; titles: Map<string, string>; onSaved: () => void
}) {
  const caps = draft.steps.flatMap((s) => (s.cap ? [s.cap] : []))
  const check = useResource(() => (caps.length ? api.flowCheck(caps) : Promise.resolve(null)), [caps.join(',')])
  const [busy, setBusy] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const update = (i: number, patch: Partial<DraftStep>) =>
    setDraft((d) => ({ ...d, steps: d.steps.map((s, j) => (j === i ? { ...s, ...patch } : s)) }))
  const remove = (i: number) => setDraft((d) => ({ ...d, steps: d.steps.filter((_, j) => j !== i) }))
  const move = (i: number, dir: -1 | 1) => setDraft((d) => {
    const steps = [...d.steps]
    const j = i + dir
    if (j < 0 || j >= steps.length) return d
    ;[steps[i], steps[j]] = [steps[j], steps[i]]
    return { ...d, steps }
  })
  const add = (step: DraftStep) => setDraft((d) => ({ ...d, steps: [...d.steps, step] }))

  const save = async () => {
    setBusy(true)
    setNote(null)
    try {
      const saved = await api.saveWorkflow({ ...draft, overwrite })
      setNote({ ok: true, text: `存好了：workflows/${saved.name}.yaml。主页面开实验时带 --workflow ${saved.name} 就照它跑。` })
      onSaved()
    } catch (exc) {
      setNote({ ok: false, text: exc instanceof Error ? exc.message : String(exc) })
    } finally {
      setBusy(false)
    }
  }
  const problems = check.data?.problems ?? []
  const canSave = draft.name.trim() !== '' && draft.title.trim() !== '' && draft.summary.trim() !== ''
    && draft.steps.length > 0 && problems.length === 0 && !busy

  return (
    <aside className="paper-grid self-start rounded-2xl border p-5 lg:sticky lg:top-6">
      <h2 className="font-serif text-[1.0625rem] font-semibold">拼流台</h2>
      <div className="mt-3 space-y-2">
        <Input value={draft.name} placeholder="名字，小写英文加连字符，就是文件名" aria-label="工作流名字"
               className="bg-card font-mono" onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
        <Input value={draft.title} placeholder="人话标题" aria-label="工作流标题" className="bg-card"
               onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} />
        <Input value={draft.summary} placeholder="一句话：这条流什么时候用" aria-label="工作流说明" className="bg-card"
               onChange={(e) => setDraft((d) => ({ ...d, summary: e.target.value }))} />
      </div>
      <ol className="mt-4 space-y-2">
        {draft.steps.length === 0 && (
          <li className="rounded-xl border border-dashed px-3 py-4 text-[0.8125rem] text-muted-foreground">
            还是空的。点左边货架上的能力，或者加一步人的事。
          </li>
        )}
        {draft.steps.map((step, i) => (
          <li key={i} className="flex items-start gap-2 rounded-xl border bg-card px-3 py-2">
            <span className="mt-1 w-4 shrink-0 text-right text-[0.8125rem] font-semibold tabular">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="text-[0.75rem] text-muted-foreground">
                {step.by}{step.cap ? `按「${titles.get(step.cap) ?? step.cap}」` : step.key ? `按${step.key === 'publish' ? '发布' : '验收'}键` : ''}
              </div>
              <input value={step.does} aria-label={`第 ${i + 1} 步做什么`}
                     onChange={(e) => update(i, { does: e.target.value })}
                     className="w-full bg-transparent text-[0.875rem] outline-none focus-visible:underline" />
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
        <Button variant="outline" size="sm" onClick={() => add({ by: '人', does: '看一眼，决定下一步' })}>加一步人的事</Button>
        <Button variant="outline" size="sm" onClick={() => add({ by: '人', does: '看一遍需求，署名发布', key: 'publish' })}>加发布键</Button>
        <Button variant="outline" size="sm" onClick={() => add({ by: '人', does: '看一眼结果，署名验收', key: 'accept' })}>加验收键</Button>
      </div>
      <div className="mt-4 space-y-1.5 text-[0.8125rem]">
        {caps.length > 0 && check.data && (
          <p className={cn(problems.length ? 'text-bad' : 'text-ok')}>
            {problems.length ? '这样摆不通' : `通。${coverageSentence(check.data.covers)}`}
          </p>
        )}
        {check.data?.remarks.map((r) => <p key={r} className="text-wait">{r}</p>)}
        <Problems items={problems} />
        {check.error && <ErrorNote text={check.error} />}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <label className="flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground">
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          同名就覆盖
        </label>
        <Button onClick={() => void save()} disabled={!canSave}>{busy ? '存着…' : '存成文件'}</Button>
      </div>
      {note && <p className={cn('mt-3 text-[0.8125rem] leading-relaxed', note.ok ? 'text-ok' : 'text-bad')}>{note.text}</p>}
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

function capStep(cap: Capability): DraftStep {
  return { by: '助理', does: cap.title, cap: cap.name }
}
function fromWorkflow(wf: Workflow): Draft {
  return {
    name: `${wf.name}-2`, title: wf.title, summary: wf.summary,
    steps: wf.steps.map((s) => ({ by: s.by, does: s.does, ...(s.cap ? { cap: s.cap } : {}),
                                  ...(s.key ? { key: s.key } : {}), ...(Object.keys(s.with ?? {}).length ? { with: s.with } : {}) })),
  }
}
