// 流程脊柱：主页面右边那一列（外层 #64 #67 #74 #82 #98）。只读一个工作区（P-15），一块板几条泳道：
// 顶上一条是任务包那一段（流开头的假设 / 设计阶段与断点），下面每个 run 一条（照的那条流的全部阶段），取了还没开跑的流
// 一行薄的「备着」。默认全部收着；只有助理正在承接的那条——作业在跑，或当前对话开的、还没走完——自动展开，展开才拉详情，
// 一个阶段一个模块，模块的实心程度来自盘上真实的文件。人点哪条展开哪条，点过的以人为准。对话不绑流：流走到哪写在盘上，谁驱动的都一样。
// 装什么流长什么样：这里不写死任何一条流，阶段与断点从 run 的进度记录（或流文件）来，状态由 derive.ts 算。
import { CaretDown } from '@phosphor-icons/react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { createElement, type ReactNode, useEffect, useState } from 'react'

import { api } from '@/api/client'
import type { FlowItem, RunDetail, RunSummary, TaskDetail, Workflow, WorkspaceDetail } from '@/api/types'
import { Dot, ErrorNote, Problems, Skeleton } from '@/components/bits'
import { FoldText } from '@/components/reactbits/FoldText'
import ElectricBorder from '@/components/reactbits/ElectricBorder'
import ShinyText from '@/components/reactbits/ShinyText'
import { AcceptKey } from '@/keys/AcceptKey'
import { PublishKey } from '@/keys/PublishKey'
import { metric } from '@/lib/format'
import { conclusionOf, stopSentence } from '@/lib/humanize'
import { itemIcon, itemLabel } from '@/lib/stages'
import { useToken } from '@/lib/tokens'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { deriveRunItems, deriveTaskItems, type ItemView, synthesizeFlow, taskPart, waitingSentence } from './derive'

/** 有作业在跑时多久重拉一次摘要：别的对话起的作业跑完，这边才看得见 */
const POLL_MS = 10_000

type TitleOf = (cap: string) => string | undefined

export function Spine({ workspace, epoch, chatId }: { workspace: string; epoch: number; chatId: string | null }) {
  const doc = useResource(() => api.workspace(workspace), [workspace, epoch])
  const workflows = useResource(api.workflows, [])
  // 能力清单只为一件事：点名的能力显示人话标题
  const caps = useResource(api.capabilities, [])
  // 人点过的以人为准；没点过的按「承接中」自动
  const [manual, setManual] = useState<Record<string, boolean>>({})

  const busy = doc.data?.runs.some((r) => r.job !== null) ?? false
  const reload = doc.reload
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => { void reload() }, POLL_MS)
    return () => clearInterval(timer)
  }, [busy, reload])

  const error = doc.error ?? workflows.error ?? caps.error
  if (error) return <div className="p-6"><ErrorNote text={error} /></div>
  if (!doc.data || !workflows.data || !caps.data) return <div className="p-6"><Skeleton lines={6} /></div>
  const catalog = caps.data
  const titleOf: TitleOf = (name) => catalog.find((c) => c.name === name)?.title
  // 任务包那一段照哪条流：工作区里取来的、从任务包起步的第一条；没有就照库里的；库里也没有就不画这一段
  const startsAtTask = (f: Workflow) => f.problems.length === 0 && taskPart(f.stages).length > 0
  const guide: Workflow | null = doc.data.flows.find(startsAtTask) ?? workflows.data.find(startsAtTask) ?? null
  const runs = [...doc.data.runs].sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''))
  // 老 run 没进度记录时照哪条：库里第一条能用的
  const template = workflows.data.find((f) => f.problems.length === 0) ?? null
  const spare = doc.data.flows.filter((f) => f !== guide && !runs.some((r) => r.flow?.workflow === f.name))
  const task = doc.data.task

  const isOpen = (id: string, auto: boolean) => manual[id] ?? auto
  const toggle = (id: string, auto: boolean) => setManual((m) => ({ ...m, [id]: !isOpen(id, auto) }))
  // 任务包那一段：起了任务包、还没跑到基线，就是助理正在承接的
  const taskAuto = task !== null && task.stage !== 'baselined'
  // 某个 run：作业在跑，或当前对话开的、还没验收
  const runAuto = (run: RunSummary) =>
    run.job !== null || (chatId !== null && run.chat_id === chatId && !(run.accept !== null && !run.accept.stale))

  return (
    <div className="h-full space-y-3 overflow-y-auto px-5 pt-5 pb-8">
      <header className="px-1 pb-1">
        <h2 className="font-serif text-[1.125rem] leading-snug font-semibold"><FoldText text="工作流" /></h2>
      </header>
      {guide && (
        <TaskLane workspace={doc.data} guide={guide} reload={doc.reload} titleOf={titleOf}
                  open={isOpen('task', taskAuto)} onToggle={() => toggle('task', taskAuto)} />
      )}
      {runs.map((run) => (
        <RunLane key={run.run_id} workspace={workspace} run={run} template={template} epoch={epoch} titleOf={titleOf}
                 open={isOpen(run.run_id, runAuto(run))} onToggle={() => toggle(run.run_id, runAuto(run))} />
      ))}
      {spare.map((flow) => (
        <p key={flow.name} className="flex flex-wrap items-baseline gap-x-2 px-4 py-2 text-[0.8125rem] text-muted-foreground">
          <span className="font-serif font-semibold text-foreground/80">{flow.title}</span>
          {flow.problems.length > 0
            ? <span className="text-bad">{flow.problems[0]}</span>
            : <span>{flow.stages.length} 项，未开始</span>}
        </p>
      ))}
    </div>
  )
}

// ── 泳道 ─────────────────────────────────────────────────────────────────
/** 一条流一行：收着只有标题与「走到哪、在等谁」，展开是一项一个模块。 */
function Lane({ title, note, live = false, open, onToggle, children }: {
  title: string; note: string; live?: boolean; open: boolean; onToggle: () => void; children: ReactNode
}) {
  const still = useReducedMotion() === true
  return (
    <section className="rounded-2xl border bg-card/80 backdrop-blur-sm">
      <button type="button" onClick={onToggle} aria-expanded={open}
              className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left transition-colors hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-ring">
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            {live && <Dot tone="primary" pulse />}
            <span className="truncate font-serif text-[1rem] leading-snug font-semibold">{title}</span>
          </span>
          <span className="mt-0.5 block truncate text-[0.8125rem] text-muted-foreground">{note}</span>
        </span>
        <CaretDown aria-hidden="true"
                   className={cn('size-4 shrink-0 text-muted-foreground transition-transform duration-200', open && 'rotate-180')} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div key="body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }} transition={{ duration: still ? 0 : 0.22 }} className="overflow-hidden">
            <ol className="space-y-3.5 px-4 pt-1 pb-4">{children}</ol>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

// ── run：照的那条流 ────────────────────────────────────────────────────────
function RunLane({ workspace, run, template, epoch, titleOf, open, onToggle }: {
  workspace: string; run: RunSummary; template: Workflow | null; epoch: number; titleOf: TitleOf
  open: boolean; onToggle: () => void
}) {
  // 老 run 没进度记录：按库里那条的样子从摘要推一条出来
  const flow = run.flow ?? (template ? synthesizeFlow(run, template.stages, template.name, template.title) : null)
  const items = flow ? deriveRunItems(flow, run) : []
  const where = waitingSentence(items, titleOf) || (flow ? `第 ${flow.step} 项` : '没有流可对照')
  return (
    <Lane title={flow?.title ?? run.title} note={`${run.run_id}，${where}`} live={run.job !== null} open={open} onToggle={onToggle}>
      {open && <RunLaneBody workspace={workspace} run={run} items={items} epoch={epoch} titleOf={titleOf} />}
    </Lane>
  )
}

/** 展开才拉 run 详情：分析的结论、账本这些收着时用不上。 */
function RunLaneBody({ workspace, run, items, epoch, titleOf }: {
  workspace: string; run: RunSummary; items: ItemView[]; epoch: number; titleOf: TitleOf
}) {
  const detail = useResource(() => api.run(workspace, run.run_id), [workspace, run.run_id, epoch, run.updated_at])
  if (detail.error) return <li><ErrorNote text={detail.error} /></li>
  if (!detail.data) return <li><Skeleton lines={4} /></li>
  if (items.length === 0) return <li><ErrorNote text="没有流可对照" /></li>
  const doc = detail.data
  return (
    <>
      {items.map((view, i) => (
        <ItemModule key={view.n} view={view} title={itemLabel(view.item, titleOf)} last={i === items.length - 1}
                    ok={view.item.kind === 'stage' && view.item.stage === '验证' && doc.verify?.status === 'PASS'}>
          <RunItemContent workspace={workspace} view={view} run={doc} reload={detail.reload} />
        </ItemModule>
      ))}
    </>
  )
}

/** 一个阶段里显示这个 run 留下的东西：按阶段名配视图，没配的阶段就是一句状态。 */
function RunItemContent({ workspace, view, run, reload }: {
  workspace: string; view: ItemView; run: RunDetail; reload: () => Promise<void>
}) {
  const { item, state } = view
  if (item.kind === 'stop') {
    if (item.key === 'accept' && state !== 'todo') return <AcceptKey workspace={workspace} run={run} reload={reload} />
    return <StopNote item={item} state={state} />
  }
  const delta = run.baseline !== null ? run.baseline - run.best_metric : null
  if (state === 'todo') return <Hint>还没到</Hint>
  switch (item.stage) {
    case '实验':
      if (state === 'running') {
        return (
          <>
            {run.last_iter > 0 && <Pair from={run.baseline} to={run.best_metric} />}
            <Live text={`第 ${run.last_iter + 1} 轮跑着`} />
          </>
        )
      }
      if (run.last_iter === 0) return <Fact>起点 {metric(run.baseline)}</Fact>
      return (
        <>
          <Pair from={run.baseline} to={run.best_metric} />
          <Fact>
            最好第 {run.best_iter} 轮，共 {run.last_iter} 轮
            {delta !== null && delta > 0 ? `，好了 ${metric(delta, 4)}` : ''}。{stopSentence(run.stop_reason, run.running)}
          </Fact>
        </>
      )
    case '分析':
      if (state === 'running') return <Live text="写分析中" />
      if (!run.analysis_text) return <Hint>轮到助理</Hint>
      return (
        <>
          <p className="line-clamp-3 text-[0.875rem] leading-relaxed">{plain(conclusionOf(run.analysis_text))}</p>
          {run.verify === null && <p className="mt-1 text-[0.8125rem] text-muted-foreground">未验证</p>}
        </>
      )
    case '验证':
      if (!run.verify) return <Hint>{state === 'running' ? '核对中' : '轮到助理'}</Hint>
      if (run.verify.status === 'PASS') return <Fact className="text-ok">数字全部可回溯</Fact>
      if (run.verify.status === 'FAIL') return <Fact className="text-bad">有数字对不上</Fact>
      return <Fact className="text-bad">报告坏了，重跑</Fact>
    default:
      return <Hint>{state === 'done' ? '做完了' : state === 'running' ? '跑着' : '轮到助理'}</Hint>
  }
}

// ── 任务包那一段 ───────────────────────────────────────────────────────────
function TaskLane({ workspace, guide, reload, titleOf, open, onToggle }: {
  workspace: WorkspaceDetail; guide: Workflow; reload: () => Promise<void>; titleOf: TitleOf
  open: boolean; onToggle: () => void
}) {
  const task = workspace.task
  const items = deriveTaskItems(taskPart(guide.stages), task, task?.intake_problems ?? null)
  return (
    <Lane title={task?.title ?? guide.title} note={task ? waitingSentence(items, titleOf) : '还没有需求'} open={open} onToggle={onToggle}>
      {items.map((view, i) => (
        <ItemModule key={view.n} view={view} title={itemLabel(view.item, titleOf)} last={i === items.length - 1}>
          <TaskItemContent workspace={workspace.id} view={view} task={task} reload={reload} />
        </ItemModule>
      ))}
    </Lane>
  )
}

function TaskItemContent({ workspace, view, task, reload }: {
  workspace: string; view: ItemView; task: TaskDetail | null; reload: () => Promise<void>
}) {
  const { item, state } = view
  if (item.kind === 'stop') {
    if (item.key === 'publish' && task && state !== 'todo') return <PublishKey workspace={workspace} task={task} reload={reload} />
    return <StopNote item={item} state={state} />
  }
  if (state === 'todo') return <Hint>还没到</Hint>
  if (!task) return <Hint>轮到助理：起任务包，和你把课题说清</Hint>
  if (item.stage === '假设') {
    return (
      <>
        <p className="text-[0.9375rem] font-medium">{task.title}</p>
        <p className="mt-0.5 line-clamp-2 text-[0.8125rem] leading-relaxed text-muted-foreground">{task.question}</p>
        {task.intake_problems.length > 0 && <div className="mt-2"><Problems items={task.intake_problems} tone="warn" /></div>}
      </>
    )
  }
  if (item.stage === '设计') {
    const h = task.headroom
    if (state === 'done' && h?.baseline !== undefined) {
      return (
        <Fact>
          评分脚本已封。起点 {metric(h.baseline)}，抖动 {metric(h.sigma, 3)}，门 {metric(h.gate, 3)}
          {h.gates != null ? `，离尽头 ${h.gates.toFixed(1)} 个门` : ''}
        </Fact>
      )
    }
    return <Hint>{state === 'done' ? '评分脚本已封' : '轮到助理：写评分脚本、跑基线'}</Hint>
  }
  return <Hint>{state === 'done' ? '做完了' : '轮到助理'}</Hint>
}

/** 断点那一格：要人确认什么；等着的时候把话说给人 */
function StopNote({ item, state }: { item: Extract<FlowItem, { kind: 'stop' }>; state: ItemView['state'] }) {
  if (state === 'done') return <Hint>已确认</Hint>
  if (state === 'todo') return <Hint>{item.key ? '到这儿要你确认' : '到这儿停一下'}</Hint>
  return <Fact className="text-wait">轮到你：看完跟助理说「继续」</Fact>
}

// ── 零件 ──────────────────────────────────────────────────────────────────
const BUBBLE: Record<ItemView['state'], string> = {
  done: 'bg-foreground text-background',
  running: 'bg-primary text-primary-foreground',
  assistant: 'border-[1.5px] border-primary text-primary',
  'wait-key': 'bg-wait text-white',
  'wait-human': 'bg-wait text-white',
  todo: 'border-[1.5px] border-dashed border-muted-foreground text-muted-foreground',
}

/** 跑着的那一项的状态字：闪着的一行；系统要求减少动效就是普通一行。 */
function Live({ text }: { text: string }) {
  const still = useReducedMotion()
  const indigo = useToken('--primary')
  const muted = useToken('--muted-foreground')
  if (still) return <p className="text-[0.8125rem] text-muted-foreground">{text}</p>
  return <ShinyText text={text} color={muted} shineColor={indigo} speed={2.5} className="text-[0.8125rem]" />
}

function ItemModule({ view, title, last, ok = false, children }: {
  view: ItemView; title: string; last: boolean; ok?: boolean; children: ReactNode
}) {
  const indigo = useToken('--primary')
  const still = useReducedMotion()
  const { state } = view
  const waiting = state === 'wait-key' || state === 'wait-human'
  const box = (
    <div className={cn('rounded-xl border px-4 py-3',
      state === 'todo' ? 'border-dashed bg-transparent' : 'bg-card',
      state === 'assistant' && 'border-primary/50',
      waiting && 'border-wait/60 bg-wait-soft',
      state === 'running' && 'border-transparent')}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className={cn('t-step flex items-center gap-2', state === 'todo' && 'text-muted-foreground', waiting && 'text-wait')}>
          {createElement(itemIcon(view.item), {
            weight: state === 'done' ? 'fill' : 'duotone', 'aria-hidden': true,
            className: cn('size-[1.125rem] shrink-0', state === 'done' ? 'text-foreground' : state === 'running' || state === 'assistant' ? 'text-primary' : waiting ? 'text-wait' : 'text-muted-foreground'),
          })}
          {title}
        </h3>
        {state === 'assistant' && <span className="text-[0.75rem] text-primary">轮到助理</span>}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  )
  return (
    <li className="relative grid grid-cols-[28px_minmax(0,1fr)] gap-3">
      <span className={cn('grid size-7 place-items-center rounded-full text-[0.8125rem] font-semibold',
                          BUBBLE[state], ok && state === 'done' && 'bg-ok text-white')}>
        {view.item.kind === 'stop' ? '◆' : view.n}
      </span>
      {!last && <span aria-hidden className="absolute top-[30px] bottom-[-14px] left-[13px] w-0.5 bg-border" />}
      {state === 'running' && !still
        ? <ElectricBorder color={indigo} speed={0.5} chaos={0.06} borderRadius={12}>{box}</ElectricBorder>
        : box}
    </li>
  )
}

function Pair({ from, to }: { from: number | null; to: number }) {
  return (
    <p className="t-big flex flex-wrap items-baseline gap-x-2">
      <span className="text-muted-foreground">{metric(from, 4)}</span>
      <span aria-hidden className="text-muted-foreground">→</span>
      <span>{metric(to, 4)}</span>
    </p>
  )
}
function Fact({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn('text-[0.875rem] leading-relaxed', className)}>{children}</p>
}
function Hint({ children }: { children: ReactNode }) {
  return <p className="text-[0.8125rem] leading-relaxed text-muted-foreground">{children}</p>
}
/** 摘要只要字：去掉 Markdown 的加粗、代码、列表记号。 */
function plain(markdown: string): string {
  return markdown.replace(/[*`#>]/g, '').replace(/^\s*[-+]\s+/gm, '').replace(/\s+/g, ' ').trim()
}
