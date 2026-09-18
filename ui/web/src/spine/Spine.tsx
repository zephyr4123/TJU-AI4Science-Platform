// 流程脊柱：主页面右边那一列，全页唯一放胆的地方（外层 #64 #67 #74）。
// 只读一个工作区（P-15）：有 run 就是当前 run 照的那条流，一步一个模块，模块的实心程度来自盘上真实的文件；
// 没有 run 时就是需求对齐，看这个工作区的任务包。
// 装什么流长什么样：这里不写死任何一条流，步骤从 run 的便条（或工作流文件）来，状态由 derive.ts 算。
import { type ReactNode, useState } from 'react'

import { api } from '@/api/client'
import type { FlowState, RunDetail, RunSummary, TaskDetail, Workflow, WorkspaceDetail } from '@/api/types'
import { ErrorNote, Problems, Skeleton } from '@/components/bits'
import ElectricBorder from '@/components/reactbits/ElectricBorder'
import ShinyText from '@/components/reactbits/ShinyText'
import { AcceptKey } from '@/keys/AcceptKey'
import { PublishKey } from '@/keys/PublishKey'
import { metric } from '@/lib/format'
import { conclusionOf, stopSentence } from '@/lib/humanize'
import { useToken } from '@/lib/tokens'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { deriveIntakeSteps, deriveRunSteps, type StepView, synthesizeFlow, waitingSentence } from './derive'

export function Spine({ workspace, epoch }: { workspace: string; epoch: number }) {
  const doc = useResource(() => api.workspace(workspace), [workspace, epoch])
  const workflows = useResource(api.workflows, [])
  const [pickedRun, setPickedRun] = useState<string | null>(null)

  const error = doc.error ?? workflows.error
  if (error) return <div className="p-6"><ErrorNote text={error} /></div>
  if (!doc.data || !workflows.data) return <div className="p-6"><Skeleton lines={6} /></div>

  const byRecent = [...doc.data.runs].sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''))
  const run = (pickedRun ? byRecent.find((r) => r.run_id === pickedRun) : undefined) ?? byRecent[0] ?? null
  if (run) {
    return <RunSpine workspace={workspace} run={run} runs={byRecent} onPick={setPickedRun}
                     workflows={workflows.data} epoch={epoch} />
  }
  const intake = workflows.data.find((w) => w.name === 'intake') ?? null
  return <IntakeSpine workspace={doc.data} intake={intake} reload={doc.reload} />
}

// ── run：照的那条流 ────────────────────────────────────────────────────────
function RunSpine({ workspace, run, runs, onPick, workflows, epoch }: {
  workspace: string; run: RunSummary; runs: RunSummary[]; onPick: (id: string) => void; workflows: Workflow[]
  epoch: number
}) {
  const detail = useResource(() => api.run(workspace, run.run_id), [workspace, run.run_id, epoch])
  if (detail.error) return <div className="p-6"><ErrorNote text={detail.error} /></div>
  if (!detail.data) return <div className="p-6"><Skeleton lines={6} /></div>
  const doc = detail.data
  const template = workflows.find((w) => w.name === 'auto-research') ?? workflows[0] ?? null
  const flow: FlowState | null = doc.flow ?? (template ? synthesizeFlow(doc, template) : null)
  if (!flow) return <div className="p-6"><ErrorNote text="没有流可对照" /></div>
  const steps = deriveRunSteps(flow, doc)
  return (
    <Column
      title={flow.title}
      subtitle={`${run.run_id}，${waitingSentence(steps) || `第 ${flow.step} 步`}`}
      picker={runs.length > 1 && (
        <Picker value={run.run_id} options={runs.map((r) => r.run_id)} onChange={onPick} label="换 run" />
      )}
    >
      {steps.map((step, i) => (
        <StepModule key={step.n} step={step} last={i === steps.length - 1}
                    ok={step.cap === 'verify' && doc.verify?.status === 'PASS'}>
          <RunStepContent workspace={workspace} step={step} run={doc} reload={detail.reload} />
        </StepModule>
      ))}
    </Column>
  )
}

function RunStepContent({ workspace, step, run, reload }: {
  workspace: string; step: StepView; run: RunDetail; reload: () => Promise<void>
}) {
  const indigo = useToken('--primary')
  const muted = useToken('--muted-foreground')
  const delta = run.baseline !== null ? run.baseline - run.best_metric : null
  if (step.state === 'todo') return <Hint>{tail(step.does)}</Hint>
  if (step.key === 'accept') return <AcceptKey workspace={workspace} run={run} reload={reload} />
  switch (step.cap) {
    case 'start':
      return <Fact>起点 {metric(run.baseline)}</Fact>
    case 'experiment':
      if (step.state === 'running') {
        return (
          <>
            {run.last_iter > 0 && <Pair from={run.baseline} to={run.best_metric} />}
            <ShinyText text={`第 ${run.last_iter + 1} 轮跑着`} color={muted} shineColor={indigo}
                       speed={2.5} className="text-[0.8125rem]" />
          </>
        )
      }
      if (run.last_iter === 0) return <Hint>{tail(step.does)}</Hint>
      return (
        <>
          <Pair from={run.baseline} to={run.best_metric} />
          <Fact>
            最好第 {run.best_iter} 轮，共 {run.last_iter} 轮
            {delta !== null && delta > 0 ? `，好了 ${metric(delta, 4)}` : ''}。{stopSentence(run.stop_reason, run.running)}
          </Fact>
        </>
      )
    case 'analysis':
      if (step.state === 'running') {
        return <ShinyText text="写分析中" color={muted} shineColor={indigo} speed={2.5} className="text-[0.8125rem]" />
      }
      if (!run.analysis_text) return <Hint>{tail(step.does)}</Hint>
      return (
        <>
          <p className="line-clamp-3 text-[0.875rem] leading-relaxed">{plain(conclusionOf(run.analysis_text))}</p>
          {run.verify === null && <p className="mt-1 text-[0.8125rem] text-muted-foreground">未验证</p>}
        </>
      )
    case 'verify':
      if (!run.verify) return <Hint>{tail(step.does)}</Hint>
      if (run.verify.status === 'PASS') return <Fact className="text-ok">数字全部可回溯</Fact>
      if (run.verify.status === 'FAIL') return <Fact className="text-bad">有数字对不上</Fact>
      return <Fact className="text-bad">报告坏了，重跑</Fact>
    default:
      return <Hint>{step.state === 'wait-human' ? `轮到你：${tail(step.does)}` : tail(step.does)}</Hint>
  }
}

// ── 需求对齐：还没有 run ─────────────────────────────────────────────────
function IntakeSpine({ workspace, intake, reload }: {
  workspace: WorkspaceDetail; intake: Workflow | null; reload: () => Promise<void>
}) {
  if (!intake) return <div className="p-6"><ErrorNote text="库里没有 intake" /></div>
  const task = workspace.task
  const steps = deriveIntakeSteps(intake, task, task?.intake_problems ?? null)
  return (
    <Column
      title={intake.title}
      subtitle={task ? waitingSentence(steps) : '还没有需求'}
    >
      {steps.map((step, i) => (
        <StepModule key={step.n} step={step} last={i === steps.length - 1}>
          <IntakeStepContent workspace={workspace.id} step={step} task={task} reload={reload} />
        </StepModule>
      ))}
    </Column>
  )
}

function IntakeStepContent({ workspace, step, task, reload }: {
  workspace: string; step: StepView; task: TaskDetail | null; reload: () => Promise<void>
}) {
  if (step.key === 'publish' && task && step.state !== 'todo') {
    return <PublishKey workspace={workspace} task={task} reload={reload} />
  }
  if (step.state === 'todo' || !task) {
    return <Hint>{step.state === 'wait-human' ? `轮到你：${tail(step.does)}` : tail(step.does)}</Hint>
  }
  if (step.cap === 'init') return <Fact>已起，材料在 task/data/</Fact>
  if (step.by === '助理' && step.cap === null) {
    return (
      <>
        <p className="text-[0.9375rem] font-medium">{task.title}</p>
        <p className="mt-0.5 line-clamp-2 text-[0.8125rem] leading-relaxed text-muted-foreground">{task.question}</p>
        {task.intake_problems.length > 0 && <div className="mt-2"><Problems items={task.intake_problems} tone="warn" /></div>}
      </>
    )
  }
  if (step.cap === 'design') {
    return <Fact>{step.state === 'done' ? '裁判脚本已封' : tail(step.does)}</Fact>
  }
  if (step.cap === 'baseline') {
    const h = task.headroom
    if (step.state === 'done' && h?.baseline !== undefined) {
      return (
        <Fact>
          起点 {metric(h.baseline)}，抖动 {metric(h.sigma, 3)}，门 {metric(h.gate, 3)}
          {h.gates != null ? `，离尽头 ${h.gates.toFixed(1)} 个门` : ''}
        </Fact>
      )
    }
    return <Hint>{tail(step.does)}</Hint>
  }
  return <Hint>{step.state === 'wait-human' ? `轮到你：${tail(step.does)}` : tail(step.does)}</Hint>
}

// ── 零件 ──────────────────────────────────────────────────────────────────
function Column({ title, subtitle, picker, children }: {
  title: string; subtitle: string; picker?: ReactNode; children: ReactNode
}) {
  return (
    <div className="relative flex h-full flex-col">
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 z-[1] h-10 bg-gradient-to-b from-background to-transparent" />
      <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-10 bg-gradient-to-t from-background to-transparent" />
      <div className="px-6 pt-6 pb-4">
        <h2 className="font-serif text-[1.125rem] leading-snug font-semibold">{title}</h2>
        <p className="mt-1 text-[0.8125rem] text-muted-foreground">{subtitle}</p>
        {picker}
      </div>
      <ol className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-6 pb-8">{children}</ol>
    </div>
  )
}

function Picker({ value, options, onChange, label }: {
  value: string; options: string[]; onChange: (v: string) => void; label: string
}) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
            className="mt-2 h-7 max-w-full rounded-md border bg-card px-2 font-mono text-[0.75rem] text-muted-foreground">
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  )
}

const BUBBLE: Record<StepView['state'], string> = {
  done: 'bg-foreground text-background',
  running: 'bg-primary text-primary-foreground',
  assistant: 'border-[1.5px] border-primary text-primary',
  'wait-key': 'bg-wait text-white',
  'wait-human': 'bg-wait text-white',
  todo: 'border-[1.5px] border-dashed border-muted-foreground text-muted-foreground',
}

function StepModule({ step, last, ok = false, children }: {
  step: StepView; last: boolean; ok?: boolean; children: ReactNode
}) {
  const indigo = useToken('--primary')
  const waiting = step.state === 'wait-key' || step.state === 'wait-human'
  const box = (
    <div className={cn('rounded-xl border px-4 py-3',
      step.state === 'todo' ? 'border-dashed bg-transparent' : 'bg-card',
      step.state === 'assistant' && 'border-primary/50',
      waiting && 'border-wait/60 bg-wait-soft',
      step.state === 'running' && 'border-transparent')}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className={cn('t-step', step.state === 'todo' && 'text-muted-foreground', waiting && 'text-wait')}>
          {head(step.does)}
        </h3>
        {step.state === 'assistant' && <span className="text-[0.75rem] text-primary">轮到助理</span>}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  )
  return (
    <li className="relative grid grid-cols-[28px_1fr] gap-3">
      <span className={cn('grid size-7 place-items-center rounded-full text-[0.8125rem] font-semibold',
                          BUBBLE[step.state], ok && step.state === 'done' && 'bg-ok text-white')}>
        {step.n}
      </span>
      {!last && <span aria-hidden className="absolute top-[30px] bottom-[-14px] left-[13px] w-0.5 bg-border" />}
      {step.state === 'running'
        ? <ElectricBorder color={indigo} speed={0.5} chaos={0.06} borderRadius={12}>{box}</ElectricBorder>
        : box}
    </li>
  )
}

function Pair({ from, to }: { from: number | null; to: number }) {
  return (
    <p className="t-big flex items-baseline gap-2">
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
/** 步骤的 does 是一句话，冒号前是标题，后面是说明。 */
function head(does: string): string {
  const i = does.indexOf('：')
  return i > 0 && i <= 14 ? does.slice(0, i) : does
}
function tail(does: string): string {
  const i = does.indexOf('：')
  return i > 0 && i <= 14 ? does.slice(i + 1) : ''
}
