// 页面唯一的取数入口：每个端点一个函数，路径与 `framework/chat/server.py` 顶部的清单一致。
// 组件不直接 fetch——换一种 UI（TUI）时这一层就是要照抄的契约。
// 端点按域分前缀（纲领 P-16）：工作区 `/workspaces/<id>` 是研究助理的域，`/studio` 是造流助理的域；
// 对话四个端点在两个域下共用，`Scope` 决定前缀。

import type { Backend, Capability, ChatDoc, ChatMeta, CheckReport, DirListing, FileContent, Job, OutputDetail, Removed, RequirementDetail, SettingsDoc, SkillEntry, StageInfo, Template, Tuning, Workflow, WorkflowCheck, WorkflowDraft, WorkspaceDetail, WorkspaceSummary } from './types'

export type Scope = { kind: 'workspace'; id: string } | { kind: 'studio' }

export const STUDIO: Scope = { kind: 'studio' }
export const inWorkspace = (id: string): Scope => ({ kind: 'workspace', id })

export function scopePath(scope: Scope): string {
  return scope.kind === 'studio' ? '/studio' : `/workspaces/${encodeURIComponent(scope.id)}`
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
const ws = (id: string) => scopePath(inWorkspace(id))

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
  /** 删（主人 2026-09-22：人产生的都能删，级联到根；拒 409、没有 404、出厂的 403） */
  removeWorkspace: (id: string) => request<Removed>(`${ws(id)}/remove`, post({})),
  removeOutput: (id: string, oid: string) => request<Removed>(`${ws(id)}/outputs/${oid}/remove`, post({})),
  removeFlow: (id: string, name: string) => request<Removed>(`${ws(id)}/flows/${encodeURIComponent(name)}/remove`, post({})),
  removeWorkflow: (name: string) => request<Removed>(`/workflows/${encodeURIComponent(name)}/remove`, post({})),
  removeChat: (scope: Scope, chatId: string) =>
    request<Removed>(`${scopePath(scope)}/chats/${encodeURIComponent(chatId)}/remove`, post({})),
  removeCompute: (name: string) =>
    request<SettingsDoc>(`/settings/computes/${encodeURIComponent(name)}/remove`, post({})),
  stages: () => request<StageInfo[]>('/stages'),
  templates: () => request<Template[]>('/templates'),
  capabilities: () => request<Capability[]>('/cap'),
  skills: () => request<SkillEntry[]>('/skills'),
  workflows: () => request<Workflow[]>('/workflows'),
  saveWorkflow: (doc: WorkflowDraft) => request<Workflow>('/workflows', post(doc)),
  checkWorkflow: (doc: WorkflowDraft) => request<WorkflowCheck>('/workflows/check', post(doc)),

  workspaces: () => request<WorkspaceSummary[]>('/workspaces'),
  newWorkspace: (id: string, title: string, template: string) =>
    request<WorkspaceSummary>('/workspaces', post({ id, title, template })),
  workspace: (id: string) => request<WorkspaceDetail>(ws(id)),
  requirement: (id: string) => request<RequirementDetail>(`${ws(id)}/requirement`),
  confirm: (id: string, by: string) =>
    request<RequirementDetail>(`${ws(id)}/requirement/confirm`, post({ by })),
  /** 产出的 id 就是路径（experiment/2），直接拼进 URL */
  output: (id: string, oid: string) => request<OutputDetail>(`${ws(id)}/outputs/${oid}`),
  sign: (id: string, oid: string, by: string, note: string) =>
    request<OutputDetail>(`${ws(id)}/outputs/${oid}/sign`, post({ by, note })),
  /** 人叫停一个后台作业：杀进程树，作业记 stopped、它的产出记失败（外层 #115） */
  stopJob: (id: string, jobId: string, by: string) =>
    request<Job>(`${ws(id)}/jobs/${jobId}/stop`, post({ by })),
  /** 文件镜头：目录一层、一个文件的正文、原样端出的 URL（图片直接当 src） */
  files: (id: string, path: string) => request<DirListing>(`${ws(id)}/files?path=${encodeURIComponent(path)}`),
  file: (id: string, path: string) => request<FileContent>(`${ws(id)}/file?path=${encodeURIComponent(path)}`),
  rawUrl: (id: string, path: string) => `${ws(id)}/raw?path=${encodeURIComponent(path)}`,

  chats: (scope: Scope) => request<ChatMeta[]>(`${scopePath(scope)}/chats`),
  chat: (scope: Scope, chatId: string) =>
    request<ChatDoc>(`${scopePath(scope)}/chats/${encodeURIComponent(chatId)}`),
  /** 开一段：哪家、模型、深度都可以不给——服务从按人的设置抄（P-25） */
  newChat: (scope: Scope, tuning?: Tuning, backend?: string) =>
    request<ChatMeta>(`${scopePath(scope)}/chats`, post({ ...(tuning ?? {}), ...(backend ? { backend } : {}) })),
}
