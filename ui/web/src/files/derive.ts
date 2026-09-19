// 文件镜头算出来的东西，纯函数、有单测：一条路径在工作区里是什么（阶段目录、某次产出、平台记录、普通文件）、
// 一个文件按什么方式渲染、csv / tsv 切成表、哪些产出冻结了。语义都从 `GET /workspaces/<id>` 拼，后端的树只给名字。
import type { OutputBrief, StageBoard, WorkspaceDetail } from '@/api/types'

/** 树里一行是什么：阶段目录（显示阶段名 + 图标）、某次产出（带状态）、平台记录（灰）、其它 */
export type RowMeaning =
  | { kind: 'stage'; stage: StageBoard }
  | { kind: 'output'; output: OutputBrief; frozen: boolean }
  | { kind: 'platform' }
  | { kind: 'plain' }

/** 被下游 `from` 引用过的产出 id：引用过就冻结（P-19），和签过字一样 */
export function referencedIds(doc: WorkspaceDetail): Set<string> {
  const found = new Set<string>()
  for (const stage of doc.stages) for (const o of stage.outputs) for (const id of o.from) found.add(id)
  return found
}

/** 路径 → 它所属的那次产出 id（`design/1/harness/x.py` → `design/1`）；不在任何产出目录下是 null */
export function outputIdOf(path: string, doc: WorkspaceDetail): string | null {
  const [slug, n] = path.split('/')
  if (!slug || !n || !/^\d+$/.test(n)) return null
  return doc.stages.some((s) => s.slug === slug) ? `${slug}/${n}` : null
}

export function meaningOf(path: string, doc: WorkspaceDetail, referenced: Set<string>): RowMeaning {
  const parts = path.split('/')
  if (parts.length === 1) {
    if (path.startsWith('.')) return { kind: 'platform' }
    const stage = doc.stages.find((s) => s.slug === path)
    if (stage) return { kind: 'stage', stage }
    return { kind: 'plain' }
  }
  if (parts.length === 2) {
    const id = outputIdOf(path, doc)
    const output = id ? doc.stages.flatMap((s) => s.outputs).find((o) => o.id === id) : undefined
    if (output) {
      const frozen = referenced.has(output.id) || (output.signed !== null && !output.signed.stale)
      return { kind: 'output', output, frozen }
    }
  }
  return { kind: 'plain' }
}

export type FileKind = 'markdown' | 'image' | 'table' | 'text'

const IMAGE = /\.(png|jpe?g|gif|svg|webp|bmp)$/i

/** 按后缀定渲染方式：markdown 排版、图片直接显示、csv / tsv 成表，其它原样 */
export function fileKind(path: string): FileKind {
  if (/\.md$/i.test(path)) return 'markdown'
  if (IMAGE.test(path)) return 'image'
  if (/\.(csv|tsv)$/i.test(path)) return 'table'
  return 'text'
}

export const TABLE_ROWS = 200

/** csv / tsv 切表：第一行是表头；最多 TABLE_ROWS 行，`more` 是没显示的行数。引号里的逗号不特殊处理——数据表不是电子表格 */
export function parseTable(text: string, path: string): { header: string[]; rows: string[][]; more: number } {
  const delim = /\.tsv$/i.test(path) ? '\t' : ','
  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== '')
  const [first = '', ...rest] = lines
  const header = first.split(delim)
  const rows = rest.slice(0, TABLE_ROWS).map((line) => line.split(delim))
  return { header, rows, more: Math.max(0, rest.length - TABLE_ROWS) }
}

/** 一条路径的每一级祖先（不含自己）：`a/b/c` → `a`、`a/b`；树按它逐级展开定位 */
export function ancestors(path: string): string[] {
  const parts = path.split('/').filter(Boolean)
  return parts.slice(0, -1).map((_, i) => parts.slice(0, i + 1).join('/'))
}

/** 根一层按工作区的骨架排：需求、原件、流、七个阶段按顺序、其它、平台记录（点开头的）垫底；底下各层照后端给的顺序 */
export function orderRoot<T extends { name: string; kind: 'dir' | 'file' }>(entries: T[], doc: WorkspaceDetail): T[] {
  const rank = (e: T): number => {
    if (e.name === 'requirement.md') return 0
    if (e.name === 'requirement.lock') return 1
    if (e.name === 'materials') return 2
    if (e.name === 'flows') return 3
    const stage = doc.stages.findIndex((s) => s.slug === e.name)
    if (stage >= 0) return 10 + stage
    if (e.name.startsWith('.')) return 90
    return 50
  }
  return [...entries].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))
}
