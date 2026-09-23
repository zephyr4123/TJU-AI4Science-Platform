// 项目的世界（外层 #136）：一个项目一位助理，对话是项目的，这里拿着它——项目页（正中间输入框、整屏的对话）与项目里的工作区页
// 共用同一份对话清单与同一份项目清单，来回切换不断线。进了工作区，对话在右边那块板上，接着最近的一段。
import { useEffect, useMemo } from 'react'

import { api, inProject, WorkspaceClient } from '@/api/client'
import type { Backend, ProjectSummary } from '@/api/types'
import { coverOf } from '@/assets'
import { ChatDrawer } from '@/chat/ChatDrawer'
import { ChatView } from '@/chat/ChatView'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Scene } from '@/components/Scene'
import { useChats } from '@/lib/useChats'
import { useResource } from '@/lib/useResource'
import { WorkspacePage } from '@/workspace/WorkspacePage'

import { ProjectPage } from './ProjectPage'

/** 有作业在跑时多久重拉一次项目清单 */
const POLL_MS = 10_000

export function ProjectPlace({ projectId, summary, wsId, healthy, backends, menu, onOpenWorkspace, onBack, onRemoved, onWorkspaceRemoved }: {
  projectId: string
  /** 首页清单里的那一行：那一整份还没回来时标题与目标先照它写 */
  summary: ProjectSummary | null
  /** 在项目里的哪个工作区；null 是项目页本身 */
  wsId: string | null
  healthy: boolean | null
  backends: Backend[] | null
  menu?: React.ReactNode
  onOpenWorkspace: (id: string) => void
  /** 从工作区回项目页 */
  onBack: () => void
  onRemoved: (leftovers: string[]) => Promise<void>
  onWorkspaceRemoved: (leftovers: string[]) => Promise<void>
}) {
  const scope = useMemo(() => inProject(projectId), [projectId])
  const c = useChats(scope)
  const doc = useResource(() => api.project(projectId), [projectId, c.epoch], `project:${projectId}`)
  // 能力表与 skill 清单整个项目拉一次：看板每一列底下的能力、产出记录里能力的名与参数的 label 都从它查（P-21）
  const caps = useResource(api.capabilities, [], 'caps')
  const skills = useResource(api.skills, [], 'skills')
  const ws = useMemo(() => (wsId ? new WorkspaceClient(projectId, wsId) : null), [projectId, wsId])

  const busy = (doc.data?.running ?? 0) > 0
  const reload = doc.reload
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => { void reload() }, POLL_MS)
    return () => clearInterval(timer)
  }, [busy, reload])

  if (ws) {
    const title = doc.data?.title ?? projectId
    return (
      <WorkspacePage key={ws.key} ws={ws} project={doc.data} epoch={c.epoch} caps={caps} skills={skills} menu={menu}
                     onBack={onBack} onSwitch={onOpenWorkspace} onRemoved={onWorkspaceRemoved}
                     chat={(close) => (
                       <ChatView scope={scope} chatId={c.chatId} current={c.current} create={c.newChat} backends={backends}
                                 onTurnDone={c.turnDone} onClose={close}
                                 welcome={{ headline: '课题', body: '问题、材料、评价标准。' }}
                                 drawer={
                                   <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                                               creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                                               onRemove={async (id) => { await c.remove(id) }}
                                               cover={coverOf(projectId)} title={title} />
                                 } />
                     )} />
    )
  }
  if (!doc.data) {
    // 第一次进这个项目、那一整份还没回来：底图、标题、目标先照首页清单里那一行摆好（和项目页同一个位置），
    // 输入框的地方放骨架——回来时只有输入框与工作区清单冒出来，别的都不动
    return (
      <div className="relative flex min-h-0 flex-1 flex-col">
        <Scene picture={coverOf(projectId)} veil="mist" />
        {menu && <div className="absolute top-3 left-4 z-10">{menu}</div>}
        <div className="relative mx-auto w-full max-w-[47rem] px-6 pt-[12vh]">
          <h1 className="text-center font-serif text-[2rem] leading-[1.25] font-semibold tracking-tight text-balance">{summary?.title ?? projectId}</h1>
          {summary?.goal && <p className="t-body mx-auto mt-3 text-center text-muted-foreground">{summary.goal}</p>}
          <div className="mt-8">{doc.error ? <ErrorNote text={doc.error} /> : <Skeleton lines={3} />}</div>
        </div>
      </div>
    )
  }
  return (
    <ProjectPage project={doc.data} chats={c} backends={backends} healthy={healthy} menu={menu}
                 onOpenWorkspace={onOpenWorkspace}
                 onCreatedWorkspace={async (id) => { await reload(); onOpenWorkspace(id) }}
                 onRemove={async () => { const removed = await api.removeProject(projectId); await onRemoved(removed.leftovers) }} />
  )
}
