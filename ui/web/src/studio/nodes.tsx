// 画布上的两种节点：研究阶段（装能力）与断点。位置由 model.layout 排，节点自己只管长相与四个把手
// （左右接同一行的边，上下接跨行的边）。
// 阶段节点是 reactbits 的 SpotlightCard 改装件（鼠标经过时一抹淡光）；断点是琥珀色的一小块，与脊柱上等人的那一格同色。
import { Handle, type Node, type NodeProps, Position } from '@xyflow/react'
import { HandPalm, Signature, Stamp, X } from '@phosphor-icons/react'
import { createElement } from 'react'

import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
import { stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { WIDTH } from './model'

export interface StageData extends Record<string, unknown> {
  n: number
  stage: string
  /** 点名的能力，标题已翻好 */
  caps: string[]
  problems: string[]
  onRemove: () => void
}
export interface StopData extends Record<string, unknown> {
  n: number
  note: string
  problems: string[]
  onRemove: () => void
}
export type StageNodeType = Node<StageData, 'stage'>
export type StopNodeType = Node<StopData, 'stop'>

// 把手只给边找位置用，不给人连线，藏起来
const HANDLE = '!size-1 !min-h-0 !min-w-0 !border-0 !bg-transparent'

/** 四个把手：同一行左进右出，换行时下出上进 */
function Handles() {
  return (
    <>
      <Handle id="l" type="target" position={Position.Left} className={HANDLE} isConnectable={false} />
      <Handle id="t" type="target" position={Position.Top} className={HANDLE} isConnectable={false} />
      <Handle id="r" type="source" position={Position.Right} className={HANDLE} isConnectable={false} />
      <Handle id="b" type="source" position={Position.Bottom} className={HANDLE} isConnectable={false} />
    </>
  )
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" aria-label={label} onPointerDown={(e) => e.stopPropagation()} onClick={onClick}
            className="nodrag grid size-6 place-items-center rounded-md text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:bg-muted hover:text-foreground focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-ring">
      <X className="size-3.5" />
    </button>
  )
}

/** 节点上的问题标记：红点，悬停看句子 */
function ProblemDot({ problems }: { problems: string[] }) {
  if (problems.length === 0) return null
  return <span role="img" aria-label={problems.join('；')} title={problems.join('\n')} className="size-2 shrink-0 rounded-full bg-bad" />
}

export function StageNode({ data, selected }: NodeProps<StageNodeType>) {
  return (
    <div className="group" style={{ width: WIDTH.stage }}>
      <Handles />
      <SpotlightCard spotlight="color-mix(in oklab, var(--primary) 14%, transparent)"
                     className={cn('rounded-xl transition-[border-color,box-shadow]', selected && 'border-primary shadow-[0_0_0_3px_color-mix(in_oklab,var(--primary)_22%,transparent)]',
                                   data.problems.length > 0 && !selected && 'border-bad/60')}>
        <div className="flex items-center gap-2 px-3 pt-2.5 pb-1">
          {createElement(stageIcon(data.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-[1.125rem] shrink-0 text-primary' })}
          <span className="min-w-0 flex-1 truncate font-serif text-[1rem] font-semibold">{data.stage}</span>
          <ProblemDot problems={data.problems} />
          <span className="tabular text-[0.6875rem] text-muted-foreground">{data.n}</span>
          <RemoveButton label={`删除第 ${data.n} 项`} onClick={data.onRemove} />
        </div>
        <ul className="flex flex-wrap gap-1 px-3 pb-3">
          {data.caps.length === 0
            ? <li className="text-[0.75rem] text-muted-foreground">不限能力</li>
            : data.caps.map((title) => <li key={title} className="rounded-md bg-muted px-1.5 py-0.5 text-[0.75rem]">{title}</li>)}
        </ul>
      </SpotlightCard>
    </div>
  )
}

export function StopNode({ data, selected }: NodeProps<StopNodeType>) {
  const icon = data.note === '发布' ? Stamp : data.note === '验收' ? Signature : HandPalm
  return (
    <div className="group" style={{ width: WIDTH.stop }}>
      <Handles />
      <div className={cn('rounded-xl border border-wait/60 bg-wait-soft px-3 py-2.5 text-wait transition-[border-color,box-shadow]',
                         selected && 'border-wait shadow-[0_0_0_3px_color-mix(in_oklab,var(--wait)_25%,transparent)]',
                         data.problems.length > 0 && !selected && 'border-bad/60')}>
        <div className="flex items-center gap-1.5">
          {createElement(icon, { weight: 'duotone', 'aria-hidden': true, className: 'size-[1.125rem] shrink-0' })}
          <span className="min-w-0 flex-1 truncate text-[0.875rem] font-semibold">断点</span>
          <ProblemDot problems={data.problems} />
          <span className="tabular text-[0.6875rem] text-wait/70">{data.n}</span>
          <RemoveButton label={`删除第 ${data.n} 项`} onClick={data.onRemove} />
        </div>
        <p className={cn('mt-0.5 truncate text-[0.75rem]', data.note ? 'text-wait' : 'text-wait/60')}>{data.note || '确认事项'}</p>
      </div>
    </div>
  )
}
