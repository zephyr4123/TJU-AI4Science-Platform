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

export interface Capability {
  name: string
  level: 'task' | 'run' | 'project'
  summary: string
  inputs: CapabilityFile[]
  outputs: CapabilityFile[]
  params: CapabilityParam[]
  needs_executor: boolean
  needs_compute: boolean
  criteria: string[]
}

export interface FlowCheck {
  steps: string[]
  problems: string[]
}
