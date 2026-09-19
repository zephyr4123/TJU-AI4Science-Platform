// 主页面的看板（纲领 P-19，外层 #104 #107）：按 requirement.lock 在不在分两个状态。
// 未确认——需求文档就是页面；已确认——需求收成顶部一条，下面七个阶段的产出与每条流的进度。
// 只读一个工作区；有作业在跑时轮询；对话每一轮结束（epoch）重读，助理改了文件立刻看得见。
import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import { ErrorNote, Skeleton } from '@/components/bits'
import { useResource } from '@/lib/useResource'

import { OutputSheet } from './OutputSheet'
import { RequirementPage, RequirementStrip } from './Requirement'
import { needsSign } from './derive'
import { Stages } from './Stages'

/** 有作业在跑时多久重拉一次：别的对话起的作业跑完，这边才看得见 */
const POLL_MS = 10_000

export function Board({ workspace, epoch }: { workspace: string; epoch: number }) {
  const doc = useResource(() => api.workspace(workspace), [workspace, epoch])
  // 能力清单只为一件事：点名的能力显示人话标题
  const caps = useResource(api.capabilities, [])
  const [opened, setOpened] = useState<string | null>(null)

  const busy = (doc.data?.running ?? 0) > 0
  const reload = doc.reload
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => { void reload() }, POLL_MS)
    return () => clearInterval(timer)
  }, [busy, reload])

  const error = doc.error ?? caps.error
  if (error) return <div className="p-6"><ErrorNote text={error} /></div>
  if (!doc.data || !caps.data) return <div className="p-6"><Skeleton lines={6} /></div>
  const data = doc.data
  const titleOf = (name: string) => caps.data!.find((c) => c.name === name)?.title
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
        <Stages doc={data} titleOf={titleOf} onOpen={setOpened} />
      </div>
      <OutputSheet workspace={workspace} oid={opened} onClose={() => setOpened(null)} onChanged={doc.reload}
                   signHint={opened && waiting.has(opened) ? '流在这儿等你签，签了下一步才能读它' : null} />
    </div>
  )
}
