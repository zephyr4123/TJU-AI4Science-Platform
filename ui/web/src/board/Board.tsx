// 主页面的看板（纲领 P-19，外层 #104 #107）：按 requirement.lock 在不在分两个状态。
// 未确认——需求文档就是页面；已确认——需求收成顶部一条，下面一条流一张表（横向阶段、纵向每次产出）。
// 工作区那一整份由父组件拉（两个镜头共用、有作业在跑时轮询、对话每一轮结束重读），这里只读。
import { api } from '@/api/client'
import type { WorkspaceDetail } from '@/api/types'
import { ErrorNote, Skeleton } from '@/components/bits'
import { type Resource, useResource } from '@/lib/useResource'

import { OutputSheet } from './OutputSheet'
import { RequirementPage, RequirementStrip } from './Requirement'
import { needsSign } from './derive'
import { Flows } from './Flows'

/** `opened` 是侧滑里打开的那次产出，状态在父组件（文件镜头「在看板打开」要能指定它） */
export function Board({ workspace, doc, opened, onOpen, onOpenFiles }: {
  workspace: string; doc: Resource<WorkspaceDetail>; opened: string | null
  onOpen: (oid: string | null) => void; onOpenFiles: (path: string) => void
}) {
  // 能力清单只为一件事：每一列底下写这一步的能力（点名的，或这个阶段能用的）的人话标题
  const caps = useResource(api.capabilities, [])

  const error = doc.error ?? caps.error
  if (error) return <div className="p-6"><ErrorNote text={error} /></div>
  if (!doc.data || !caps.data) return <div className="p-6"><Skeleton lines={6} /></div>
  const data = doc.data
  const catalog = caps.data
  const capsOf = (stage: string, named: string[]) => (named.length
    ? { titles: named.map((name) => catalog.find((c) => c.name === name)?.title ?? name), named: true }
    : { titles: catalog.filter((c) => c.stage === stage).map((c) => c.title), named: false })
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
        <Flows doc={data} capsOf={capsOf} onOpen={onOpen} />
      </div>
      <OutputSheet workspace={workspace} oid={opened} onClose={() => onOpen(null)} onChanged={doc.reload}
                   signHint={opened && waiting.has(opened) ? '流在此处待你确认，确认后下一步方可读取' : null}
                   onOpenFiles={(path) => { onOpen(null); onOpenFiles(path) }} />
    </div>
  )
}
