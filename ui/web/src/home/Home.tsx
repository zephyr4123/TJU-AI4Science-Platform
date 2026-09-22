// 首页 = 项目墙（主人 2026-09-22：侧边栏列项目很鸡肋，直接在门口把项目都摆出来，点一个进去）。一格一个项目，字在前——名字、
// 目标一句、几个工作区、什么时候建的、有没有东西在跑；封面压暗当底（主人：图可以作背景，信息必须陈列出来）。
// 一个项目都没有：一句「还没有项目」加一枚「新建项目」。格子是 reactbits MagicBento 改装（components/reactbits/MagicBento）。
import { Plus } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'

import type { ProjectSummary } from '@/api/types'
import { ASSETS, coverOf } from '@/assets'
import { Dot, ErrorNote, Skeleton } from '@/components/bits'
import { BentoCard, BentoGrid } from '@/components/reactbits/MagicBento'
import SpecularButton from '@/components/reactbits/SpecularButton'
import { Scene } from '@/components/Scene'
import { Button } from '@/components/ui/button'
import { day } from '@/lib/format'
import { useToken } from '@/lib/tokens'
import type { Resource } from '@/lib/useResource'

export function Home({ projects, onOpen, onNew, menu }: {
  projects: Resource<ProjectSummary[]>; onOpen: (id: string) => void; onNew: () => void; menu?: ReactNode
}) {
  const list = projects.data ? newestFirst(projects.data) : null
  return (
    <div className="relative flex-1 overflow-y-auto">
      <Scene picture={ASSETS.welcome} veil="mist" />
      <div className="relative mx-auto w-full max-w-[72rem] px-6 pt-8 pb-16 sm:px-8">
        <header className="flex items-center gap-3">
          {menu}
          <h1 className="font-serif text-[1.75rem] leading-none font-semibold tracking-tight">项目</h1>
          {list && list.length > 0 && <span className="t-label tabular">{list.length}</span>}
          {list && list.length > 0 && (
            <Button onClick={onNew} className="ml-auto rounded-full"><Plus weight="bold" data-icon="inline-start" />新建项目</Button>
          )}
        </header>
        {projects.error && <ErrorNote text={projects.error} className="mt-6" />}
        {!list && !projects.error && <div className="mt-8"><Skeleton lines={5} /></div>}
        {list && list.length === 0 && <NoProjects onNew={onNew} />}
        {list && list.length > 0 && (
          <BentoGrid className="mt-8 sm:grid-cols-2 xl:grid-cols-3">
            {list.map((p) => <ProjectTile key={p.id} project={p} onOpen={() => onOpen(p.id)} />)}
          </BentoGrid>
        )}
      </div>
    </div>
  )
}

/** 后端按目录名给；墙上新的在前 */
function newestFirst(projects: ProjectSummary[]): ProjectSummary[] {
  return [...projects].sort((a, b) => b.created_at.localeCompare(a.created_at))
}

/** 一格：封面压暗铺底，名字宋体在上，目标一句在中，底下一行事实——几个工作区、建于哪天、几个在跑 */
function ProjectTile({ project, onOpen }: { project: ProjectSummary; onOpen: () => void }) {
  const cover = coverOf(project.id)
  return (
    <BentoCard onClick={onOpen} label={project.title} className="min-h-[11.5rem]"
               backdrop={(
                 <>
                   <img src={cover.src} alt="" decoding="async" className="size-full object-cover opacity-60 transition-opacity duration-300 group-hover:opacity-80" />
                   <div className="absolute inset-0 veil-foot" />
                 </>
               )}>
      <div className="flex h-full min-h-[11.5rem] flex-col justify-end p-5">
        <h2 className="line-clamp-2 font-serif text-[1.25rem] leading-[1.3] font-semibold text-balance">{project.title}</h2>
        {project.goal && <p className="t-label mt-1.5 line-clamp-1">{project.goal}</p>}
        <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.8125rem] text-muted-foreground">
          <span className="tabular">{project.workspaces} 个工作区</span>
          <span>创建于 {day(project.created_at)}</span>
          {project.running > 0 && (
            <span className="flex items-center gap-1.5 text-primary"><Dot tone="primary" pulse />运行中 {project.running}</span>
          )}
        </p>
      </div>
    </BentoCard>
  )
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
