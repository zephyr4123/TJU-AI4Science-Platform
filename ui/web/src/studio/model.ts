// 编辑台画布的数据：一条线性的链，一项是一个研究阶段（装能力 + 参数）或一个断点（纲领 P-18，外层 #100 #101）。
// 纯函数，不碰 React 也不碰 React Flow：位置、顺序、插入、页面形状 ↔ 文件形状。
// 位置：人摆过的项记着坐标（存进文件的 layout 块），没摆过的按顺序自动排、放不下换行；顺序 = 阅读顺序（先上后下、同一行先左后右），
// 拖一个节点松手，它留在松手的地方，顺序按阅读顺序重算——边跟着顺序画，所以看着在哪就是排第几。
import type { DraftItem, FlowItem, Workflow, WorkflowDraft } from '@/api/types'

export interface XY { x: number; y: number }
export interface Pick { cap: string; with: Record<string, unknown> }
export interface StageItem { uid: number; kind: 'stage'; stage: string; caps: Pick[]; pos?: XY }
export interface StopItem { uid: number; kind: 'stop'; note: string; pos?: XY }
export type Item = StageItem | StopItem
export interface Draft { name: string; title: string; summary: string; items: Item[] }

export const EMPTY: Draft = { name: '', title: '', summary: '', items: [] }

/** 从梯子拖 / 点过来的是什么；拖的时候塞在 dataTransfer 里过画布 */
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

export const stageItem = (stage: string, caps: Pick[] = [], pos?: XY): StageItem => ({ uid: mint(), kind: 'stage', stage, caps, pos })
export const stopItem = (note = '', pos?: XY): StopItem => ({ uid: mint(), kind: 'stop', note, pos })
export const fromSeed = (seed: Seed, pos?: XY): Item => (seed.kind === 'stage' ? stageItem(seed.stage, [], pos) : stopItem(seed.note, pos))

// ── 位置 ───────────────────────────────────────────────────────────────────
/** 节点在画布上占的宽：阶段是一张卡，断点是一枚 56px 的圆点（主人 2026-09-23：和阶段一样大只靠颜色分不出来） */
export const WIDTH = { stage: 208, stop: 56 } as const
export const GAP = 56
/** 自动排时一行最宽多少；超了换行。出厂那条 8 项分两行 */
export const ROW_WIDTH = 1100
/** 行距：节点高 ~80，行间留 70 走跨行的边；也是阅读顺序里「同一行」的粒度 */
export const ROW_PITCH = 150

/** 没摆过的项按顺序自动排：一行接一行，从左到右 */
export function autoLayout(items: Item[]): XY[] {
  let x = 0
  let row = 0
  return items.map((item) => {
    const width = WIDTH[item.kind]
    if (x > 0 && x + width > ROW_WIDTH) { x = 0; row += 1 }
    const at = { x, y: row * ROW_PITCH }
    x += width + GAP
    return at
  })
}

/** 每一项此刻在哪：摆过的按摆的，没摆过的按自动排 */
export function positions(items: Item[]): XY[] {
  const auto = autoLayout(items)
  return items.map((item, i) => item.pos ?? auto[i])
}

/** 人摆过没有：摆过才把坐标存进文件 */
export const arranged = (items: Item[]): boolean => items.some((item) => item.pos !== undefined)

/** 阅读顺序里的行：按纵坐标分带 */
const band = (y: number) => Math.round(y / ROW_PITCH)

/** 一个坐标落在第几项之前：上面几带的全算，同一带里中点在它左边的算 */
export function indexAt(items: Item[], x: number, y: number): number {
  const at = positions(items)
  const row = band(y)
  return items.filter((item, i) => band(at[i].y) < row || (band(at[i].y) === row && at[i].x + WIDTH[item.kind] / 2 < x)).length
}

/** 按阅读顺序重排：先上后下，同一带先左后右（稳定：同位置保持原顺序） */
export function byReadingOrder(items: Item[]): Item[] {
  const at = positions(items)
  return items.map((item, i) => ({ item, i, y: band(at[i].y), x: at[i].x }))
    .sort((a, b) => a.y - b.y || a.x - b.x || a.i - b.i)
    .map((r) => r.item)
}

// ── 增删移 ──────────────────────────────────────────────────────────────────
export function insertAt(items: Item[], index: number, item: Item): Item[] {
  const at = Math.max(0, Math.min(items.length, index))
  return [...items.slice(0, at), item, ...items.slice(at)]
}

/** 从梯子落到画布上的某个点：留在那儿，顺序按落点算 */
export function dropAt(items: Item[], seed: Seed, x: number, y: number): Item[] {
  const width = WIDTH[seed.kind]
  return insertAt(items, indexAt(items, x, y), fromSeed(seed, { x: x - width / 2, y: y - 40 }))
}

/** 点一下加到末尾：接在最后一项右边（最后一项没摆过就跟着自动排） */
export function append(items: Item[], seed: Seed): Item[] {
  const last = items[items.length - 1]
  const pos = last?.pos ? { x: last.pos.x + WIDTH[last.kind] + GAP, y: last.pos.y } : undefined
  return [...items, fromSeed(seed, pos)]
}

export function remove(items: Item[], uid: number): Item[] {
  return items.filter((item) => item.uid !== uid)
}

/** 拖完一个节点：留在松手的地方，顺序按阅读顺序重算 */
export function place(items: Item[], uid: number, pos: XY): Item[] {
  return byReadingOrder(items.map((item) => (item.uid === uid ? { ...item, pos } : item)))
}

/** 整理：忘掉人摆的坐标，全部回到自动排 */
export function tidy(items: Item[]): Item[] {
  return items.map(({ pos: _pos, ...item }) => item as Item)
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
/** 画布 → 文件同形的 JSON：不点名的阶段一个名字、点名的一个清单、带参数的「能力: 参数」映射；断点一个词或「断点: 一句话」；
 *  人摆过就带 layout 块（每一项此刻的坐标，取整）。 */
export function toDraft(draft: Draft): WorkflowDraft {
  const stages: DraftItem[] = draft.items.map((item) => {
    if (item.kind === 'stop') return item.note.trim() ? { 断点: item.note.trim() } : '断点'
    if (item.caps.length === 0) return item.stage
    if (item.caps.every((p) => Object.keys(p.with).length === 0)) return { [item.stage]: item.caps.map((p) => p.cap) }
    return { [item.stage]: Object.fromEntries(item.caps.map((p) => [p.cap, Object.keys(p.with).length ? p.with : null])) }
  })
  const doc: WorkflowDraft = { name: draft.name.trim(), title: draft.title.trim(), summary: draft.summary.trim(), stages }
  if (arranged(draft.items)) doc.layout = positions(draft.items).map(({ x, y }) => [Math.round(x), Math.round(y)])
  return doc
}

/** 库里的一条 → 画布：名字照旧，存回去要勾「覆盖同名」；文件里有 layout 就照它摆 */
export function fromWorkflow(wf: Workflow): Draft {
  const items = wf.stages.map((item, i) => fromItem(item, wf.layout?.[i] ? { x: wf.layout[i][0], y: wf.layout[i][1] } : undefined))
  return { name: wf.name, title: wf.title, summary: wf.summary, items }
}

export function fromItem(item: FlowItem, pos?: XY): Item {
  if (item.kind === 'stop') return stopItem(item.note, pos)
  return stageItem(item.stage, item.caps.map((c) => ({ cap: c.cap, with: { ...c.with } })), pos)
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
