// 页面此刻在哪，与地方栏的形状。两个世界（纲领 P-15 P-16）：项目的世界——首页（项目墙）、门口（起项目那一屏）、
// 某个项目、项目里的某个工作区——与编辑台；设置是全局的一块，不算地方。每次打开都从首页进（主人 2026-09-23：
// 首启该看到项目清单，不该直接落进上次那个项目的对话入口），不记上次在哪。
export type Place =
  | { kind: 'home' }
  | { kind: 'door' }
  | { kind: 'project'; id: string }
  | { kind: 'workspace'; project: string; id: string }
  | { kind: 'studio' }

export type World = 'projects' | 'studio'

export const HOME: Place = { kind: 'home' }

export const worldOf = (place: Place): World => (place.kind === 'studio' ? 'studio' : 'projects')

/** 此刻在哪个项目里（项目页或它的工作区页）；不在就是 null */
export function projectOf(place: Place): string | null {
  if (place.kind === 'project') return place.id
  if (place.kind === 'workspace') return place.project
  return null
}

/** 地方栏（宽屏）与地方清单（窄屏）同一份：三个键——首页、编辑台、设置 */
export interface PlacesProps {
  place: Place
  onHome: () => void
  onStudio: () => void
  /** 设置（P-25）：归人、全局一份；那个点在有一项自检没过时才亮 */
  settingsOpen: boolean
  settingsDot: boolean
  onSettings: () => void
}
