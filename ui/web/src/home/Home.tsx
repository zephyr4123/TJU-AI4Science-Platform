// 首页 = 项目清单（主人 2026-09-22：侧边栏列项目很鸡肋，直接在门口把项目都摆出来，点一个进去）。外层 #249（主人 2026-10-05）：
// 三列格子名字高低不齐，改成一行一个；封面图与项目无关，看着难受，不放图，只靠字与材质。整张清单是一块玻璃（与产出悬浮窗
// 同一种），底下垫两团静态的极光、边上一圈渐变细线；一行：宋体名字与目标一句、右边三列事实（运行中几个、几个工作区、
// 创建于哪天，列宽固定上下对齐）；鼠标在哪行，那行跟着一团淡靛光、右端滑出箭头。标题那一行有搜索框（项目多了也好找）：
// 按名字与目标筛，搜中的字标出来。一个项目都没有：一句「还没有项目」加一枚「新建项目」。
import { ArrowRight, MagnifyingGlass, Plus, X } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { type MouseEvent, type ReactNode, useState } from 'react'

import type { ProjectSummary } from '@/api/types'
import { ASSETS } from '@/assets'
import { Dot, ErrorNote, Skeleton } from '@/components/bits'
import { GLASS } from '@/components/glass'
import SpecularButton from '@/components/reactbits/SpecularButton'
import { Scene } from '@/components/Scene'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { day } from '@/lib/format'
import { useToken } from '@/lib/tokens'
import type { Resource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { findProjects, marks, newestFirst, wordsOf } from './derive'

export function Home({ projects, onOpen, onNew, menu }: {
  projects: Resource<ProjectSummary[]>; onOpen: (id: string) => void; onNew: () => void; menu?: ReactNode
}) {
  const [query, setQuery] = useState('')
  const list = projects.data ? newestFirst(projects.data) : null
  const shown = list ? findProjects(list, query) : null
  const words = wordsOf(query)
  return (
    <div className="relative flex-1 overflow-y-auto">
      <Scene picture={ASSETS.welcome} veil="mist" />
      <div className="relative mx-auto w-full max-w-[54rem] px-6 pt-8 pb-16 sm:px-8">
        <header className="flex flex-wrap items-center gap-3">
          {menu}
          <div className="flex items-baseline gap-2.5">
            <h1 className="font-serif text-[1.75rem] leading-none font-semibold tracking-tight">项目</h1>
            {list && list.length > 0 && <span className="text-[0.9375rem] text-muted-foreground tabular">{list.length}</span>}
          </div>
          {list && list.length > 0 && (
            <>
              <Search value={query} onChange={setQuery} className="order-last basis-full sm:order-none sm:ml-auto sm:basis-64" />
              <Button onClick={onNew} className="ml-auto rounded-full sm:ml-0"><Plus weight="bold" data-icon="inline-start" />新建项目</Button>
            </>
          )}
        </header>
        {projects.error && <ErrorNote text={projects.error} className="mt-6" />}
        {!list && !projects.error && <div className="mt-8"><Skeleton lines={5} /></div>}
        {list && list.length === 0 && <NoProjects onNew={onNew} />}
        {shown && shown.length > 0 && (
          <Aurora className="mt-6">
            <ul>
              {shown.map((p) => (
                <li key={p.id} className="relative not-first:before:absolute not-first:before:inset-x-6 not-first:before:top-0 not-first:before:h-px not-first:before:bg-foreground/[0.07]">
                  <ProjectRow project={p} words={words} onOpen={() => onOpen(p.id)} />
                </li>
              ))}
            </ul>
          </Aurora>
        )}
        {list && list.length > 0 && shown?.length === 0 && (
          <p className="t-label mt-8">名字和目标里都没有「{query.trim()}」</p>
        )}
      </div>
    </div>
  )
}

/** 清单那块玻璃：底下垫两团极光（靛在左上、青在右下），边上一圈从靛渐到青的细线；全是静态的，不起动画 */
function Aurora({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('relative isolate overflow-hidden rounded-[22px] shadow-[inset_0_1px_0_0_var(--glass-shine),0_1px_2px_rgb(0_0_0/0.04),0_18px_48px_-24px_rgb(0_0_0/0.22)]', GLASS, className)}>
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10"
           style={{ background: 'radial-gradient(65% 95% at 0% 0%, color-mix(in oklab, var(--aurora-1) 26%, transparent), transparent 70%), '
                              + 'radial-gradient(60% 90% at 100% 100%, color-mix(in oklab, var(--aurora-2) 24%, transparent), transparent 70%)' }} />
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-[22px] p-px"
           style={{
             background: 'linear-gradient(135deg, color-mix(in oklab, var(--aurora-1) 85%, transparent), transparent 42%, transparent 58%, color-mix(in oklab, var(--aurora-2) 80%, transparent))',
             WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor',
             mask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', maskComposite: 'exclude',
           }} />
      {children}
    </div>
  )
}

/** 搜索框：输入即筛；有字时右端一枚清空，Esc 也清 */
function Search({ value, onChange, className }: { value: string; onChange: (v: string) => void; className?: string }) {
  return (
    <div className={cn('relative', className)}>
      <MagnifyingGlass aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 z-10 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input type="search" value={value} placeholder="搜索项目" aria-label="搜索项目"
             onChange={(e) => onChange(e.target.value)} onKeyDown={(e) => { if (e.key === 'Escape') onChange('') }}
             className="h-8 rounded-full bg-card/70 pr-8 pl-9 backdrop-blur-sm [&::-webkit-search-cancel-button]:appearance-none" />
      {value && (
        <Button variant="ghost" size="icon-xs" aria-label="清空搜索" onClick={() => onChange('')}
                className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded-full"><X /></Button>
      )}
    </div>
  )
}

/** 鼠标在行里的位置写进 CSS 变量，那团光跟着走；只在鼠标动时写，不起帧循环 */
function follow(e: MouseEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--spot-x', `${e.clientX - r.left}px`)
  e.currentTarget.style.setProperty('--spot-y', `${e.clientY - r.top}px`)
}

/** 一行：宋体名字（最多两行）与目标一句、右边三列事实；鼠标进来事实往左让，右端滑出箭头。窄屏事实挪到目标底下一行 */
function ProjectRow({ project, words, onOpen }: { project: ProjectSummary; words: string[]; onOpen: () => void }) {
  const running = project.running > 0 && (
    <span className="flex items-center justify-end gap-1.5 text-primary"><Dot tone="primary" pulse />运行中 {project.running}</span>
  )
  return (
    <button type="button" onClick={onOpen} onMouseMove={follow}
            className="group relative isolate flex min-h-[4.75rem] w-full items-center gap-6 px-6 py-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:ring-inset">
      <span aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 opacity-0 transition-opacity duration-200 ease-out group-hover:opacity-100 group-focus-visible:opacity-100"
            style={{ background: 'radial-gradient(26rem circle at var(--spot-x, 50%) var(--spot-y, 50%), color-mix(in oklab, var(--primary) 9%, transparent), transparent 72%)' }} />
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 font-serif text-[1.125rem] leading-[1.35] font-semibold text-balance"><Marked text={project.title} words={words} /></span>
        {project.goal && <span className="t-label mt-1 block truncate"><Marked text={project.goal} words={words} /></span>}
        <span className="t-label mt-1 flex flex-wrap gap-x-4 tabular sm:hidden">
          {running}<span>{project.workspaces} 个工作区</span><span>创建于 {day(project.created_at)}</span>
        </span>
      </span>
      <span className="hidden shrink-0 grid-cols-[5.5rem_5.5rem_7rem] items-center text-right text-[0.8125rem] text-muted-foreground tabular transition-[translate] duration-200 ease-out group-hover:-translate-x-7 group-focus-visible:-translate-x-7 sm:grid">
        <span>{running}</span>
        <span>{project.workspaces} 个工作区</span>
        <span>创建于 {day(project.created_at)}</span>
      </span>
      <ArrowRight aria-hidden="true"
                  className="absolute top-1/2 right-6 size-4 -translate-x-1.5 -translate-y-1/2 text-primary opacity-0 transition-[opacity,translate] duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:translate-x-0 group-focus-visible:opacity-100" />
    </button>
  )
}

/** 搜中的字底下垫一层淡靛 */
function Marked({ text, words }: { text: string; words: string[] }) {
  return marks(text, words).map((m, i) => m.hit
    ? <mark key={i} className="rounded-[3px] bg-primary/15 text-inherit">{m.text}</mark>
    : <span key={i}>{m.text}</span>)
}

/** 一个项目都没有：一句话与一枚玻璃键（与「打开对话」同一种键） */
function NoProjects({ onNew }: { onNew: () => void }) {
  const still = useReducedMotion() === true
  const indigo = useToken('--primary')
  const card = useToken('--card')
  const ink = useToken('--foreground')
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-8 text-center">
      <h2 className="font-serif text-[1.75rem] leading-[1.25] font-semibold tracking-tight">还没有项目</h2>
      <SpecularButton size="lg" radius={18} tint={card} tintOpacity={0.78} blur={12} textColor={ink} lineColor={indigo} baseColor={ink}
                      intensity={1.1} speed={still ? 0 : 0.35} followMouse={!still} autoAnimate={false} onClick={onNew}
                      className="shadow-lg ring-1 ring-foreground/10">
        <span className="inline-flex items-center gap-2"><Plus weight="bold" className="size-5 text-primary" />新建项目</span>
      </SpecularButton>
    </div>
  )
}
