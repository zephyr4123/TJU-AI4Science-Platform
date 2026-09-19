// 画布上的两种节点：研究阶段（装能力）与断点。位置由 model.layout 排，节点自己只管长相与四个把手
// （左右接同一行的边，上下接跨行的边）。序号是真序列（文件里的第几项），所以敢放大写成宋体数字。
// 阶段节点是 reactbits 的 SpotlightCard 改装件（鼠标经过时一抹淡光），点名的能力是一枚枚小片（名字、hover 一行、点了跳详情，P-21）；
// 断点是琥珀色的一块，直接写确认事项（上游产出经人确认后下游方可读取）。
import { Handle, type Node, type NodeProps, Position } from '@xyflow/react'
import { Signature, X } from '@phosphor-icons/react'
import { createElement } from 'react'

import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
import { stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { WIDTH } from './model'

/** 节点上一枚能力小片：名字直接显示、一行 hover、点了跳详情（P-21） */
export interface CapChip { name: string; title: string; brief: string }
export interface StageData extends Record<string, unknown> {
  n: number
  stage: string
  caps: CapChip[]
  problems: string[]
  onRemove: () => void
  onOpenCap: (name: string) => void
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

function RemoveButton({ label, onClick, className }: { label: string; onClick: () => void; className?: string }) {
  return (
    <button type="button" aria-label={label} onPointerDown={(e) => e.stopPropagation()} onClick={onClick}
            className={cn('nodrag absolute top-1.5 right-1.5 grid size-6 place-items-center rounded-md opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-ring', className)}>
      <X className="size-3.5" />
    </button>
  )
}

/** 节点上的问题标记：红点，悬停看句子 */
function ProblemDot({ problems }: { problems: string[] }) {
  if (problems.length === 0) return null
  return <span role="img" aria-label={problems.join('；')} title={problems.join('\n')} className="size-2 shrink-0 rounded-full bg-bad" />
}

/** 右下角的序号：宋体、淡，像图纸上的编号 */
function Numeral({ n, className }: { n: number; className?: string }) {
  return <span aria-hidden className={cn('absolute right-3 bottom-1.5 font-serif text-[1.5rem] leading-none font-semibold tabular', className)}>{n}</span>
}

export function StageNode({ data, selected }: NodeProps<StageNodeType>) {
  const bad = data.problems.length > 0
  return (
    <div className="group relative" style={{ width: WIDTH.stage }}>
      <Handles />
      <SpotlightCard spotlight="color-mix(in oklab, var(--primary) 16%, transparent)"
                     className={cn('rounded-2xl transition-[border-color,box-shadow]',
                                   selected ? 'border-primary shadow-[0_0_0_3px_color-mix(in_oklab,var(--primary)_22%,transparent)]' : bad ? 'border-bad/60' : 'shadow-sm')}>
        <div className="relative px-3.5 pt-3 pb-3">
          <div className="flex items-center gap-2 pr-6">
            {createElement(stageIcon(data.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-[1.375rem] shrink-0 text-primary' })}
            <span className="min-w-0 flex-1 truncate font-serif text-[1.125rem] font-semibold">{data.stage}</span>
            <ProblemDot problems={data.problems} />
          </div>
          <ul className="mt-2 flex min-h-5 flex-wrap gap-1 pr-7">
            {data.caps.length === 0
              ? <li className="text-[0.75rem] text-muted-foreground">不限能力</li>
              : data.caps.map((cap) => (
                <li key={cap.name}>
                  <button type="button" title={cap.brief} onPointerDown={(e) => e.stopPropagation()} onClick={() => data.onOpenCap(cap.name)}
                          className="nodrag rounded-md bg-primary/10 px-1.5 py-0.5 text-[0.75rem] text-primary transition-colors hover:bg-primary/20 focus-visible:outline-2 focus-visible:outline-ring">
                    {cap.title}
                  </button>
                </li>
              ))}
          </ul>
          <Numeral n={data.n} className="text-foreground/20" />
          <RemoveButton label={`删除第 ${data.n} 项`} onClick={data.onRemove} className="text-muted-foreground hover:bg-muted hover:text-foreground" />
        </div>
      </SpotlightCard>
    </div>
  )
}

export function StopNode({ data, selected }: NodeProps<StopNodeType>) {
  const bad = data.problems.length > 0
  return (
    <div className="group relative" style={{ width: WIDTH.stop }}>
      <Handles />
      <div className={cn('relative rounded-2xl border bg-wait-soft px-3.5 pt-3 pb-3 text-wait transition-[border-color,box-shadow]',
                         selected ? 'border-wait shadow-[0_0_0_3px_color-mix(in_oklab,var(--wait)_25%,transparent)]' : bad ? 'border-bad/60' : 'border-wait/50 shadow-sm')}>
        <div className="flex items-center gap-2 pr-5">
          <Signature weight="duotone" aria-hidden className="size-[1.375rem] shrink-0" />
          <ProblemDot problems={data.problems} />
        </div>
        <p className={cn('mt-2 line-clamp-2 min-h-5 pr-6 text-[0.875rem] leading-snug font-semibold', !data.note && 'font-normal text-wait/60')}>{data.note || '确认事项'}</p>
        <Numeral n={data.n} className="text-wait/35" />
        <RemoveButton label={`删除第 ${data.n} 项`} onClick={data.onRemove} className="text-wait/70 hover:bg-wait/15 hover:text-wait" />
      </div>
    </div>
  )
}
