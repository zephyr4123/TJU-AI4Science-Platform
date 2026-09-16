// 页面唯一的取数入口：每个端点一个函数，路径与 `framework/chat/server.py` 顶部的清单一致。
// 组件不直接 fetch——换一种 UI（TUI）时这一层就是要照抄的契约。

import type {
  Capability, ChatDoc, ChatMeta, FlowCheck, RunDetail, RunSummary, TaskDetail, TaskSummary,
} from './types'

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
  health: () => request<{ ok: boolean }>('/health'),
  capabilities: () => request<Capability[]>('/cap'),
  flowCheck: (steps: string[]) =>
    request<FlowCheck>(`/flow/check?steps=${encodeURIComponent(steps.join(','))}`),

  chats: () => request<ChatMeta[]>('/chats'),
  chat: (id: string) => request<ChatDoc>(`/chats/${encodeURIComponent(id)}`),
  newChat: () => request<ChatMeta>('/chats', post({})),

  tasks: () => request<TaskSummary[]>('/tasks'),
  task: (id: string) => request<TaskDetail>(`/tasks/${encodeURIComponent(id)}`),
  publish: (id: string, by: string) =>
    request<TaskDetail>(`/tasks/${encodeURIComponent(id)}/publish`, post({ by })),

  runs: () => request<RunSummary[]>('/runs'),
  run: (id: string) => request<RunDetail>(`/runs/${encodeURIComponent(id)}`),
  accept: (id: string, by: string) =>
    request<RunDetail>(`/runs/${encodeURIComponent(id)}/accept`, post({ by })),
}
