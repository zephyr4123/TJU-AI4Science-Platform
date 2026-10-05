// 文献精读的进度面板（外层 #245）：一条流水线，原文 → 精读 → 核对 → 笔记。每篇文献是一枚六边形：开头全在「原文」那堆（就是
// 检索蜂巢里下到原文的那些实心格），开读时滑进「精读」的一个空位（同时几个会话就几个位）、在位上呼吸，读完滑进「笔记」那堆——
// 原句在原文里全找到的是铜绿，有没找到的淡一些；没读成的落到下面一格。「核对」是一个圆环：读完的笔记里原句找到了几成。
// 字只有方块名和数；悬停一枚看题目，点笔记堆里的一枚打开那篇笔记；其余进「详情」。
import { LayoutGroup, motion, useReducedMotion } from 'motion/react'
import { type MouseEvent, type ReactNode, useRef, useState } from 'react'

import { Clock } from '@/components/Clock'
import { cn } from '@/lib/utils'

import type { Phase } from './events'
import { Details, Figure, Hex, HoverNote, Station, Wire } from './kit'
import { noteAnchor } from './note'
import type { Paper, ReadView } from './read'

/** 一枚六边形的宽（px）；在读的那几枚放大到位上 */
const SIZE = 12
const BIG = 18
/** 一堆里一行几枚 */
const PER_ROW = 7
const MOVE = { duration: 0.55, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] }

export function ReadPanel({ view, layoutKey, onOpenFile }: {
  view: ReadView
  /** 这次产出的 id：六边形在几堆之间滑动认的是它 + 篇号 */
  layoutKey: string
  onOpenFile?: (path: string) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ paper: Paper; x: number; y: number } | null>(null)
  const live = !view.ended
  const of = (state: Paper['state']) => view.papers.filter((p) => p.state === state)
  const queued = of('queued')
  const reading = of('reading')
  const done = of('done')
  const failed = of('failed')
  const total = view.papers.length
  const phase = (running: boolean, finished: boolean): Phase =>
    running ? 'running' : finished ? 'done' : live ? 'pending' : 'skipped'
  const enter = (e: MouseEvent<HTMLElement>, paper: Paper) => {
    const at = noteAnchor(e.currentTarget, box.current)
    if (at) setHover({ paper, ...at })
  }
  const dot = (p: Paper, i: number) => (
    <Dot key={p.n} paper={p} layoutId={`${layoutKey}:${p.n}`} onEnter={enter} onLeave={() => setHover(null)}
         at={p.state === 'reading' ? null : cellAt(i)}
         onOpen={p.state === 'done' && onOpenFile ? () => onOpenFile(`notes/${p.n}/note.md`) : undefined} />
  )
  const reads = live && (reading.length > 0 || queued.length > 0)
  return (
    <div ref={box} className="@container relative space-y-4">
      <LayoutGroup id={layoutKey}>
        {/* 宽的时候一行从左往右，窄的时候一列从上往下：连线跟着换方向 */}
        <div className="mx-auto flex max-w-[16rem] flex-col items-stretch @md:max-w-none @md:flex-row">
          <Station label="原文" phase={phase(false, total > 0)} className="@md:w-[8.5rem]">
            <Figure value={total ? queued.length : null} of={total || null} />
            <Pile count={queued.length}>{queued.map(dot)}</Pile>
          </Station>
          <Link active={reads} />
          <div className="flex shrink-0 flex-col gap-2 @md:w-[6.25rem]">
            <Station label="精读" phase={phase(reads, total > 0 && done.length + failed.length === total)}
                     since={reads ? view.started : null} title={`同时读 ${view.sessions} 篇`}>
              <Slots count={Math.max(view.sessions, reading.length)}>{reading.map(dot)}</Slots>
            </Station>
            {failed.length > 0 && (
              <Station label="没读成" phase="failed" className="py-2">
                <Pile count={failed.length}>{failed.map(dot)}</Pile>
              </Station>
            )}
          </div>
          <Link active={live && done.length > 0} top />
          <Station label="核对" phase={phase(false, done.length > 0)} className="@md:w-[4.5rem] @md:self-start" title="笔记里的原句在原文里找得到几成">
            <Ring found={view.found} quotes={view.quotes} />
          </Station>
          <Link active={live && done.length > 0} top />
          <Station label="笔记" phase={phase(false, done.length > 0)} className="@md:w-[8.5rem]">
            <Figure value={done.length || null} of={total || null} />
            <Pile count={done.length}>{done.map(dot)}</Pile>
          </Station>
        </div>
      </LayoutGroup>
      <div className="flex items-center gap-4">
        <Details rows={details(view)} />
        {live && <span className="ml-auto inline-flex items-center gap-1.5 text-[0.75rem] text-primary">
          <span className="size-1.5 animate-pulse rounded-full bg-primary" /><Clock since={view.started} />
        </span>}
      </div>
      {hover && <HoverNote at={hover} title={hover.paper.title} note={note(hover.paper)} />}
    </div>
  )
}

/** 两步之间的线：宽的时候横着（`top` 是连到方块头上那一行，给矮的「核对」对齐），窄的时候竖着 */
function Link({ active, top = false }: { active: boolean; top?: boolean }) {
  return (
    <>
      <Wire vertical active={active} className="h-4 self-center @md:hidden" />
      <Wire active={active} className={cn('hidden min-w-3 flex-1 @md:flex', top && '@md:self-start @md:pt-[2.1rem]')} />
    </>
  )
}

/** 一堆里第 i 枚的位置：一行 PER_ROW 枚，奇数行错开半枚，排成蜂窝 */
function cellAt(i: number): { left: number; top: number } {
  const row = Math.floor(i / PER_ROW)
  const step = SIZE + 1.5
  return { left: (i % PER_ROW) * step + (row % 2) * (step / 2), top: row * SIZE * 0.95 }
}

/** 一堆六边形（位置由 cellAt 给）：高度跟着行数长 */
function Pile({ count, children }: { count: number; children: React.ReactNode }) {
  const rows = Math.ceil(count / PER_ROW)
  return <div className="relative mt-1" style={{ height: rows ? (rows - 1) * SIZE * 0.95 + SIZE * 1.16 : 16 }}>{children}</div>
}

/** 精读里的空位：同时几个会话就几个，空着的是虚线六边形 */
function Slots({ count, children }: { count: number; children: React.ReactNode[] }) {
  return (
    <div className="grid grid-cols-2 place-items-center gap-1.5 pt-1">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="relative grid size-7 place-items-center">
          <Hex size={BIG + 2} className="absolute bg-foreground/12"><Hex size={BIG} className="absolute top-[1.15px] left-px bg-card" /></Hex>
          {children[i]}
        </div>
      ))}
    </div>
  )
}

/** 一篇文献。layoutId 一样，换了堆就从原来的位置滑过去；`at` 是在堆里的位置，在读的那几枚在位上（null） */
function Dot({ paper, layoutId, at, onEnter, onLeave, onOpen }: {
  paper: Paper; layoutId: string; at: { left: number; top: number } | null
  onEnter: (e: MouseEvent<HTMLElement>, p: Paper) => void; onLeave: () => void; onOpen?: () => void
}) {
  const still = useReducedMotion() === true
  const tone = paper.state === 'done' ? (paper.found < paper.quotes ? 'bg-ok/50' : 'bg-ok')
    : paper.state === 'failed' ? 'bg-bad' : 'bg-primary'
  return (
    <motion.span layoutId={layoutId} layout={still ? false : true} transition={MOVE}
                 role={onOpen ? 'button' : undefined} tabIndex={onOpen ? 0 : undefined} aria-label={paper.title}
                 onMouseEnter={(e) => onEnter(e, paper)} onMouseLeave={onLeave}
                 onClick={onOpen} onKeyDown={onOpen ? (e) => { if (e.key === 'Enter') onOpen() } : undefined}
                 style={at ?? undefined}
                 className={cn(at ? 'absolute' : 'relative', 'inline-block leading-none', onOpen && 'cursor-pointer')}>
      <Hex size={at ? SIZE : BIG - 3} className={cn(tone, 'block transition-colors duration-500', !at && 'animate-glimmer')}>
        {paper.state === 'failed' && <Hex size={SIZE - 3} className="absolute top-[1.7px] left-[1.5px] bg-card" />}
      </Hex>
    </motion.span>
  )
}

/** 核对：一个圆环，读完的笔记里原句在原文找到了几成 */
function Ring({ found, quotes }: { found: number; quotes: number }) {
  const r = 15
  const c = 2 * Math.PI * r
  const share = quotes ? found / quotes : 0
  return (
    <div className="relative mx-auto mt-1 size-10" title={quotes ? `原句 ${quotes} 条，在原文找到 ${found} 条` : undefined}>
      <svg viewBox="0 0 40 40" className="size-10 -rotate-90">
        <circle cx={20} cy={20} r={r} fill="none" strokeWidth={4} className="stroke-foreground/10" />
        <circle cx={20} cy={20} r={r} fill="none" strokeWidth={4} strokeLinecap="round" className="stroke-ok transition-[stroke-dasharray] duration-500"
                strokeDasharray={`${c * share} ${c}`} />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-[0.6875rem] font-semibold tabular-nums">
        {quotes ? `${Math.round(share * 100)}%` : '—'}
      </span>
    </div>
  )
}

function note(p: Paper): string {
  if (p.state === 'done') return `原句 ${p.quotes} 条，在原文找到 ${p.found} 条`
  if (p.state === 'failed') return p.why || '没读成'
  return p.state === 'reading' ? '精读中' : '排队'
}

function details(view: ReadView): [string, ReactNode][] {
  const done = view.papers.filter((p) => p.state === 'done').length
  const rows: [string, ReactNode][] = [['精读', `同时读 ${view.sessions} 篇 · 读完 ${done} / ${view.papers.length} 篇`]]
  if (view.quotes) rows.push(['核对', `摘录原句 ${view.quotes} 条 → 在原文找到 ${view.found} 条`])
  // 没读成的题目给成节点：题目里的数（GPT-4 这类）不该当成数加重
  for (const p of view.papers.filter((x) => x.state === 'failed')) rows.push(['没读成', <span key={p.n}>{p.title}：{p.why || '中途停止'}</span>])
  return rows
}
