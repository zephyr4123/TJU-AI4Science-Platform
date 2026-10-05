// 文献检索的进度面板（外层 #244）：左边一列方块 + 连线是检索走的几步（种子 → 汇集 → 筛选 ⟲ 扩展 → 原文），正在跑的那一步一圈
// 靛光呼吸、通向它的线在流；筛选左边一道自环是「扩展一轮、再筛一轮」，几颗圆点是第几轮。右边是收录的蜂巢：筛过的每篇一格，
// 第一轮在正中、往外一圈一圈是扩出来的；空心是没收、淡靛是收了、实心是下到了原文；正在筛的那一批是虚格。悬停一格看题目，
// 点有原文的那格打开原文。数只放在方块上，其余进「详情」。
import { useMemo, useRef, useState, type MouseEvent } from 'react'

import { Clock } from '@/components/Clock'
import { cn } from '@/lib/utils'

import type { Phase } from './events'
import { center, hexPoints, ringsFor, spiral } from './hex'
import { Details, Figure, HoverNote, Station, Wire } from './kit'
import { noteAnchor } from './note'
import type { Cell, CellState, SearchView, Source } from './search'

/** 蜂巢一格的外接圆半径（px）；格与格之间留一点缝 */
const R = 12
const GAP = 0.9
/** 新来的一批格子逐个浮出来，一批最多拉这么长 */
const STAGGER_MS = 12
const STAGGER_MAX_MS = 700

const CELL: Record<CellState, string> = {
  screening: 'fill-transparent stroke-primary/60 [stroke-dasharray:2_2] animate-glimmer',
  out: 'fill-transparent stroke-foreground/20',
  in: 'fill-primary/25 stroke-primary/35',
  text: 'fill-primary stroke-primary',
}
const CELL_WORD: Record<CellState, string> = { screening: '筛选中', out: '未收录', in: '收录', text: '收录，有原文' }

export function SearchPanel({ view, maxHops, capacity, onOpenFile }: {
  view: SearchView
  /** 最多扩几轮（这次产出的参数）：自环上画几颗圆点 */
  maxHops: number
  /** 这次最多会筛几篇（按参数算的上限）：蜂巢一开始就按它画好淡框，跑的时候格子从正中往外填，画布不跟着变 */
  capacity: number
  /** 打开这次产出里的一个文件（相对产出目录）；不给就不能点 */
  onOpenFile?: (path: string) => void
}) {
  const { seeds, gather, screen, expand, fulltext } = view
  const flowing = (p: Phase) => p === 'running'
  // 宽的时候左边一列是流程、右边是蜂巢，筛选与原文各一条线连进蜂巢（筛出来的格子长在里面、下到的原文点亮格子）；
  // 窄的时候蜂巢落到流程底下，那两条线不画
  return (
    <div className="@container space-y-3">
      <div className="grid grid-cols-[minmax(0,1fr)] justify-items-center pl-7 @md:grid-cols-[7rem_minmax(1.5rem,1fr)_auto] @md:justify-items-stretch">
        <Station label="种子" phase={seeds.phase} since={seeds.since} className="w-[7rem]" title="助理按需求写检索词、找种子论文">
          <Figure value={seeds.seeds} />
        </Station>
        <Wire vertical active={flowing(gather.phase)} className="col-start-1 h-5 justify-self-center" />
        <Station label="汇集" phase={gather.phase} since={gather.since} className="col-start-1 w-[7rem]" title="到四家学术库查、去重">
          <Figure value={gather.found} />
          <Sources sources={gather.sources} live={gather.phase === 'running'} />
        </Station>
        <Wire vertical active={flowing(screen.phase)} className="col-start-1 h-5 justify-self-center" />
        <div className="relative col-start-1 w-[7rem]">
          <Loop rounds={view.rounds} maxHops={maxHops} phase={expand.phase} since={expand.since} hop={expand.hop} />
          <Station label="筛选" phase={screen.phase} since={screen.since} title="助理读摘要，判相关不相关">
            <Figure value={started(screen.phase) ? screen.included : null} of={screen.screened || null} />
          </Station>
        </div>
        <Wire active={flowing(screen.phase)} className="col-start-2 row-start-5 hidden @md:flex" />
        <Wire vertical active={flowing(fulltext.phase)} className="col-start-1 h-5 justify-self-center" />
        <Station label="原文" phase={fulltext.phase} since={fulltext.since} className="col-start-1 w-[7rem]" title="下载收录论文的原文并解析">
          <Figure value={started(fulltext.phase) ? fulltext.ok : null} of={fulltext.n} />
        </Station>
        <Wire active={flowing(fulltext.phase)} className="col-start-2 row-start-7 hidden @md:flex" />
        <div className="col-start-1 mt-5 -ml-7 justify-self-stretch @md:col-start-3 @md:row-span-7 @md:row-start-1 @md:mt-0 @md:ml-0 @md:self-center">
          <Hive cells={view.cells} capacity={capacity} onOpenFile={onOpenFile} />
        </div>
      </div>
      <div className="flex items-center gap-4">
        <Details rows={details(view)} />
        {!view.ended && <span className="ml-auto inline-flex items-center gap-1.5 text-[0.75rem] text-primary">
          <span className="size-1.5 animate-pulse rounded-full bg-primary" /><Clock since={view.started} />
        </span>}
      </div>
    </div>
  )
}

const started = (p: Phase) => p !== 'pending' && p !== 'skipped'

/** 汇集方块里四颗点：一家一颗，查完亮、查失败红，还在查的一闪一闪；悬停看是哪家、几条 */
function Sources({ sources, live }: { sources: Source[]; live: boolean }) {
  return (
    <div className="flex gap-1 pt-0.5">
      {sources.map((s) => (
        <span key={s.name} title={`${s.name}${s.done ? (s.failed ? ' 失败' : ` ${s.hits ?? 0} 条`) : ''}`}
              className={cn('size-1.5 rounded-full transition-colors duration-300',
                            s.failed ? 'bg-bad' : s.done ? 'bg-foreground/45' : cn('bg-foreground/15', live && 'animate-glimmer'))} />
      ))}
    </div>
  )
}

/** 筛选左边的自环：筛完一轮往外扩一轮再筛。圆点一颗一轮扩展，扩完的实心、正在扩的闪；悬停看第几轮 */
function Loop({ rounds, maxHops, phase, since, hop }: {
  rounds: SearchView['rounds']; maxHops: number; phase: Phase; since: string | null; hop: number | null
}) {
  const live = phase === 'running'
  const expanded = (h: number) => rounds.some((r) => r.hop === h && r.admitted !== null)
  return (
    <div className="absolute inset-y-0.5 -left-7 w-7" title={live && hop ? `扩展第 ${hop + 1} 轮` : '扩展'}>
      <svg viewBox="0 0 24 40" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible" aria-hidden>
        <path d="M24 9 C2 9 2 31 24 31" fill="none" vectorEffect="non-scaling-stroke" strokeWidth={1.5}
              className={cn(live ? 'stroke-primary [stroke-dasharray:4_3] animate-dash-flow' : 'stroke-foreground/20')} />
      </svg>
      <svg viewBox="0 0 6 8" className={cn('absolute top-[8px] right-0 h-2 w-1.5 -translate-y-1/2', live ? 'fill-primary' : 'fill-foreground/30')} aria-hidden>
        <path d="M0 0 6 4 0 8z" />
      </svg>
      <div className="absolute inset-y-0 left-1.5 flex w-3 flex-col items-center justify-center gap-1">
        {Array.from({ length: Math.max(maxHops, 0) }, (_, i) => i + 1).map((h) => (
          <span key={h} className={cn('size-[5px] rounded-full transition-colors duration-300',
                                      expanded(h) ? 'bg-primary/70' : live && hop === h ? 'bg-primary animate-glimmer' : 'bg-foreground/15')} />
        ))}
      </div>
      {live && since && <Clock since={since} className="absolute top-full left-0 text-[0.625rem] text-primary/80" />}
    </div>
  )
}

/** 收录的蜂巢。格子的像素大小固定，画布按「最多会筛几篇」一开始就定好（还没填的位置是淡底），已有的格子一动不动，只有新来的浮出来；
 *  真筛的比上限多（种子没算准）才往外加一圈 */
function Hive({ cells, capacity, onOpenFile }: { cells: Cell[]; capacity: number; onOpenFile?: (path: string) => void }) {
  const box = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ cell: Cell; x: number; y: number } | null>(null)
  // 第一次画出来时已有的格子不浮：打开一次跑完的检索不该先演一遍；之后来的才浮
  const [first] = useState(() => new Set(cells.map((c) => c.key)))
  const rings = Math.max(ringsFor(Math.max(cells.length, capacity)), 2)
  const slots = 1 + 3 * rings * (rings + 1)
  const halfW = Math.sqrt(3) * R * (rings + 0.5) + 2
  const halfH = 1.5 * R * rings + R + 2
  const placed = useMemo(() => cells.map((cell, i) => ({ cell, at: center(spiral(i), R) })), [cells])
  let fresh = 0
  const enter = (e: MouseEvent<SVGPolygonElement>, cell: Cell) => {
    const at = noteAnchor(e.currentTarget, box.current)
    if (at) setHover({ cell, ...at })
  }
  return (
    <div ref={box} className="relative">
      <svg viewBox={`${-halfW} ${-halfH} ${halfW * 2} ${halfH * 2}`} style={{ width: halfW * 2 }}
           className="mx-auto block h-auto max-w-full" role="img" aria-label={`筛过 ${cells.filter((c) => c.state !== 'screening').length} 篇`}>
        {Array.from({ length: slots - cells.length }, (_, i) => {
          const [x, y] = center(spiral(cells.length + i), R)
          return <polygon key={`_${i}`} points={hexPoints(x, y, R - GAP)} className="fill-foreground/[0.035]" />
        })}
        {placed.map(({ cell, at: [x, y] }) => {
          const animate = !first.has(cell.key)
          const delay = animate ? Math.min(fresh++ * STAGGER_MS, STAGGER_MAX_MS) : 0
          const openable = cell.state === 'text' && onOpenFile
          return (
            <g key={cell.key}>
              <polygon points={hexPoints(x, y, R - GAP)} strokeWidth={1}
                       className={cn('transition-[fill,stroke] duration-500 [transform-box:fill-box] [transform-origin:center] hover:stroke-foreground hover:[stroke-width:1.5]',
                                     CELL[cell.state], animate && 'animate-cell-in', openable && 'cursor-pointer')}
                       style={animate ? { animationDelay: `${delay}ms` } : undefined}
                       onMouseEnter={cell.state === 'screening' ? undefined : (e) => enter(e, cell)}
                       onMouseLeave={() => setHover(null)}
                       onClick={openable ? () => onOpenFile(`papers/${cell.key}/paper.md`) : undefined} />
              {cell.seed && cell.state !== 'out' && <circle cx={x} cy={y} r={1.8} className="pointer-events-none fill-card" />}
            </g>
          )
        })}
      </svg>
      <Legend cells={cells} />
      {hover && <HoverNote at={hover} title={hover.cell.title}
                           note={`第 ${hover.cell.hop + 1} 轮${hover.cell.seed ? '，种子' : ''}，${CELL_WORD[hover.cell.state]}`} />}
    </div>
  )
}

/** 蜂巢底下一行图例：只列出现了的几种 */
function Legend({ cells }: { cells: Cell[] }) {
  const present = new Set(cells.map((c) => c.state))
  const items: [CellState, string][] = [['screening', '筛选中'], ['out', '未收录'], ['in', '收录'], ['text', '有原文']]
  if (cells.length === 0) return null
  return (
    <div className="mt-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[0.6875rem] text-muted-foreground">
      {items.filter(([s]) => present.has(s)).map(([s, word]) => (
        <span key={s} className="inline-flex items-center gap-1">
          <svg viewBox="-6 -7 12 14" className="h-3 w-2.5"><polygon points={hexPoints(0, 0, 5.4)} strokeWidth={1} className={CELL[s]} /></svg>
          {word}
        </span>
      ))}
    </div>
  )
}

function details(view: SearchView): [string, string][] {
  const rows: [string, string][] = []
  if (view.seeds.seeds !== null) rows.push(['种子', `${view.seeds.seeds} 篇，检索词 ${view.seeds.queries ?? 0} 条`])
  if (view.gather.found !== null) {
    const each = view.gather.sources.map((s) => `${s.name} ${s.failed ? '失败' : `${s.hits ?? 0} 条`}`).join('、')
    rows.push(['汇集', `检索命中 ${view.gather.found} 篇（${each}）`])
  }
  for (const r of view.rounds) {
    const took = r.hop === 0 ? `候选 ${r.screened ?? r.admitted ?? 0} 篇` : `扩出 ${r.admitted ?? 0} 篇`
    rows.push([`第 ${r.hop + 1} 轮`, r.included === null ? `${took}，筛选中` : `${took}，收录 ${r.included} 篇`])
  }
  if (view.fulltext.n !== null) rows.push(['原文', `${view.fulltext.n} 篇里拿到 ${view.fulltext.ok} 篇`])
  return rows
}
