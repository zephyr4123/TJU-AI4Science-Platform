// 首页项目清单的纯函数：排序、搜索与搜中的字标出来（外层 #249）。

import type { ProjectSummary } from '@/api/types'

/** 后端按目录名给；清单上新的在前 */
export function newestFirst(projects: ProjectSummary[]): ProjectSummary[] {
  return [...projects].sort((a, b) => b.created_at.localeCompare(a.created_at))
}

/** 搜索框里的字拆成词：空白分开、不分大小写 */
export function wordsOf(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean)
}

/** 按名字与目标找：几个词都要对上（不论先后）；没写词就是全部 */
export function findProjects(projects: ProjectSummary[], query: string): ProjectSummary[] {
  const words = wordsOf(query)
  if (words.length === 0) return projects
  return projects.filter((p) => {
    const text = `${p.title}\n${p.goal}`.toLowerCase()
    return words.every((w) => text.includes(w))
  })
}

export interface Mark { text: string; hit: boolean }

/** 一段字切成搜中与没搜中的几截，重叠的并成一截。转小写会改长度的字（极少）不标，免得标错位置 */
export function marks(text: string, words: string[]): Mark[] {
  const lower = text.toLowerCase()
  if (words.length === 0 || lower.length !== text.length) return [{ text, hit: false }]
  const hit = new Array<boolean>(text.length).fill(false)
  for (const w of words) {
    for (let i = lower.indexOf(w); i !== -1; i = lower.indexOf(w, i + 1)) hit.fill(true, i, i + w.length)
  }
  const out: Mark[] = []
  for (let i = 0; i < text.length;) {
    let j = i
    while (j < text.length && hit[j] === hit[i]) j++
    out.push({ text: text.slice(i, j), hit: hit[i] })
    i = j
  }
  return out
}
