// 看板上算出来的东西，纯函数、有单测：一条流程在等谁、下一步是哪个阶段、每次产出用哪个词、断点的短标签、侧滑里文件那一行。
import type { FlowOutput, FlowProgress, FlowProgressItem } from '@/api/types'

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

/** 一条流程现在在等谁，一句话：下一步：实验 · 助理 / 待确认：设计 · 1 / 运行中：实验 · 2 / 完成 / 流程文件有误 */
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
  return next ? `下一步：${next.stage} · 助理` : '完成'
}

/** 产出 id 上屏的写法：design/1 → 设计 · 1（P-21：机器的名字不上屏） */
export function outputName(id: string, nameOf: NameOf): string {
  const [slug, n] = id.split('/')
  return `${nameOf(slug)} · ${n}`
}

/** 文件按后缀归的种类；同样多时照这个顺序排，归不进去的算「其它」 */
const FILE_KINDS: [string, RegExp][] = [
  ['文档', /\.(md|txt)$/i],
  ['数据', /\.(jsonl?|csv|tsv|ya?ml|toml|npy|npz|h5|parquet)$/i],
  ['图片', /\.(png|jpe?g|gif|svg|webp|bmp|tiff?)$/i],
  ['PDF', /\.pdf$/i],
  ['代码', /\.(py|sh|ipynb|r|jl)$/i],
]

/** 产出侧滑里「文件」那一行：一共几个、各是什么（主人 2026-10-05：一次文献检索几百个文件，大半是原文切出来的图，
 *  不在侧滑里平铺，要看去文件镜头）。`9 个：图片 3、文档 2、…`，只有一种写 `2 个文档`，一个没有写「—」 */
export function filesWord(paths: string[]): string {
  if (paths.length === 0) return '—'
  const counts = new Map<string, number>()
  for (const path of paths) {
    const kind = FILE_KINDS.find(([, pattern]) => pattern.test(path))?.[0] ?? '其它'
    counts.set(kind, (counts.get(kind) ?? 0) + 1)
  }
  const order = [...FILE_KINDS.map(([kind]) => kind), '其它']
  const kinds = [...counts].sort(([a, m], [b, n]) =>
    (a === '其它' ? 1 : 0) - (b === '其它' ? 1 : 0) || n - m || order.indexOf(a) - order.indexOf(b))
  if (kinds.length > 1) return `${paths.length} 个：${kinds.map(([kind, n]) => `${kind} ${n}`).join('、')}`
  const [only] = kinds[0]
  if (only === '其它') return `${paths.length} 个`
  return `${paths.length} 个${/^[A-Z]/.test(only) ? ' ' : ''}${only}`
}
