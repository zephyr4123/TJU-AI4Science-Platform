// 壳：顶栏（名字、工作区切换、主页面 / 编辑台胶囊）+ 两块看板（外层 #58 #64 #70）。
// 页面先认工作区（一个工作区一份需求，P-15）：主页面是这个工作区的对话 + 流程脊柱；
// 编辑台改「库」：造流助理的对话 + 工作流墙、七段货架、拼流台。两位助理分权（P-16），页面只是 `ai4sci serve` 的客户端。
import { useState } from 'react'

import { api, inWorkspace, STUDIO } from '@/api/client'
import { ChatView } from '@/chat/ChatView'
import { PillNav } from '@/components/reactbits/PillNav'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useChats } from '@/lib/useChats'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { ChatDrawer } from '@/sidebar/ChatDrawer'
import { Spine } from '@/spine/Spine'
import { Studio } from '@/studio/Studio'
import { NewWorkspace } from '@/workspace/NewWorkspace'
import { WorkspaceSwitcher } from '@/workspace/WorkspaceSwitcher'

type View = 'main' | 'studio'

const VIEWS: { id: View; label: string }[] = [
  { id: 'main', label: '主页面' },
  { id: 'studio', label: '编辑台' },
]

export default function App() {
  const workspaces = useResource(api.workspaces, [])
  const health = useResource(api.health, [])
  const [picked, setPicked] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [view, setView] = useState<View>('main')

  const newest = workspaces.data?.length
    ? [...workspaces.data].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))[0].id : null
  const wsId = picked && workspaces.data?.some((w) => w.id === picked) ? picked : newest
  const healthy = health.loading && !health.data ? null : health.data?.ok === true

  const created = async (id: string) => {
    await workspaces.reload()
    setPicked(id)
    setCreating(false)
    setView('main')
  }

  return (
    <TooltipProvider>
      <div className="flex h-dvh flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-card px-4 sm:gap-5 sm:px-5">
          <span className="hidden font-serif text-[1.0625rem] font-semibold tracking-[0.02em] sm:inline">AI4Science</span>
          <WorkspaceSwitcher workspaces={workspaces.data} selected={wsId}
                             onPick={(id) => { setPicked(id); setCreating(false); setView('main') }}
                             onNew={() => { setCreating(true); setView('main') }} />
          <span className="flex-1" />
          <PillNav items={VIEWS} active={view} onSelect={setView} />
        </header>

        {view === 'studio'
          ? <StudioView healthy={healthy} />
          : creating || (workspaces.data && !wsId)
            ? <NewWorkspace existing={workspaces.data ?? []} onCreated={(id) => void created(id)}
                            onCancel={wsId ? () => setCreating(false) : undefined}
                            onPick={(id) => { setPicked(id); setCreating(false) }} />
            : wsId
              ? <MainView key={wsId} wsId={wsId} healthy={healthy} />
              : <div className="flex-1" />}
      </div>
    </TooltipProvider>
  )
}

/** 主页面：这个工作区的对话 + 脊柱。换工作区时父组件用 key 重建，状态天然按工作区隔离。 */
function MainView({ wsId, healthy }: { wsId: string; healthy: boolean | null }) {
  const scope = inWorkspace(wsId)
  const c = useChats(scope)
  const wide = useMediaQuery(WIDE)
  // 没点过：宽屏常开、窄屏收着；窄屏上脊柱是一张从右边拉出来的抽屉
  const [boardOpen, setBoardOpen] = useState<boolean | null>(null)
  const open = boardOpen ?? wide
  const spine = <Spine workspace={wsId} epoch={c.epoch} />
  return (
    <div className="flex min-h-0 flex-1">
      <ChatView
        key={c.chatId ?? 'none'} scope={scope} chatId={c.chatId} current={c.current}
        boardOpen={open} onToggleBoard={() => setBoardOpen(!open)}
        onNew={() => void c.newChat()} onTurnDone={c.turnDone}
        intro={{ lede: '先说清课题。', body: '想解决什么、数据在哪、什么算好。' }}
        placeholder="说说你的课题"
        welcome={{
          headline: '把实验交给助理。',
          body: '你只做两件事：发布需求，验收结果。',
        }}
        drawer={
          <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                      creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                      description="这个工作区的对话" />
        }
      />
      {wide ? (
        <aside
          className={cn('paper-grid relative h-full shrink-0 border-l transition-[width] duration-200',
                        open ? 'w-[27.5rem]' : 'w-0 overflow-hidden border-l-0')}
          aria-label="这条流" aria-hidden={!open}
        >
          <div className="h-full w-[27.5rem]">{spine}</div>
        </aside>
      ) : (
        <Sheet open={open} onOpenChange={setBoardOpen}>
          <SheetContent side="right"
                        className="paper-grid gap-0 p-0 data-[side=right]:w-[100vw] data-[side=right]:sm:w-[27.5rem] data-[side=right]:sm:max-w-[27.5rem]">
            <SheetHeader className="sr-only"><SheetTitle>这条流</SheetTitle></SheetHeader>
            <div className="h-full">{spine}</div>
          </SheetContent>
        </Sheet>
      )}
    </div>
  )
}

/** 编辑台：左边造流助理的对话（窄一列，库才是主角），右边工作流墙、货架、拼流台。 */
function StudioView({ healthy }: { healthy: boolean | null }) {
  const c = useChats(STUDIO)
  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="flex h-[45dvh] shrink-0 flex-col border-b lg:h-auto lg:w-[30rem] lg:border-r lg:border-b-0">
        <ChatView
          key={c.chatId ?? 'none'} scope={STUDIO} chatId={c.chatId} current={c.current}
          onNew={() => void c.newChat()} onTurnDone={c.turnDone}
          intro={{ lede: '说清要拼什么流。', body: '给谁用、从哪步起、要不要验证。' }}
          placeholder="说说要拼的流"
          welcome={{
            headline: '把能力拼成流。',
            body: '存进库，研究者取走就能跑。',
          }}
          drawer={
            <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                        creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                        description="编辑台的对话" />
          }
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto"><Studio epoch={c.epoch} /></div>
    </div>
  )
}
