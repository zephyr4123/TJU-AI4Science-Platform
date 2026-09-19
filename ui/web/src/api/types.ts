// 与 `framework/chat/boards.py`、`server.py` 的响应体一一对应。改后端字段先改这里，页面才会跟着编译不过。

/** 七个研究阶段之一（`GET /stages`）：名字给人看、slug 是目录名与 id 的前缀；主文件是这个阶段钉死的文件名（P-20）
 *  连同它页面上的名字（P-21），还没定的阶段是空表。 */
export interface StageInfo {
  name: string
  slug: string
  main_files: { name: string; label: string }[]
}
export type ResearchStage = string

/** 需求确认的状态（`requirement.lock`）：没确认过 / 确认过 / 确认后又改了（dirty）。 */
export interface RequirementState {
  confirmed: boolean
  version: number | null
  by: string | null
  at: string | null
  dirty: boolean
}

/** 需求文档里按二级标题切出来的一格；`pending` 是空着或还有「待填」。 */
export interface RequirementSection {
  heading: string
  body: string
  pending: boolean
}

/** `GET /workspaces/<id>/requirement`：原文、格、确认状态、上一版确认时的原文（页面做 diff）。 */
export interface RequirementDetail extends RequirementState {
  title: string
  text: string
  sections: RequirementSection[]
  pending: boolean
  confirmed_text: string | null
}

/** 人的签字（产出目录里的 signed.json）；`stale`：签过之后目录又改了。 */
export interface Signature {
  by: string
  signed_at: string
  sha256: string
  note: string
  stale: boolean
}

export type OutputStatus = 'running' | 'ok' | 'failed'

/** 一次产出的记录（meta.yaml）：谁产的、读了谁、在哪条流第几项下产的、成没成、签没签。 */
export interface OutputBrief {
  id: string
  stage: string
  title: string
  status: OutputStatus
  by: string
  from: string[]
  params: Record<string, unknown>
  flow: string | null
  step: number | null
  requirement: number | null
  chat_id: string | null
  created_at: string
  finished_at: string | null
  result: string
  error: string
  signed: Signature | null
}

/** 产出目录里的一个文件：小文本带正文（页面按种类渲染），大的与二进制只给名字。 */
export interface OutputFile {
  path: string
  size: number
  text?: string
}

export interface OutputDetail extends OutputBrief {
  files: OutputFile[]
  jobs: Job[]
}

/** 一个阶段一格：名字、目录名、这个阶段的全部产出。 */
export interface StageBoard extends StageInfo {
  outputs: OutputBrief[]
}

/** `cap ... --detach` 起的一个后台作业。`status` 是记录里写的，`effective_status` 探过 pid。 */
export interface Job {
  job_id: string
  cap: string
  stage: string
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
  flow: string | null
  /** 这个作业产的那次产出；子进程开了目录才有 */
  output: string | null
}

/** 流实例的一项在盘上对应的产出（进度算出来的） */
export interface FlowOutput {
  id: string
  title: string
  status: OutputStatus
  by: string
  from: string[]
  signed: boolean
  signed_stale: boolean
}

export type FlowProgressItem =
  | { kind: 'stage'; index: number; stage: ResearchStage; caps: { cap: string; with: Record<string, unknown> }[]; outputs: FlowOutput[] }
  | { kind: 'stop'; index: number; note: string; outputs: FlowOutput[]; signed: boolean }

/** 在等谁：作业 / 人签 / 助理 / 走完 */
export type Waiting = 'job' | 'sign' | 'assistant' | 'done'

/** 工作区里的一条流实例（`flows/*.yaml`）+ 它的进度（沿产出的 meta 算）。坏文件只有 problems。 */
export interface FlowProgress extends Workflow {
  items?: FlowProgressItem[]
  step?: number
  total?: number
  waiting?: Waiting
  job?: Job | null
}

/** 一个工作区 = 一份需求（`GET /workspaces`）。 */
export interface WorkspaceSummary {
  id: string
  title: string
  root: string
  requirement: RequirementState
  /** 每个阶段几次产出，键是目录名 */
  counts: Record<string, number>
  /** 几个作业在跑 */
  running: number
}

/** `GET /workspaces/<id>`：需求 + 七个阶段各自的产出 + 每条流实例的进度 + 作业。 */
export interface WorkspaceDetail extends WorkspaceSummary {
  requirement: RequirementDetail
  stages: StageBoard[]
  flows: FlowProgress[]
  jobs: Job[]
}

/** 文件镜头：目录的一层（`GET /workspaces/<id>/files?path=`），目录在前；`.venv` `.git` 不列。 */
export interface DirEntry {
  name: string
  kind: 'dir' | 'file'
  size: number | null
}
export interface DirListing {
  path: string
  entries: DirEntry[]
}

/** 一个文件（`GET /workspaces/<id>/file?path=`）：文本带正文（大的截断），二进制 `text` 为 null、走 raw。 */
export interface FileContent {
  path: string
  size: number
  text: string | null
  truncated: boolean
}

/** 库里的一份需求模板（`GET /templates`）。 */
export interface Template {
  name: string
  title: string
  summary: string
  text: string
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
  /** 这一轮的框架事件（落盘的 trace.jsonl，不含 delta）：工具调用是对话的一部分，重开也在 */
  events: ChatEvent[]
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
  /** 页面上的名字（`max_iters` → 最多轮数）；`help` 是 hover 的一句 */
  label: string
  help?: string
  default?: unknown
  type?: string
  /** 假的是每次调用时才定的（哪个 run、接不接着跑），流里写不了 */
  in_flow?: boolean
}

/** 一颗能力：一个阶段里的一件活，对助理就是一条命令。五栏是给人读的机制说明（纲领 P-18）。 */
export interface Capability {
  name: string
  /** 属于哪个阶段：标签，不定先后；`stage_slug` 是那个阶段的目录名 */
  stage: ResearchStage
  stage_slug: string
  /** 名：页面直接显示（P-21） */
  title: string
  /** 一行：hover 显示 */
  brief: string
  /** 详情：职责 / 边界 / 输入 / 产出 / 终止条件，点开才看 */
  does: string
  does_not: string
  brings: string
  leaves: string
  stops: string
  params: CapabilityParam[]
  needs_executor: boolean
  needs_compute: boolean
  /** 能接着上一次的产出干（--continue），不另开目录 */
  continuable: boolean
  /** 点名用在哪几条工作流里：后端从工作流文件反查的，能力自己不写 */
  used_by: string[]
}

/** 流里的一项：一个阶段（可点名能力、带参数），或一个断点（前一项的产出要人签了下游才能读）。 */
export type FlowItem =
  | { kind: 'stage'; stage: ResearchStage; caps: { cap: string; with: Record<string, unknown> }[] }
  | { kind: 'stop'; note: string }

/** 编辑台交给 `POST /workflows`（存）与 `POST /workflows/check`（只查）的一条流：形状同文件。
 *  一项是阶段名、`{阶段: [能力]}`、`{阶段: {能力: 参数}}`、`"断点"` 或 `{断点: 一句话}`。 */
export type DraftItem = string | Record<string, string | string[] | Record<string, Record<string, unknown> | null>>
export interface WorkflowDraft {
  name: string
  title: string
  summary: string
  stages: DraftItem[]
  /** 画布上每一项的坐标（与 stages 一样长），人摆过才带 */
  layout?: [number, number][]
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
  /** 画布上每一项的坐标（与 stages 一样长）；没人摆过就是 null */
  layout: [number, number][] | null
  /** 经过哪几个阶段，按出现顺序去重 */
  covers: ResearchStage[]
  /** 提醒，不是问题：比如做了实验没验证 */
  remarks: string[]
  problems: string[]
}
