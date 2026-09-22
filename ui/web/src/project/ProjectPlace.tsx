// 项目的世界（外层 #136）：一个项目一位助理，对话是项目的，这里拿着它——项目页、整屏的对话、项目里的工作区页三个样子共用同一段
// 对话与同一份项目清单，来回切换不断线。项目页正中间输入框打的第一句开一段新对话，页面切成整屏的对话；从「对话 · N」挑一段也是；
// 「‹ 项目名」回项目页。进了工作区，对话在右边那块板上。
import { useEffect, useMemo, useState } from 'react'

import { api, inProject, WorkspaceClient } from '@/api/client'
import type { Backend } from '@/api/types'
import { coverOf } from '@/assets'
import { ChatDrawer } from '@/chat/ChatDrawer'
import { ChatView } from '@/chat/ChatView'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Top } from '@/components/Top'
import { usd } from '@/lib/format'
import { useChats } from '@/lib/useChats'
import { useResource } from '@/lib/useResource'
import { WorkspacePage } from '@/workspace/WorkspacePage'

import { Hub } from './Hub'

/** 有作业在跑时多久重拉一次项目清单 */
const POLL_MS = 10_000

export function ProjectPlace({ projectId, wsId, healthy, backends, menu, onOpenWorkspace, onBack, onRemoved, onWorkspaceRemoved }: {
  projectId: string
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
  const doc = useResource(() => api.project(projectId), [projectId, c.epoch])
  // 能力表与 skill 清单整个项目拉一次：看板每一列底下的能力、产出记录里能力的名与参数的 label 都从它查（P-21）
  const caps = useResource(api.capabilities, [])
  const skills = useResource(api.skills, [])
  const ws = useMemo(() => (wsId ? new WorkspaceClient(projectId, wsId) : null), [projectId, wsId])
  // 项目页是两个样子：正中间输入框的那页，和整屏的对话；进过工作区再回来落在前者
  const [talking, setTalking] = useState(false)
  const openWorkspace = (id: string) => { setTalking(false); onOpenWorkspace(id) }

  const busy = (doc.data?.running ?? 0) > 0
  const reload = doc.reload
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => { void reload() }, POLL_MS)
    return () => clearInterval(timer)
  }, [busy, reload])

  const title = doc.data?.title ?? projectId
  const drawer = (
    <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                creating={c.creating} onSelect={(id) => { c.pick(id); setTalking(true) }}
                onNew={() => { void c.newChat(); setTalking(true) }}
                onRemove={async (id) => { await c.remove(id) }}
                cover={coverOf(projectId)} title={title} />
  )
  const chat = (opts: { onClose?: () => void; header: boolean }) => (
    <ChatView
      key={c.chatId ?? 'none'} scope={scope} chatId={c.chatId} current={c.current}
      onClose={opts.onClose} header={opts.header}
      autoSend={c.opening} onAutoSent={c.opened} onStart={(text, tuning, backend) => void c.start(text, tuning, backend)}
      onTurnDone={c.turnDone}
      backends={backends}
      intro={{ lede: '课题', body: '问题、材料、评价标准。' }}
      welcome={{ headline: '课题', body: '问题、材料、评价标准。' }}
      drawer={drawer}
    />
  )

  if (ws) {
    return (
      <WorkspacePage key={ws.key} ws={ws} project={doc.data} epoch={c.epoch} caps={caps} skills={skills}
                     chat={(close) => chat({ onClose: close, header: true })} menu={menu}
                     onBack={onBack} onSwitch={openWorkspace} onRemoved={onWorkspaceRemoved} />
    )
  }
  if (doc.error) return <div className="p-6"><ErrorNote text={doc.error} /></div>
  if (!doc.data) return <div className="p-6"><Skeleton lines={5} /></div>
  if (talking) {
    return (
      <>
        <Top menu={menu} back={{ label: title, onClick: () => setTalking(false) }} picture={coverOf(projectId)}
             title={c.current?.title ?? '新对话'}
             tail={<span className="ml-auto flex items-center gap-3">
               {c.current && c.current.cost_usd > 0 && <span className="t-label whitespace-nowrap">{usd(c.current.cost_usd)}</span>}
               {drawer}
             </span>} />
        <div className="relative flex min-h-0 flex-1">
          {c.chatId ? chat({ header: false }) : <div className="p-6"><Skeleton lines={3} /></div>}
        </div>
      </>
    )
  }
  return (
    <Hub project={doc.data} backends={backends} busy={c.creating} menu={menu} drawer={drawer}
         onStart={(text, tuning, backend) => { setTalking(true); void c.start(text, tuning, backend) }}
         onOpenWorkspace={openWorkspace}
         onCreatedWorkspace={async (id) => { await reload(); openWorkspace(id) }}
         onRemove={async () => { const removed = await api.removeProject(projectId); await onRemoved(removed.leftovers) }} />
  )
}
