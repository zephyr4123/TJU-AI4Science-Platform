// 页面此刻在哪，与地方栏的形状。两个世界（纲领 P-15 P-16）：项目的世界——首页（项目墙）、门口（起项目那一屏）、
// 某个项目、项目里的某个工作区——与编辑台；设置是全局的一块，不算地方。上次在哪记在浏览器里，下次打开直接回去。
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

const KEY = 'ai4sci.place'
const ID = /^[a-z][a-z0-9-]*$/

/** 浏览器里记的那条：只认项目与工作区（首页、门口、编辑台不值得记），字段不对就当没记 */
export function parseStored(raw: string | null): Place | null {
  if (!raw) return null
  let doc: unknown
  try { doc = JSON.parse(raw) } catch { return null }
  if (!doc || typeof doc !== 'object') return null
  const { project, workspace } = doc as { project?: unknown; workspace?: unknown }
  if (typeof project !== 'string' || !ID.test(project)) return null
  if (workspace === undefined || workspace === null) return { kind: 'project', id: project }
  if (typeof workspace !== 'string' || !ID.test(workspace)) return null
  return { kind: 'workspace', project, id: workspace }
}

export function recallPlace(): Place | null {
  try { return parseStored(window.localStorage.getItem(KEY)) } catch { return null }
}

export function rememberPlace(place: Place): void {
  const project = projectOf(place)
  if (!project) return
  const doc = place.kind === 'workspace' ? { project, workspace: place.id } : { project }
  try { window.localStorage.setItem(KEY, JSON.stringify(doc)) } catch { /* 隐私模式存不了就每次从首页进 */ }
}
