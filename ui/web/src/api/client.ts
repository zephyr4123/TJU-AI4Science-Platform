// 页面唯一的取数入口：每个端点一个函数，路径与 `framework/chat/server.py` 顶部的清单一致。
// 组件不直接 fetch——换一种 UI（TUI）时这一层就是要照抄的契约。
// 端点按域分前缀（纲领 P-16）：工作区 `/workspaces/<id>` 是研究助理的域，`/studio` 是造流助理的域；
// 对话四个端点在两个域下共用，`Scope` 决定前缀。

import type {
  Backend, Capability, ChatDoc, ChatMeta, OutputDetail, RequirementDetail, StageInfo, Template,
  Tuning, Workflow, WorkflowCheck, WorkflowDraft, WorkspaceDetail, WorkspaceSummary,
} from './types'

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
  health: () => request<{ ok: boolean }>('/health'),
  backends: () => request<Backend[]>('/backends'),
  stages: () => request<StageInfo[]>('/stages'),
  templates: () => request<Template[]>('/templates'),
  capabilities: () => request<Capability[]>('/cap'),
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

  chats: (scope: Scope) => request<ChatMeta[]>(`${scopePath(scope)}/chats`),
  chat: (scope: Scope, chatId: string) =>
    request<ChatDoc>(`${scopePath(scope)}/chats/${encodeURIComponent(chatId)}`),
  newChat: (scope: Scope, tuning?: Tuning) =>
    request<ChatMeta>(`${scopePath(scope)}/chats`, post(tuning ?? {})),
}
