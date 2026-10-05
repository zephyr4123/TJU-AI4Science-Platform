// 一次产出的进度面板（外层 #242），在产出侧滑的最上面：照产它的能力挑那个能力自己的面板——每个能力一块定制的，不做通用的
// （主人 2026-10-05）。还没有面板的能力、早于进度文件的旧产出，这里什么都不画，侧滑照旧。
// 产出运行中时每两秒重读一次 `progress.jsonl`；跑完再读最后一次，面板停在最后的样子，当这次产出的摘要。
import type { WorkspaceClient } from '@/api/client'
import type { OutputDetail } from '@/api/types'
import { ErrorNote } from '@/components/bits'

import { type ProgressEvent, useProgress } from './events'
import { ReadPanel } from './ReadPanel'
import { readView } from './read'
import { SearchPanel } from './SearchPanel'
import { searchView } from './search'

interface PanelProps {
  events: ProgressEvent[]
  output: OutputDetail
  onOpenFile?: (path: string) => void
}

/** 能力名 → 它的面板。加一个能力的面板：写它自己的推导（事件 → 样子）与画法，再在这里加一行 */
const PANELS: Record<string, (props: PanelProps) => React.ReactNode> = {
  'literature-search': ({ events, output, onOpenFile }) => {
    // 缺省与 literature_search 的描述符一致；一次最多筛：种子 20 篇 + 第一轮两倍的每轮筛选数 + 每扩一轮一份
    const param = (name: string, fallback: number) => (typeof output.params[name] === 'number' ? output.params[name] as number : fallback)
    const maxHops = param('max_hops', 2)
    return <SearchPanel view={searchView(events, output.status, output.created_at)} onOpenFile={onOpenFile}
                        maxHops={maxHops} capacity={20 + param('per_hop', 30) * (2 + maxHops)} />
  },
  'literature-read': ({ events, output, onOpenFile }) => (
    <ReadPanel view={readView(events, output.status, output.created_at)} layoutKey={output.id} onOpenFile={onOpenFile} />
  ),
}

/** `onOpenFile` 拿到的是相对产出目录的路径；不给就不能点 */
export function ProgressPanel({ workspace, output, onOpenFile }: {
  workspace: WorkspaceClient; output: OutputDetail; onOpenFile?: (path: string) => void
}) {
  const live = output.status === 'running'
  const { events, error } = useProgress(workspace, output.id, live)
  const Panel = PANELS[output.by]
  if (!Panel || events === null) return null
  if (!live && events.length === 0) return null
  return (
    <section aria-label="进度" className="rounded-2xl bg-muted/50 px-4 pt-4 pb-3">
      {error && <ErrorNote text={error} className="mb-3" />}
      <Panel events={events} output={output} onOpenFile={onOpenFile} />
    </section>
  )
}
