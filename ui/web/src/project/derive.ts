// 项目页上每个工作区那一行怎么说（纯函数，有单测）：一个词答「现在到哪一步、在等谁」，一两句小字说细节。
// 词只用词表里的：需求未确认 / 运行中 / 待确认 / 进行中 / 完成 / 尚未选定流程 / 流程文件有误（主人：能用词就用词）。
import type { WorkspaceRow } from '@/api/types'
import type { Tone } from '@/components/bits'

/** 状态符（reactbits StatusMark）的四种样子：空心虚线环 / 转圈 / 画勾 / 画叉 */
export type Mark = 'pending' | 'running' | 'done' | 'failed'

export interface RowState {
  word: string
  tone: Tone
  mark: Mark
  /** 小字：流程走到第几步、产出几次 */
  details: string[]
}

export function rowState(row: WorkspaceRow): RowState {
  const details = detailsOf(row)
  if (!row.requirement.confirmed) return { word: '需求未确认', tone: 'warn', mark: 'pending', details }
  if (row.running > 0) return { word: '运行中', tone: 'primary', mark: 'running', details }
  if (row.flows.some((f) => f.problems.length > 0)) return { word: '流程文件有误', tone: 'bad', mark: 'failed', details }
  if (row.flows.length === 0) return { word: '尚未选定流程', tone: 'neutral', mark: 'pending', details }
  // 几条流程各在等谁：有一条等人就先说等人；有一条在跑说运行中；有一条等助理就是进行中；全走完才是完成
  const waiting = new Set(row.flows.map((f) => f.waiting))
  if (waiting.has('sign')) return { word: '待确认', tone: 'warn', mark: 'pending', details }
  if (waiting.has('job')) return { word: '运行中', tone: 'primary', mark: 'running', details }
  if (waiting.has('assistant')) return { word: '进行中', tone: 'primary', mark: 'pending', details }
  return { word: '完成', tone: 'ok', mark: 'done', details }
}

/** 细节两句：第一条流程走到第几步（多条时再加「等 N 条」）、七个阶段一共产出几次 */
function detailsOf(row: WorkspaceRow): string[] {
  const out: string[] = []
  const [first, ...rest] = row.flows.filter((f) => f.problems.length === 0)
  if (first && first.total) {
    const name = first.title ?? first.name
    out.push(`${name} ${first.step ?? 0} / ${first.total}` + (rest.length ? ` 等 ${rest.length + 1} 条` : ''))
  }
  const produced = Object.values(row.counts).reduce((a, b) => a + b, 0)
  if (produced > 0) out.push(`产出 ${produced} 次`)
  return out
}
