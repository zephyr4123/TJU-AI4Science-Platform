// 与 `framework/chat/boards.py`、`server.py` 的响应体一一对应。改后端字段先改这里，页面才会跟着编译不过。

export type Direction = 'minimize' | 'maximize'
export type Stage = 'drafting' | 'published' | 'designed' | 'baselined'

export interface PublishState {
  ok: boolean
  /** ok：发布记录有效；missing：从没发布过；invalid：发布过但签的文件改了，reason 说是哪个 */
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

/** 一个工作区 = 一份需求（`GET /workspaces`）：任务包还没起时 `task` 是 null。 */
export interface WorkspaceSummary {
  id: string
  title: string
  created_at: string | null
  root: string
  task: TaskSummary | null
  /** 几个 run */
  runs: number
}

/** `GET /workspaces/<id>`：任务包细节、从库里取来的流实例、全部 run 的摘要。 */
export interface WorkspaceDetail extends Omit<WorkspaceSummary, 'task' | 'runs'> {
  task: TaskDetail | null
  flows: Workflow[]
  runs: RunSummary[]
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

/** run 照的那条流与走到第几项（`cap auto-research --workflow`）；`waiting` 是现算的：
 *  `job:<id>` 等作业、`key:publish|accept` 停在出厂的两个断点等人、`human` 停在别的断点等人、
 *  `assistant` 轮到助理、`done` 走完。 */
export interface FlowState {
  workflow: string
  title: string
  step: number
  total: number
  stages: FlowItem[]
  next: FlowItem | null
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
  /** 哪段对话开的；终端里开的或老 run 是 null */
  chat_id: string | null
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
  /** 这段对话记着的模型与思考深度；null 是后端缺省（外层 #86） */
  model: string | null
  effort: string | null
}

/** 一轮用什么：发消息、开对话时带上；null 是后端缺省 */
export interface Tuning {
  model: string | null
  effort: string | null
}

/** 旋钮上的一个刻度：`id` 给后端，`label` 给人看，`note` 一句提示（可空） */
export interface Choice {
  id: string
  label: string
  note: string
}

/** 一家 agent 后端的两个旋钮（`GET /backends`）：清单是后端自报的；`model` / `effort` 是不选时实际会用的，null 是 CLI 自己定（页面写「默认」） */
export interface Backend {
  name: string
  default: boolean
  models: Choice[]
  efforts: Choice[]
  model: string | null
  effort: string | null
}

export interface TurnRecord {
  turn: number
  /** 谁开的口：人，或框架（作业跑完来叫醒 agent） */
  origin: '人' | '框架'
  message: string
  reply: string
}

export interface ChatDoc extends ChatMeta {
  transcript: string
  /** 落盘的问答，一轮一条；`turns` 仍是 meta 里的计数 */
  history: TurnRecord[]
}

/** `delta` 是助理正在说的几个字（不是累计），同一段说完会来一条完整的 `text` */
export type EventKind =
  | 'init' | 'delta' | 'text' | 'tool_use' | 'tool_result' | 'denied' | 'done' | 'error'

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

export interface CapabilityParam {
  name: string
  help?: string
  default?: unknown
  type?: string
}

/** 七个研究阶段之一（`GET /stages` 给顺序）；能力描述符的 `stage` 取值。 */
export type ResearchStage = string

/** 一颗能力：一个阶段里的一件活，对助理就是一条命令。五栏是给人读的机制说明（纲领 P-18）。 */
export interface Capability {
  name: string
  /** 属于哪个阶段：标签，不定先后 */
  stage: ResearchStage
  level: 'task' | 'run' | 'project'
  /** 给研究者看的名字 */
  title: string
  does: string
  does_not: string
  brings: string
  leaves: string
  stops: string
  params: CapabilityParam[]
  needs_executor: boolean
  needs_compute: boolean
  /** 点名用在哪几条工作流里：后端从工作流文件反查的，能力自己不写 */
  used_by: string[]
}

/** 流里的一项：一个阶段（可点名能力、带参数），或一个断点（停下来等人确认；发布 / 验收是出厂的两个）。 */
export type FlowItem =
  | { kind: 'stage'; stage: ResearchStage; caps: { cap: string; with: Record<string, unknown> }[] }
  | { kind: 'stop'; key: 'publish' | 'accept' | null; note: string }

/** 编辑台交给 `POST /workflows`（存）与 `POST /workflows/check`（只查）的一条流：形状同文件。
 *  一项是阶段名、`{阶段: [能力]}`、`{阶段: {能力: 参数}}`、`"断点"` 或 `{断点: 一句话}`。 */
export type DraftItem = string | Record<string, string | string[] | Record<string, Record<string, unknown> | null>>
export interface WorkflowDraft {
  name: string
  title: string
  summary: string
  stages: DraftItem[]
  overwrite?: boolean
}

export interface WorkflowCheck {
  covers: ResearchStage[]
  remarks: string[]
  problems: string[]
}

export interface Workflow {
  name: string
  title: string
  summary: string
  stages: FlowItem[]
  /** 经过哪几个阶段，按出现顺序去重 */
  covers: ResearchStage[]
  /** 提醒，不是问题：比如做了实验没验证 */
  remarks: string[]
  problems: string[]
}
