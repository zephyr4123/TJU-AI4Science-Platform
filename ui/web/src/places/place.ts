// 地方栏与窄屏清单共用的形状：页面此刻在哪、五个回调、排序。
import type { WorkspaceSummary } from '@/api/types'

/** 页面此刻在哪：某个工作区、门口（新建工作区那一屏）、编辑台 */
export type Place = { kind: 'workspace'; id: string } | { kind: 'door' } | { kind: 'studio' }

export interface PlacesProps {
  workspaces: WorkspaceSummary[] | null
  place: Place
  onPick: (id: string) => void
  onNew: () => void
  onStudio: () => void
}

/** 新的在上：地方栏与窄屏清单同一顺序 */
export function newestFirst(workspaces: WorkspaceSummary[] | null): WorkspaceSummary[] {
  return workspaces ? [...workspaces].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? '')) : []
}
