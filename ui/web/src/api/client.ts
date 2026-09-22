// 页面唯一的取数入口：每个端点一个函数，路径与 `framework/chat/server.py` 顶部的清单一致。
// 组件不直接 fetch——换一种 UI（TUI）时这一层就是要照抄的契约。
// 端点按域分前缀（纲领 P-16）：项目 `/projects/<p>` 是研究助理的域（一个项目一位助理，外层 #136），`/studio` 是流程助理的域；
// 对话四个端点在两个域下共用，`Scope` 决定前缀。工作区在项目之下：`/projects/<p>/workspaces/<id>/…`，看板、文件与两处确认
// 拿着一个绑死在（项目，工作区）上的 `WorkspaceClient` 取数，不各自拼路径。

import type {
  Backend, Capability, ChatDoc, ChatMeta, CheckReport, DirListing, FileContent, Job, OutputDetail, ProjectDetail, ProjectSummary,
  Removed, RequirementDetail, SettingsDoc, SkillEntry, StageInfo, Template, Tuning, Workflow, WorkflowCheck, WorkflowDraft,
  WorkspaceDetail, WorkspaceSummary,
} from './types'

export type Scope = { kind: 'project'; id: string } | { kind: 'studio' }

export const STUDIO: Scope = { kind: 'studio' }
export const inProject = (id: string): Scope => ({ kind: 'project', id })

export function scopePath(scope: Scope): string {
  return scope.kind === 'studio' ? '/studio' : `/projects/${encodeURIComponent(scope.id)}`
}

/** 同一个域一个字符串：给 hook 的 deps 用（对象每次渲染都可能是新的，字符串不会） */
export function scopeKey(scope: Scope): string {
  return scope.kind === 'studio' ? 'studio' : `project:${scope.id}`
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 服务端的错误体固定是 `{"error": "..."}`；不是 JSON（代理挂了、HTML 报错页）就把原文给人看。 */
export function errorMessage(status: number, raw: string): string {
  try {
    const body: unknown = JSON.parse(raw)
    if (body && typeof body === 'object' && typeof (body as { error?: unknown }).error === 'string') {
      return (body as { error: string }).error
    }
  } catch {
    // 不是 JSON：下面按原文处理
  }
  return raw.trim() || `HTTP ${status}`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  })
  const raw = await res.text()
  if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, raw))
  return JSON.parse(raw) as T
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  /** checks_ok：在用的两家 agent 与每台算力上次自检都过（没检查过也算过）；地方栏「设置」旁的点靠它 */
  health: () => request<{ ok: boolean; checks_ok: boolean }>('/health'),
  backends: () => request<Backend[]>('/backends'),
  /** 设置那块板（P-25）：读一整份、改用哪家与缺省、真探并记回、接一台机器、删一台 */
  settings: () => request<SettingsDoc>('/settings'),
  updateAgents: (body: { chat?: string; executor?: string; agents?: Record<string, { model?: string; effort?: string }> }) =>
    request<SettingsDoc>('/settings/agents', post(body)),
  runCheck: (what: 'all' | 'agents' | 'computes' | 'storage', name?: string) =>
    request<CheckReport>('/settings/check', post(name ? { what, name } : { what })),
  addCompute: (body: { name: string; ssh: string; key: string; root?: string }) =>
    request<SettingsDoc>('/settings/computes', post(body)),
  removeCompute: (name: string) =>
    request<SettingsDoc>(`/settings/computes/${encodeURIComponent(name)}/remove`, post({})),
  stages: () => request<StageInfo[]>('/stages'),
  templates: () => request<Template[]>('/templates'),
  capabilities: () => request<Capability[]>('/cap'),
  skills: () => request<SkillEntry[]>('/skills'),
  workflows: () => request<Workflow[]>('/workflows'),
  saveWorkflow: (doc: WorkflowDraft) => request<Workflow>('/workflows', post(doc)),
  checkWorkflow: (doc: WorkflowDraft) => request<WorkflowCheck>('/workflows/check', post(doc)),
  removeWorkflow: (name: string) => request<Removed>(`/workflows/${encodeURIComponent(name)}/remove`, post({})),

  /** 项目：清单、起一个（写 project.md）、一整份（每个工作区一行）、删整个（级联到工作区、对话、镜像） */
  projects: () => request<ProjectSummary[]>('/projects'),
  newProject: (id: string, title: string, goal: string) => request<ProjectSummary>('/projects', post({ id, title, goal })),
  project: (id: string) => request<ProjectDetail>(scopePath(inProject(id))),
  removeProject: (id: string) => request<Removed>(`${scopePath(inProject(id))}/remove`, post({})),
  newWorkspace: (project: string, id: string, title: string, template: string) =>
    request<WorkspaceSummary>(`${scopePath(inProject(project))}/workspaces`, post({ id, title, template })),

  chats: (scope: Scope) => request<ChatMeta[]>(`${scopePath(scope)}/chats`),
  chat: (scope: Scope, chatId: string) =>
    request<ChatDoc>(`${scopePath(scope)}/chats/${encodeURIComponent(chatId)}`),
  /** 开一段：哪家、模型、深度都可以不给——服务从按人的设置抄（P-25） */
  newChat: (scope: Scope, tuning?: Tuning, backend?: string) =>
    request<ChatMeta>(`${scopePath(scope)}/chats`, post({ ...(tuning ?? {}), ...(backend ? { backend } : {}) })),
  /** 删一段对话（主人 2026-09-22：人产生的都能删；正在一轮里的服务拒 409） */
  removeChat: (scope: Scope, chatId: string) =>
    request<Removed>(`${scopePath(scope)}/chats/${encodeURIComponent(chatId)}/remove`, post({})),
}

/** 一个工作区的全部端点，绑死在（项目，工作区）上。看板、文件镜头、两处确认拿着它取数；`key` 给 useResource 的 deps 用。
 *  方法都是箭头属性，拆下来单独传（`useResource(ws.detail, …)`）也不丢 this。 */
export class WorkspaceClient {
  readonly project: string
  readonly id: string
  readonly key: string
  private readonly base: string

  constructor(project: string, id: string) {
    this.project = project
    this.id = id
    this.key = `${project}/${id}`
    this.base = `${scopePath(inProject(project))}/workspaces/${encodeURIComponent(id)}`
  }

  /** 那一整份：需求 + 七个阶段的产出 + 每条流程的进度 + 作业 */
  detail = () => request<WorkspaceDetail>(this.base)
  requirement = () => request<RequirementDetail>(`${this.base}/requirement`)
  confirm = (by: string) => request<RequirementDetail>(`${this.base}/requirement/confirm`, post({ by }))
  /** 产出的 id 就是路径（experiment/2），直接拼进 URL */
  output = (oid: string) => request<OutputDetail>(`${this.base}/outputs/${oid}`)
  sign = (oid: string, by: string, note: string) => request<OutputDetail>(`${this.base}/outputs/${oid}/sign`, post({ by, note }))
  /** 人叫停一个后台作业：杀进程树，作业记 stopped、它的产出记失败（外层 #115） */
  stopJob = (jobId: string, by: string) => request<Job>(`${this.base}/jobs/${jobId}/stop`, post({ by }))
  /** 文件镜头：目录一层、一个文件的正文、原样端出的 URL（图片直接当 src） */
  files = (path: string) => request<DirListing>(`${this.base}/files?path=${encodeURIComponent(path)}`)
  file = (path: string) => request<FileContent>(`${this.base}/file?path=${encodeURIComponent(path)}`)
  rawUrl = (path: string) => `${this.base}/raw?path=${encodeURIComponent(path)}`
  /** 删（主人 2026-09-22：人产生的都能删，级联到根；拒 409、没有 404） */
  remove = () => request<Removed>(`${this.base}/remove`, post({}))
  removeOutput = (oid: string) => request<Removed>(`${this.base}/outputs/${oid}/remove`, post({}))
  removeFlow = (name: string) => request<Removed>(`${this.base}/flows/${encodeURIComponent(name)}/remove`, post({}))
}
