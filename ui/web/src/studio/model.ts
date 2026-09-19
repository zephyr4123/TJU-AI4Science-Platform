// 编辑台画布的数据：一条线性的链，一项是一个研究阶段（装能力 + 参数）或一个断点（纲领 P-18，外层 #100 #101）。
// 纯函数，不碰 React 也不碰 React Flow：排序、插入、坐标 → 位置、页面形状 ↔ 文件形状。坐标不进文件，按顺序自动排。
import type { DraftItem, FlowItem, Workflow, WorkflowDraft } from '@/api/types'

export interface Pick { cap: string; with: Record<string, unknown> }
export interface StageItem { uid: number; kind: 'stage'; stage: string; caps: Pick[] }
export interface StopItem { uid: number; kind: 'stop'; note: string }
export type Item = StageItem | StopItem
export interface Draft { name: string; title: string; summary: string; items: Item[] }

export const EMPTY: Draft = { name: '', title: '', summary: '', items: [] }

/** 从左栏拖 / 点过来的是什么；拖的时候塞在 dataTransfer 里过画布 */
export type Seed = { kind: 'stage'; stage: string } | { kind: 'stop'; note: string }
export const SEED_MIME = 'application/x-ai4sci-item'

export function parseSeed(raw: string): Seed | null {
  if (!raw) return null
  const seed = JSON.parse(raw) as Seed
  return seed.kind === 'stage' || seed.kind === 'stop' ? seed : null
}

let seq = 0
/** 节点在画布上的身份：换顺序不换身份，选中态与动画才跟得住 */
export const mint = (): number => ++seq

export const stageItem = (stage: string, caps: Pick[] = []): StageItem => ({ uid: mint(), kind: 'stage', stage, caps })
export const stopItem = (note = ''): StopItem => ({ uid: mint(), kind: 'stop', note })
export const fromSeed = (seed: Seed): Item => (seed.kind === 'stage' ? stageItem(seed.stage) : stopItem(seed.note))

// ── 排版：从左到右，一行放不下就换行，坐标不进文件 ────────────────────────────
export const WIDTH = { stage: 208, stop: 136 } as const
export const GAP = 56
/** 一行最宽多少；超了换行。出厂那条 8 项分两行 */
export const ROW_WIDTH = 1100
/** 行距：节点高 ~80，行间留 70 走跨行的边 */
export const ROW_PITCH = 150

export interface Slot { x: number; y: number; row: number; width: number }

/** 每一项的位置：一行接一行，从左到右；断点窄一些 */
export function layout(items: Item[]): Slot[] {
  let x = 0
  let row = 0
  return items.map((item) => {
    const width = WIDTH[item.kind]
    if (x > 0 && x + width > ROW_WIDTH) { x = 0; row += 1 }
    const slot = { x, y: row * ROW_PITCH, row, width }
    x += width + GAP
    return slot
  })
}

/** 一个坐标落在第几项之前：前面几行的全算，同一行里中点在它左边的算 */
export function indexAt(items: Item[], x: number, y: number): number {
  const slots = layout(items)
  const row = Math.max(0, Math.round(y / ROW_PITCH))
  return slots.filter((slot) => slot.row < row || (slot.row === row && slot.x + slot.width / 2 < x)).length
}

// ── 增删移 ──────────────────────────────────────────────────────────────────
export function insertAt(items: Item[], index: number, item: Item): Item[] {
  const at = Math.max(0, Math.min(items.length, index))
  return [...items.slice(0, at), item, ...items.slice(at)]
}

export function remove(items: Item[], uid: number): Item[] {
  return items.filter((item) => item.uid !== uid)
}

/** 拖完一个节点：按它松手时的中点重排；别的节点位置不变 */
export function moveTo(items: Item[], uid: number, centerX: number, centerY: number): Item[] {
  const moving = items.find((item) => item.uid === uid)
  if (!moving) return items
  const rest = remove(items, uid)
  return insertAt(rest, indexAt(rest, centerX, centerY), moving)
}

export function patch(items: Item[], uid: number, change: (item: Item) => Item): Item[] {
  return items.map((item) => (item.uid === uid ? change(item) : item))
}

/** 勾上 / 去掉一颗能力；去掉时它的参数一起走 */
export function toggleCap(item: StageItem, cap: string, on: boolean): StageItem {
  const has = item.caps.some((p) => p.cap === cap)
  if (on === has) return item
  return { ...item, caps: on ? [...item.caps, { cap, with: {} }] : item.caps.filter((p) => p.cap !== cap) }
}

/** 改一个参数：`undefined` 表示清掉（回到描述符的缺省值） */
export function setParam(item: StageItem, cap: string, name: string, value: unknown): StageItem {
  return {
    ...item,
    caps: item.caps.map((p) => {
      if (p.cap !== cap) return p
      const next = { ...p.with }
      if (value === undefined) delete next[name]
      else next[name] = value
      return { ...p, with: next }
    }),
  }
}

// ── 页面 ↔ 文件 ─────────────────────────────────────────────────────────────
/** 画布 → 文件同形的 JSON：不点名的阶段一个名字、点名的一个清单、带参数的「能力: 参数」映射；断点一个词或「断点: 一句话」。 */
export function toDraft(draft: Draft): WorkflowDraft {
  const stages: DraftItem[] = draft.items.map((item) => {
    if (item.kind === 'stop') return item.note.trim() ? { 断点: item.note.trim() } : '断点'
    if (item.caps.length === 0) return item.stage
    if (item.caps.every((p) => Object.keys(p.with).length === 0)) return { [item.stage]: item.caps.map((p) => p.cap) }
    return { [item.stage]: Object.fromEntries(item.caps.map((p) => [p.cap, Object.keys(p.with).length ? p.with : null])) }
  })
  return { name: draft.name.trim(), title: draft.title.trim(), summary: draft.summary.trim(), stages }
}

/** 库里的一条 → 画布：名字照旧，存回去要勾「覆盖同名」 */
export function fromWorkflow(wf: Workflow): Draft {
  return { name: wf.name, title: wf.title, summary: wf.summary, items: wf.stages.map(fromItem) }
}

export function fromItem(item: FlowItem): Item {
  if (item.kind === 'stop') return stopItem(item.note)
  return stageItem(item.stage, item.caps.map((c) => ({ cap: c.cap, with: { ...c.with } })))
}

/** 后端的问题句里点到「第 N 项」的，贴到第 N 项那个节点上（「第 2 项与第 3 项都是断点」贴两个） */
export function problemIndices(text: string): number[] {
  return [...text.matchAll(/第 (\d+) 项/g)].map((m) => Number(m[1]) - 1)
}

/** 参数输入框里的字 → 描述符要的类型；空串 = 清掉；解析不了也清掉（不把坏值塞进文件） */
export function parseParam(type: string | undefined, raw: string): unknown {
  const text = raw.trim()
  if (text === '') return undefined
  if (type === 'int') { const n = Number(text); return Number.isInteger(n) ? n : undefined }
  if (type === 'float') { const n = Number(text); return Number.isFinite(n) ? n : undefined }
  return text
}
