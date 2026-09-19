// 看板上算出来的东西，纯函数、有单测：一条流在等谁、下一步是哪个阶段、每次产出用哪个词、断点的短标签。
import type { FlowOutput, FlowProgress, FlowProgressItem } from '@/api/types'

/** 哪些产出待人确认：流里那一项后面是断点、产出还没确认（或确认之后又改了） */
export function needsSign(flows: FlowProgress[]): Set<string> {
  const found = new Set<string>()
  for (const flow of flows) {
    const items = flow.items ?? []
    items.forEach((item, i) => {
      if (item.kind !== 'stop') return
      const previous = [...items.slice(0, i)].reverse().find((it) => it.kind === 'stage')
      for (const o of previous?.outputs ?? []) if (o.status === 'ok' && !(o.signed && !o.signed_stale)) found.add(o.id)
    })
  }
  return found
}

/** 下一步是流里的第几项（阶段）：step 之后第一个阶段项；走完了是 null */
export function nextStage(flow: FlowProgress): Extract<FlowProgressItem, { kind: 'stage' }> | null {
  const items = flow.items ?? []
  const step = flow.step ?? -1
  for (const item of items) if (item.index > step && item.kind === 'stage') return item
  return null
}

/** 断点在两列之间只放两三个字：句子的第一段，最多六个字；全句悬停看 */
export function shortNote(note: string): string {
  const head = note.split(/[，,。．：:；;、\s（(]/)[0]
  return (head || note).slice(0, 6)
}

export type OutputState = 'running' | 'failed' | 'pending' | 'confirmed' | 'done'

/** 一次产出的状态：运行中 / 失败 / 待确认 / 已确认 / 完成 */
export function outputState(o: FlowOutput, pending: Set<string>): OutputState {
  if (o.status === 'running') return 'running'
  if (o.status === 'failed') return 'failed'
  if (pending.has(o.id)) return 'pending'
  if (o.signed && !o.signed_stale) return 'confirmed'
  return 'done'
}

/** 目录名 → 阶段名（`GET /stages` 给的表） */
export type NameOf = (slug: string) => string

/** 一条流现在在等谁，一句话：下一步：实验 · 助理 / 待确认：设计 1 / 运行中：实验 2 / 完成 / 流文件有误 */
export function waitingSentence(flow: FlowProgress, pending: Set<string>, nameOf: NameOf): string {
  if (flow.problems.length > 0 || !flow.items) return '流文件有误'
  const items = flow.items
  const step = flow.step ?? -1
  if (flow.waiting === 'job') {
    const output = flow.job?.output
    return output ? `运行中：${outputName(output, nameOf)}` : '运行中'
  }
  if (flow.waiting === 'sign') {
    const last = [...items].reverse().find((it) => it.kind === 'stage' && it.index <= step)
    const waiting = last?.kind === 'stage' ? last.outputs.find((o) => pending.has(o.id)) : undefined
    return waiting ? `待确认：${outputName(waiting.id, nameOf)}` : '待确认'
  }
  if (flow.waiting === 'done') return '完成'
  const next = nextStage(flow)
  return next ? `下一步：${next.stage} · 助理` : '完成'
}

/** 产出 id 的人话：design/1 → 设计 1 */
export function outputName(id: string, nameOf: NameOf): string {
  const [slug, n] = id.split('/')
  return `${nameOf(slug)} ${n}`
}
