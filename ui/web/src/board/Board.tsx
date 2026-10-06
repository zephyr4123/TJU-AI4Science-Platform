// 工作区页的看板（纲领 P-19，外层 #104 #107 #255）：按 requirement.lock 在不在分两个状态。
// 未确认——需求文档就是页面；已确认——题头是工作区标题加一行需求（第几版、何时确认），下面一条流程一块面（竖向时间线）。
// 工作区那一整份与能力表由父组件拉（两个镜头共用、有作业在跑时轮询、对话每一轮结束重读），这里只读。
import type { WorkspaceClient } from '@/api/client'
import type { Capability, FlowPick, SkillEntry, WorkspaceDetail } from '@/api/types'
import { ErrorNote, Skeleton } from '@/components/bits'
import type { Resource } from '@/lib/useResource'

import { OutputDialog } from './OutputDialog'
import { RequirementLine, RequirementPage } from './Requirement'
import { needsSign } from './derive'
import { Flows, type StagePlan } from './Flows'

/** `opened` 是悬浮窗里打开的那次产出，状态在父组件（文件镜头「在看板打开」要能指定它）；`siblings` 是同一项目的工作区，
 *  读了兄弟工作区的产出时用它的名字说「「X」的分析阶段第 1 次」 */
export function Board({ workspace, doc, caps, skills, siblings, opened, onOpen, onOpenFiles }: {
  workspace: WorkspaceClient; doc: Resource<WorkspaceDetail>; caps: Resource<Capability[]>; skills: Resource<SkillEntry[]>
  siblings: { id: string; title: string }[]
  opened: string | null; onOpen: (oid: string | null) => void; onOpenFiles: (path: string) => void
}) {
  const error = doc.error ?? caps.error ?? skills.error
  if (error) return <div className="p-6"><ErrorNote text={error} /></div>
  if (!doc.data || !caps.data || !skills.data) return <div className="p-6"><Skeleton lines={6} /></div>
  const data = doc.data
  const catalog = caps.data
  const library = skills.data
  const names = {
    stage: (slug: string) => data.stages.find((s) => s.slug === slug)?.name ?? slug,
    workspace: (id: string) => siblings.find((w) => w.id === id)?.title,
    cap: (name: string) => catalog.find((c) => c.name === name)?.title,
  }
  // 一个阶段计划了什么：流程在这一格点名的步骤与挂的 skill，名直接显示、一行 hover（P-21）
  const planOf = (picks: FlowPick[]): StagePlan => ({
    steps: picks.filter((p) => p.kind !== 'skill').map((p) => {
      const c = catalog.find((x) => x.name === p.cap)
      return { title: c?.title ?? p.cap, brief: c?.brief ?? '' }
    }),
    skills: picks.filter((p) => p.kind === 'skill').map((p) => {
      const s = library.find((x) => x.name === p.cap)
      return { title: s?.title ?? p.cap, brief: s?.brief ?? '' }
    }),
  })
  const waiting = needsSign(data.flows)

  if (!data.requirement.confirmed) {
    return (
      <div className="h-full overflow-y-auto">
        <RequirementPage workspace={workspace} requirement={data.requirement} reload={doc.reload} />
      </div>
    )
  }
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-[60rem] px-5 pt-8 pb-14 sm:px-8">
        <header className="px-1">
          <h1 className="font-serif text-[1.625rem] leading-[1.3] font-semibold tracking-tight text-balance">{data.requirement.title}</h1>
          <div className="mt-2"><RequirementLine workspace={workspace} requirement={data.requirement} reload={doc.reload} /></div>
        </header>
        <div className="mt-7">
          <Flows workspace={workspace} doc={data} planOf={planOf} names={names} onOpen={onOpen} onChanged={doc.reload} />
        </div>
      </div>
      <OutputDialog workspace={workspace} doc={data} catalog={catalog} oid={opened} onClose={() => onOpen(null)} onOpen={onOpen}
                   onChanged={doc.reload}
                   pending={opened !== null && waiting.has(opened)}
                   onOpenFiles={(path) => { onOpen(null); onOpenFiles(path) }} />
    </div>
  )
}
