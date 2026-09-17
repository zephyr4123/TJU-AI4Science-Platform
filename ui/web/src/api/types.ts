// 与 `framework/chat/boards.py`、`server.py` 的响应体一一对应。改后端字段先改这里，页面才会跟着编译不过。

export type Direction = 'minimize' | 'maximize'
export type Stage = 'drafting' | 'published' | 'designed' | 'baselined'

export interface PublishState {
  ok: boolean
  /** ok：钥匙有效；missing：从没发布过；invalid：发布过但签的文件改了，reason 说是哪个 */
  state: 'ok' | 'missing' | 'invalid'
  by: string | null
  at: string | null
  reason: string | null
}

export interface PrimaryMetric {
  name: string
  direction: Direction
  attainable: number | null
}

export interface TaskSummary {
  id: string
  title: string
  question: string
  domain: string
  metric: PrimaryMetric | null
  stage: Stage
  publish: PublishState
}

export interface Headroom {
  metric?: string
  direction?: Direction
  baseline?: number
  sigma?: number
  gate?: number
  attainable?: number | null
  room?: number | null
  gates?: number | null
  problems: string[]
  summary: string | null
}

export interface TaskDetail extends TaskSummary {
  manifest: Record<string, unknown>
  design: string
  intake_problems: string[]
  headroom: Headroom | null
}

export interface Acceptance {
  accepted_at: string
  by: string
  best_iter: number
  best_metric: number
  best_commit: string
  verify: string | null
  stale: boolean
}

export interface VerifyState {
  status: 'PASS' | 'FAIL' | 'invalid'
  error?: string
  checks?: unknown
}

/** `cap ... --detach` 起的一个后台作业（`GET /jobs[/<id>]`）。`status` 是记录里写的，
 *  `effective_status` 探过 pid：记录说 running 但进程不在了就是 lost。 */
export interface Job {
  job_id: string
  cap: string
  level: 'task' | 'run' | 'project'
  target: string
  argv: string[]
  pid: number
  started_at: string
  status: 'running' | 'done' | 'failed'
  effective_status: 'running' | 'done' | 'failed' | 'lost'
  finished_at: string | null
  exit_code: number | null
  result: string
  chat_id: string | null
  log: string
}

/** run 照的那条流与走到第几步（`cap start --workflow`）；`waiting` 是现算的：
 *  `job:<id>` 等作业、`key:publish|accept` 等人按键、`human` 等人、`assistant` 轮到助理、`done` 走完。 */
export interface FlowState {
  workflow: string
  title: string
  step: number
  total: number
  steps: WorkflowStep[]
  next: WorkflowStep | null
  waiting: string
  updated_at: string | null
}

export interface RunSummary {
  run_id: string
  task: string | null
  title: string
  metric: { name: string; direction: Direction }
  baseline: number | null
  best_metric: number
  best_iter: number
  last_iter: number
  stop_reason: string | null
  updated_at: string | null
  cost_usd: number | null
  running: boolean
  /** 正在跑的后台作业；没有就是 null */
  job: Job | null
  /** 照的流与步序；没照流就是 null */
  flow: FlowState | null
  analysis: boolean
  verify: VerifyState | null
  accept: Acceptance | null
}

export type LedgerStatus =
  | 'keep' | 'discard' | 'timeout' | 'crash' | 'no_results' | 'readonly_violated'
  | 'noop' | 'interrupted' | 'executor_failed' | string

export interface LedgerRow {
  iter: number
  commit: string
  parent: string
  metric: number | null
  direction: Direction
  elapsed_s: number | null
  seed: number
  status: LedgerStatus
  sigma: number | null
  harness_sha: string
  note: string
  cost_usd: number | null
  executor_s: number | null
}

export interface RunDetail extends RunSummary {
  ledger: LedgerRow[]
  /** 这个 run 的全部作业，按起的先后 */
  jobs: Job[]
  journal: string
  analysis_text: string | null
}

export interface ChatMeta {
  chat_id: string
  /** 第一轮人说的第一句；还没说过话是 null */
  title: string | null
  backend: string
  cwd: string
  created_at: string
  session_id: string | null
  turns: number
  cost_usd: number
}

export interface TurnRecord {
  turn: number
  message: string
  reply: string
}

export interface ChatDoc extends ChatMeta {
  transcript: string
  /** 落盘的问答，一轮一条；`turns` 仍是 meta 里的计数 */
  history: TurnRecord[]
}

export type EventKind = 'init' | 'text' | 'tool_use' | 'tool_result' | 'denied' | 'done' | 'error'

export interface ChatEvent {
  kind: EventKind
  text: string
  tool: string
  tool_input: Record<string, unknown>
  is_error: boolean
  session_id: string | null
  cost_usd: number | null
  duration_s: number
  exit_code: number | null
}

export interface CapabilityFile {
  name: string
  path: string
  description: string
}

export interface CapabilityParam {
  name: string
  description?: string
  default?: unknown
  type?: string
}

/** 七个科研阶段之一（`GET /stages` 给顺序）；能力描述符的 `stage` 取值。 */
export type ResearchStage = string

export interface Capability {
  name: string
  /** 属于哪个科研阶段：标签，不定先后 */
  stage: ResearchStage
  level: 'task' | 'run' | 'project'
  /** 给研究者看的名字与一句说明；`summary` 是给工程师与助理看的机制说明 */
  title: string
  what: string
  summary: string
  inputs: CapabilityFile[]
  outputs: CapabilityFile[]
  params: CapabilityParam[]
  needs_executor: boolean
  needs_compute: boolean
  criteria: string[]
  /** 目标目录由它新建（起任务包）；其余能力要求目标已存在 */
  creates_target: boolean
  /** 用在哪几条工作流里：后端从工作流文件反查的，能力自己不写 */
  used_by: string[]
}

export interface FlowCheck {
  steps: string[]
  covers: ResearchStage[]
  remarks: string[]
  problems: string[]
}

export interface WorkflowStep {
  by: '人' | '助理'
  does: string
  cap: string | null
  key: 'publish' | 'accept' | null
}

export interface Workflow {
  name: string
  title: string
  summary: string
  steps: WorkflowStep[]
  /** 覆盖哪几个科研阶段，按步骤顺序：从能力步骤算出来的 */
  covers: ResearchStage[]
  /** 提醒，不是问题：比如做了实验没验证 */
  remarks: string[]
  problems: string[]
}
