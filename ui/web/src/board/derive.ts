// 看板上算出来的东西，纯函数、有单测：一条流程在等谁、下一步是哪个阶段、时间线上每个节点什么状态、每次产出叫什么与用哪个词、
// 哪些产出不在流程里、一个阶段的产出怎么折、产出悬浮窗记录里的几处说法。
import type { FlowProgress, FlowProgressItem, OutputBrief, StageBoard } from '@/api/types'

/** 哪些产出待人确认：流程里那一项后面是断点、产出还没确认（或确认之后又改了） */
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

/** 下一步是流程里的第几项（阶段）：step 之后第一个阶段项；走完了是 null */
export function nextStage(flow: FlowProgress): Extract<FlowProgressItem, { kind: 'stage' }> | null {
  const items = flow.items ?? []
  const step = flow.step ?? -1
  for (const item of items) if (item.index > step && item.kind === 'stage') return item
  return null
}

export type OutputState = 'running' | 'failed' | 'pending' | 'confirmed' | 'done'

/** 一次产出的状态：运行中 / 失败 / 待确认 / 已确认 / 完成（确认之后目录又改了，回到完成） */
export function stateOf(o: Pick<OutputBrief, 'id' | 'status' | 'signed'>, pending: Set<string>): OutputState {
  if (o.status === 'running') return 'running'
  if (o.status === 'failed') return 'failed'
  if (pending.has(o.id)) return 'pending'
  if (o.signed && !o.signed.stale) return 'confirmed'
  return 'done'
}

type StageItem = Extract<FlowProgressItem, { kind: 'stage' }>
type StopItem = Extract<FlowProgressItem, { kind: 'stop' }>

/** 时间线上一个阶段：走过（流程走到它之后、或已经有产出）/ 当前（下一步就是它，还没走完）/ 没到 */
export function stageState(item: StageItem, flow: FlowProgress): 'done' | 'current' | 'todo' {
  if (flow.waiting !== 'done' && nextStage(flow)?.index === item.index) return 'current'
  return item.index <= (flow.step ?? -1) || item.outputs.length > 0 ? 'done' : 'todo'
}

/** 时间线上一个断点：已确认 / 待确认（流程正停在它这儿等人）/ 没到 */
export function stopState(item: StopItem, flow: FlowProgress): 'signed' | 'pending' | 'todo' {
  if (item.signed) return 'signed'
  return item.index === (flow.step ?? -1) + 1 && flow.waiting === 'sign' ? 'pending' : 'todo'
}

/** 流程外的产出：没被任何一条流程的哪一项收下的都算——没记流程的，记了流程却没记第几步的也在这，一次都不漏；
 *  按阶段的顺序、再按第几次排 */
export function looseOutputs(stages: StageBoard[], flows: FlowProgress[]): OutputBrief[] {
  const placed = new Set(flows.flatMap((f) => (f.items ?? []).flatMap((item) => item.outputs.map((o) => o.id))))
  return stages.flatMap((s) => s.outputs.filter((o) => !placed.has(o.id)).sort((a, b) => runOf(a.id) - runOf(b.id)))
}

/** 一个阶段的产出：新的在前，露最近 `keep` 次，待确认与运行中的不管多旧都露着（人要一眼看见）；
 *  其余折起，数一下折起的里头有几次失败 */
export function fold(outputs: OutputBrief[], pending: Set<string>, keep = 2): { shown: OutputBrief[]; hidden: OutputBrief[]; failed: number } {
  const newest = [...outputs].sort((a, b) => runOf(b.id) - runOf(a.id))
  const shown = newest.filter((o, i) => i < keep || o.status === 'running' || pending.has(o.id))
  const hidden = newest.filter((o) => !shown.includes(o))
  return { shown, hidden, failed: hidden.filter((o) => o.status === 'failed').length }
}

/** 第几次：design/3 → 3 */
function runOf(id: string): number {
  return Number(id.split('/').at(-1))
}

/** 目录名 → 阶段名（`GET /stages` 给的表） */
export type NameOf = (slug: string) => string

/** 一条流程现在在等谁，一句话：下一步：实验阶段 · 助理 / 待确认：设计阶段第 1 次 / 运行中：实验阶段第 2 次 / 完成 / 流程文件有误 */
export function waitingSentence(flow: FlowProgress, pending: Set<string>, nameOf: NameOf): string {
  if (flow.problems.length > 0 || !flow.items) return '流程文件有误'
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
  return next ? `下一步：${next.stage}阶段 · 助理` : '完成'
}

/** 产出 id 上屏的写法（P-21：机器的名字不上屏）：design/1 → 设计阶段第 1 次；读的是别的工作区的（`gua:analysis/1`），
 *  带上那个工作区的名字，不知道名字就说「另一个工作区」 */
export function outputName(id: string, nameOf: NameOf, workspaceOf?: (id: string) => string | undefined): string {
  const [ws, local] = id.includes(':') ? id.split(':', 2) : [null, id]
  const [slug, n] = local.split('/')
  const own = `${nameOf(slug)}阶段第 ${n} 次`
  if (ws === null) return own
  const title = workspaceOf?.(ws)
  return title ? `「${title}」的${own}` : `另一个工作区的${own}`
}

/** 文件按后缀归的种类；同样多时照这个顺序排，归不进去的算「其它」 */
const FILE_KINDS: [string, RegExp][] = [
  ['文档', /\.(md|txt)$/i],
  ['数据', /\.(jsonl?|csv|tsv|ya?ml|toml|npy|npz|h5|parquet)$/i],
  ['图片', /\.(png|jpe?g|gif|svg|webp|bmp|tiff?)$/i],
  ['PDF', /\.pdf$/i],
  ['代码', /\.(py|sh|ipynb|r|jl)$/i],
]

/** 产出悬浮窗里「生成文件」那一行：各种类几个，从多到少（主人 2026-10-05：一次文献检索几百个文件，大半是原文切出来的图，
 *  不在窗里平铺，要看去文件镜头） */
export function fileKinds(paths: string[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const path of paths) {
    const kind = FILE_KINDS.find(([, pattern]) => pattern.test(path))?.[0] ?? '其它'
    counts.set(kind, (counts.get(kind) ?? 0) + 1)
  }
  const order = [...FILE_KINDS.map(([kind]) => kind), '其它']
  return [...counts].sort(([a, m], [b, n]) =>
    (a === '其它' ? 1 : 0) - (b === '其它' ? 1 : 0) || n - m || order.indexOf(a) - order.indexOf(b))
}

/** 跑了多久，按分钟说：不到 1 分钟 / 9 分钟 / 6 小时 57 分钟 */
export function tookWord(start: string, end: string): string {
  const minutes = Math.floor(Math.max(0, Date.parse(end) - Date.parse(start)) / 60_000)
  if (minutes < 1) return '不到 1 分钟'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (!h) return `${m} 分钟`
  return m ? `${h} 小时 ${m} 分钟` : `${h} 小时`
}

/** 悬浮窗标题下那一行：literature/3 → 文献阶段 · 第 3 次产出（别处的小片写「文献 · 3」，这里地方够，说全） */
export function outputLine(id: string, nameOf: NameOf): string {
  const [slug, n] = id.split('/')
  return `${nameOf(slug)}阶段 · 第 ${n} 次产出`
}
