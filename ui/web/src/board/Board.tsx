// 主页面的看板（纲领 P-19，外层 #104 #107）：按 requirement.lock 在不在分两个状态。
// 未确认——需求文档就是页面；已确认——需求收成顶部一条，下面一条流程一张表（横向阶段、纵向每次产出）。
// 工作区那一整份与能力表由父组件拉（两个镜头共用、有作业在跑时轮询、对话每一轮结束重读），这里只读。
import type { Capability, FlowPick, SkillEntry, WorkspaceDetail } from '@/api/types'
import { ErrorNote, Skeleton } from '@/components/bits'
import type { Resource } from '@/lib/useResource'

import { OutputSheet } from './OutputSheet'
import { RequirementPage, RequirementStrip } from './Requirement'
import { needsSign } from './derive'
import { type ColumnCaps, Flows } from './Flows'

/** `opened` 是侧滑里打开的那次产出，状态在父组件（文件镜头「在看板打开」要能指定它） */
export function Board({ workspace, doc, caps, skills, opened, onOpen, onOpenFiles }: {
  workspace: string; doc: Resource<WorkspaceDetail>; caps: Resource<Capability[]>; skills: Resource<SkillEntry[]>
  opened: string | null; onOpen: (oid: string | null) => void; onOpenFiles: (path: string) => void
}) {
  const error = doc.error ?? caps.error ?? skills.error
  if (error) return <div className="p-6"><ErrorNote text={error} /></div>
  if (!doc.data || !caps.data || !skills.data) return <div className="p-6"><Skeleton lines={6} /></div>
  const data = doc.data
  const catalog = caps.data
  const library = skills.data
  // 每一列底下两行：步骤（点名的，或这个阶段能用的）与 skill（挂在这一格上的）——名直接显示、一行 hover（P-21）
  const chip = (c: Capability) => ({ title: c.title, brief: c.brief })
  const capsOf = (stage: string, picks: FlowPick[]): ColumnCaps => {
    const steps = picks.filter((p) => p.kind !== 'skill').map((p) => p.cap)
    const hung = picks.filter((p) => p.kind === 'skill').map((p) => p.cap)
    return {
      caps: steps.length
        ? steps.map((name) => { const c = catalog.find((x) => x.name === name); return c ? chip(c) : { title: name, brief: '' } })
        : catalog.filter((c) => c.stage === stage).map(chip),
      named: steps.length > 0,
      skills: hung.map((name) => ({ title: name, brief: library.find((s) => s.name === name)?.brief ?? '' })),
    }
  }
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
      <div className="mx-auto w-full max-w-[80rem] space-y-5 px-5 pt-5 pb-12 sm:px-6">
        <RequirementStrip workspace={workspace} requirement={data.requirement} reload={doc.reload} />
        <Flows doc={data} capsOf={capsOf} onOpen={onOpen} onChanged={doc.reload} />
      </div>
      <OutputSheet workspace={workspace} doc={data} catalog={catalog} oid={opened} onClose={() => onOpen(null)} onOpen={onOpen}
                   onChanged={doc.reload}
                   signHint={opened && waiting.has(opened) ? '流程在此处待你确认，确认后下一步方可读取' : null}
                   onOpenFiles={(path) => { onOpen(null); onOpenFiles(path) }} />
    </div>
  )
}
