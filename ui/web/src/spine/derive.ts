// 脊柱上每一步长什么样，全由盘上的状态算出来：run 的便条（flow）、作业、两颗键的记录、任务包的阶段。
// 纯函数，不碰 React；页面「装什么流长什么样」靠它，不写死任何一条流（外层 #58 #64）。
import type { FlowState, RunSummary, TaskSummary, Workflow, WorkflowStep } from '@/api/types'

export type StepState = 'done' | 'running' | 'assistant' | 'wait-key' | 'wait-human' | 'todo'

export interface StepView {
  n: number
  by: string
  does: string
  cap: string | null
  key: string | null
  with: Record<string, unknown>
  state: StepState
}

function view(step: WorkflowStep, n: number, state: StepState): StepView {
  return { n, by: step.by, does: step.does, cap: step.cap, key: step.key, with: step.with ?? {}, state }
}

/** run 照的那条流：便条说走到第几步、在等谁；键步骤看记录（键不是能力，便条不会替它推进）。 */
export function deriveRunSteps(flow: FlowState, run: Pick<RunSummary, 'accept'>): StepView[] {
  const accepted = run.accept !== null && !run.accept.stale
  return flow.steps.map((step, i) => {
    const n = i + 1
    if (step.key === 'accept' && accepted) return view(step, n, 'done')
    if (n <= flow.step) return view(step, n, 'done')
    if (n !== flow.step + 1) return view(step, n, 'todo')
    if (flow.waiting.startsWith('job:')) return view(step, n, 'running')
    if (flow.waiting.startsWith('key:')) return view(step, n, 'wait-key')
    if (flow.waiting === 'human') return view(step, n, 'wait-human')
    return view(step, n, 'assistant')
  })
}

/** 没照流的老 run：按 auto-research 的样子从文件推一条出来，让它也有脊柱。 */
export function synthesizeFlow(run: RunSummary, template: Workflow): FlowState {
  const doneCaps = new Set<string>(['start'])
  if (run.last_iter > 0) doneCaps.add('experiment')
  if (run.analysis) doneCaps.add('analysis')
  if (run.verify && run.verify.status !== 'invalid') doneCaps.add('verify')
  let step = 0
  for (const s of template.steps) {
    if (s.cap && doneCaps.has(s.cap)) step += 1
    else break
  }
  const following = template.steps[step] ?? null
  const waiting = run.job ? `job:${run.job.job_id}` : following === null ? 'done'
    : following.key ? `key:${following.key}` : following.cap === null ? 'human' : 'assistant'
  return { workflow: template.name, title: template.title, step, total: template.steps.length,
           steps: template.steps, next: following, waiting, updated_at: run.updated_at }
}

/** 还没有 run：脊柱就是需求对齐——接一个新课题那条流，状态从任务包的阶段与两颗键推。 */
export function deriveIntakeSteps(intake: Workflow, task: TaskSummary | null,
                                  problems: string[] | null): StepView[] {
  const stage = task?.stage ?? null
  const rank = stage === null ? -1 : ['drafting', 'published', 'designed', 'baselined'].indexOf(stage)
  const filled = task !== null && problems !== null && problems.length === 0
  const published = task?.publish.ok === true
  let firstOpen = true // 第一个没完成的步骤才是「轮到谁」，后面的都是 todo
  const mark = (done: boolean, open: StepState): StepState => {
    if (done) return 'done'
    if (!firstOpen) return 'todo'
    firstOpen = false
    return open
  }
  return intake.steps.map((step, i) => {
    const n = i + 1
    if (step.cap === 'init') return view(step, n, mark(task !== null, 'assistant'))
    if (step.key === 'publish') return view(step, n, mark(published, 'wait-key'))
    if (step.cap === 'design') return view(step, n, mark(rank >= 2, 'assistant'))
    if (step.cap === 'baseline') return view(step, n, mark(rank >= 3, 'assistant'))
    if (step.cap) return view(step, n, mark(false, 'assistant'))
    // 纯人的事 / 助理填模板：按它在流里的位置——前面都完成了就轮到它
    if (step.by === '助理') return view(step, n, mark(filled, 'assistant'))
    const humanDone = n === 1 ? task !== null : rank >= 3
    return view(step, n, mark(humanDone, 'wait-human'))
  })
}

/** 脊柱标题下那句话：走到哪、在等谁。 */
export function waitingSentence(steps: StepView[]): string {
  const open = steps.find((s) => s.state !== 'done' && s.state !== 'todo')
  if (!open) return steps.length > 0 && steps.every((s) => s.state === 'done') ? '这条流走完了' : ''
  switch (open.state) {
    case 'running': return `第 ${open.n} 步跑着，跑完助理会来说`
    case 'assistant': return `第 ${open.n} 步轮到助理`
    case 'wait-key': return `第 ${open.n} 步等你${open.key === 'publish' ? '发布' : '验收'}`
    case 'wait-human': return `第 ${open.n} 步轮到你`
    default: return ''
  }
}
