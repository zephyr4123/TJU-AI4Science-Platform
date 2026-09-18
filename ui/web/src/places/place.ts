// 地方栏与窄屏清单共用的形状：两个世界、页面此刻在哪、回调、排序。
import type { WorkspaceSummary } from '@/api/types'

/** 两个平行的世界：工作区（很多个，各有自己的对话与脊柱）与编辑台（全局一个库，自己的对话） */
export type World = 'workspace' | 'studio'

/** 页面此刻在哪：某个工作区、门口（新建工作区那一屏）、编辑台 */
export type Place = { kind: 'workspace'; id: string } | { kind: 'door' } | { kind: 'studio' }

export const worldOf = (place: Place): World => (place.kind === 'studio' ? 'studio' : 'workspace')

export interface PlacesProps {
  workspaces: WorkspaceSummary[] | null
  place: Place
  onPick: (id: string) => void
  onNew: () => void
  /** 切世界：回工作区是回上次那个（一个都没有就是门口），去编辑台就是去编辑台 */
  onWorld: (world: World) => void
}

/** 新的在上：地方栏与窄屏清单同一顺序 */
export function newestFirst(workspaces: WorkspaceSummary[] | null): WorkspaceSummary[] {
  return workspaces ? [...workspaces].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? '')) : []
}
