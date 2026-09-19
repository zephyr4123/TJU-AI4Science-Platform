// 壳：左边地方栏（先选世界：工作区 / 编辑台，再选工作区），右边页眉 + 当前地方的内容（外层 #58 #64 #70 #79 #104 #111）。
// 页面先认工作区（一个工作区一份需求，P-15）：主页面是这个工作区的两个镜头——看板（需求没确认就是需求文档，确认了是一条流
// 一张表）与文件（盘上的目录树与文件内容，只读），页眉上切换，对话在右边两个镜头都在。编辑台是全局一个库：画布 + 造流助理的
// 悬浮对话窗（外层 #100），和工作区是两个平行的世界：地方栏上是一个开关，进了编辑台工作区块整段收掉，页眉也不跟着工作区换
// （P-16）。页面只是 `ai4sci serve` 的客户端。
import { ChatCircle } from '@phosphor-icons/react'
import { type ReactNode, useState } from 'react'

import { api, inWorkspace, STUDIO } from '@/api/client'
import type { Backend } from '@/api/types'
import { ASSETS, coverOf } from '@/assets'
import { Board } from '@/board/Board'
import { ChatView } from '@/chat/ChatView'
import { Band } from '@/components/Band'
import { Scene } from '@/components/Scene'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Files } from '@/files/Files'
import { stageSentence } from '@/lib/humanize'
import { useChats } from '@/lib/useChats'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import type { Place, World } from '@/places/place'
import { PlacesSheet } from '@/places/PlacesSheet'
import { Rail } from '@/places/Rail'
import { ChatDrawer } from '@/sidebar/ChatDrawer'
import { Studio } from '@/studio/Studio'
import { NewWorkspace } from '@/workspace/NewWorkspace'

const PICKED_KEY = 'ai4sci.workspace'

/** 工作区页面的两个镜头：看板（做到哪了、在等谁）与文件（盘上有什么） */
type View = 'board' | 'files'

export default function App() {
  const workspaces = useResource(api.workspaces, [])
  const health = useResource(api.health, [])
  // 输入框上两枚旋钮的清单：缺省那家后端有哪些模型、哪几档思考深度（外层 #86）
  const backends = useResource(api.backends, [])
  const knobs = backends.data?.find((b) => b.default) ?? backends.data?.[0] ?? null
  // 上次看的哪个工作区记在浏览器里；没记过就是清单里第一个
  const [picked, setPickedState] = useState<string | null>(() => {
    try { return window.localStorage.getItem(PICKED_KEY) } catch { return null }
  })
  const setPicked = (id: string | null) => {
    setPickedState(id)
    try { if (id) window.localStorage.setItem(PICKED_KEY, id) } catch { /* 隐私模式存不了就每次从头挑 */ }
  }
  const [creating, setCreating] = useState(false)
  const [studio, setStudio] = useState(false)
  const [view, setView] = useState<View>('board')
  // 从看板「打开目录」跳到文件镜头时定位到哪个产出；从文件镜头「在看板打开」回来时侧滑里开哪次产出；换工作区都清掉
  const [focus, setFocus] = useState<string | null>(null)
  const [opened, setOpened] = useState<string | null>(null)
  const wide = useMediaQuery(WIDE)

  const first = workspaces.data?.length ? workspaces.data[0].id : null
  const wsId = picked && workspaces.data?.some((w) => w.id === picked) ? picked : first
  const current = wsId ? workspaces.data?.find((w) => w.id === wsId) ?? null : null
  const healthy = health.loading && !health.data ? null : health.data?.ok === true

  // 此刻在哪：编辑台 > 门口（正在新建，或一个工作区都没有）> 某个工作区；工作区清单还没回来时哪儿也不在
  const place: Place | null = studio ? { kind: 'studio' }
    : creating || (workspaces.data && !wsId) ? { kind: 'door' }
      : wsId ? { kind: 'workspace', id: wsId } : null

  const created = async (id: string) => {
    await workspaces.reload()
    setPicked(id)
    setCreating(false)
  }
  const places = {
    workspaces: workspaces.data,
    place: place ?? { kind: 'door' as const },
    onPick: (id: string) => { setPicked(id); setCreating(false); setStudio(false); setFocus(null); setOpened(null) },
    onNew: () => { setCreating(true); setStudio(false) },
    onWorld: (world: World) => setStudio(world === 'studio'),
  }

  return (
    <TooltipProvider>
      <div className="flex h-dvh overflow-hidden">
        {wide && <Rail {...places} />}
        <div className="flex min-w-0 flex-1 flex-col">
          {place && (
            <Top place={place} menu={wide ? null : <PlacesSheet {...places} />}
                 title={place.kind === 'studio' ? '编辑台' : place.kind === 'door' ? '新建工作区' : current?.title ?? place.id}
                 note={current && place.kind === 'workspace' ? stageSentence(current) : null}
                 view={place.kind === 'workspace' ? view : null} onView={setView} />
          )}
          {place?.kind === 'studio'
            ? <StudioView healthy={healthy} knobs={knobs} />
            : place?.kind === 'door'
              ? <NewWorkspace existing={workspaces.data ?? []} onCreated={(id) => void created(id)}
                              onCancel={wsId ? () => setCreating(false) : undefined} />
              : place
                ? <MainView key={place.id} wsId={place.id} healthy={healthy} knobs={knobs} title={current?.title ?? place.id}
                            view={view} focus={focus} opened={opened} onOpen={setOpened}
                            onOpenFiles={(path) => { setFocus(path); setView('files') }}
                            onOpenBoard={(oid) => { setOpened(oid); setView('board') }} />
                : <div className="flex-1" />}
        </div>
      </div>
    </TooltipProvider>
  )
}

/** 页眉只属于当前地方：工作区的标题 + 走到哪 + 两个镜头的开关，底下封面糊成一抹颜色（换工作区就换色）；编辑台一条横幅；
 *  门口宽屏不要页眉（画面铺满），窄屏留一条放入口。 */
function Top({ place, title, note, menu, view, onView }: {
  place: Place; title: string; note: string | null; menu: ReactNode; view: View | null; onView: (view: View) => void
}) {
  if (place.kind === 'door' && !menu) return null
  const picture = place.kind === 'studio' ? ASSETS.studio : place.kind === 'workspace' ? coverOf(place.id) : null
  const row = (
    <header className="flex h-14 items-center gap-3 px-4 sm:px-5">
      {menu}
      <span className="min-w-0 truncate font-serif text-[1.0625rem] font-semibold tracking-[0.02em]">{title}</span>
      {note && <span className="t-label hidden whitespace-nowrap sm:inline">{note}</span>}
      {view && (
        <Tabs value={view} onValueChange={(v) => onView(v as View)} className="ml-auto">
          <TabsList aria-label="镜头" className="bg-background/70 backdrop-blur-sm">
            <TabsTrigger value="board" className="px-3">看板</TabsTrigger>
            <TabsTrigger value="files" className="px-3">文件</TabsTrigger>
          </TabsList>
        </Tabs>
      )}
      <ThemeToggle className={cn(!view && 'ml-auto')} />
    </header>
  )
  if (!picture) return <div className="shrink-0 border-b bg-card">{row}</div>
  return <Band picture={picture} veil="wash" blur className="shrink-0 border-b">{row}</Band>
}

/** 主页面：这个工作区的看板或文件铺满，对话在右边一列（宽屏常开、可收；窄屏是从右边拉出来的抽屉）。
 *  换工作区时父组件用 key 重建，状态天然按工作区隔离。 */
function MainView({ wsId, title, healthy, knobs, view, focus, opened, onOpen, onOpenFiles, onOpenBoard }: {
  wsId: string; title: string; healthy: boolean | null; knobs: Backend | null
  view: View; focus: string | null; opened: string | null; onOpen: (oid: string | null) => void
  onOpenFiles: (path: string) => void; onOpenBoard: (oid: string) => void
}) {
  const scope = inWorkspace(wsId)
  const c = useChats(scope)
  const wide = useMediaQuery(WIDE)
  const [chatOpen, setChatOpen] = useState<boolean | null>(null)
  const open = chatOpen ?? true
  const chat = (
    <ChatView
      key={c.chatId ?? 'none'} scope={scope} chatId={c.chatId} current={c.current}
      onClose={() => setChatOpen(false)}
      autoSend={c.opening} onAutoSent={c.opened} onStart={(text, tuning) => void c.start(text, tuning)} onTurnDone={c.turnDone}
      knobs={knobs}
      intro={{ lede: '课题', body: '问题、材料、评价标准。' }}
      welcome={{ headline: '课题', body: '问题、材料、评价标准。' }}
      drawer={
        <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                    creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                    cover={coverOf(wsId)} title={title} />
      }
    />
  )
  return (
    <div className="relative flex min-h-0 flex-1">
      <main className="relative min-w-0 flex-1">
        <Scene picture={ASSETS.board} veil="mist" />
        <div className="relative h-full">
          {view === 'files'
            ? <Files key={focus ?? ''} workspace={wsId} epoch={c.epoch} focus={focus} onOpenBoard={onOpenBoard} />
            : <Board workspace={wsId} epoch={c.epoch} opened={opened} onOpen={onOpen} onOpenFiles={onOpenFiles} />}
        </div>
        {!open && (
          <Button size="icon-lg" className="absolute right-5 bottom-5 rounded-full shadow-lg" onClick={() => setChatOpen(true)} aria-label="展开对话">
            <ChatCircle weight="duotone" className="size-5" />
          </Button>
        )}
      </main>
      {wide ? (
        <aside className={cn('relative h-full shrink-0 border-l transition-[width] duration-200',
                             open ? 'w-[30rem]' : 'w-0 overflow-hidden border-l-0')}
               aria-label="对话" aria-hidden={!open}>
          <div className="relative h-full w-[30rem]">{chat}</div>
        </aside>
      ) : (
        <Sheet open={open} onOpenChange={setChatOpen}>
          <SheetContent side="right"
                        className="gap-0 p-0 data-[side=right]:w-[100vw] data-[side=right]:sm:w-[30rem] data-[side=right]:sm:max-w-[30rem]">
            <SheetHeader className="sr-only"><SheetTitle>对话</SheetTitle></SheetHeader>
            <div className="relative h-full">{chat}</div>
          </SheetContent>
        </Sheet>
      )}
    </div>
  )
}

/** 编辑台：画布铺满，造流助理的对话是右下角弹出的悬浮窗（对话的状态在这儿，窗口在画布上）。 */
function StudioView({ healthy, knobs }: { healthy: boolean | null; knobs: Backend | null }) {
  const c = useChats(STUDIO)
  return (
    <div className="flex min-h-0 flex-1">
      <Studio epoch={c.epoch} chat={(close) => (
        <ChatView
          key={c.chatId ?? 'none'} scope={STUDIO} chatId={c.chatId} current={c.current} onClose={close}
          autoSend={c.opening} onAutoSent={c.opened} onStart={(text, tuning) => void c.start(text, tuning)} onTurnDone={c.turnDone}
          knobs={knobs}
          intro={{ lede: '工作流', body: '阶段、能力、断点。' }}
          welcome={{ headline: '工作流', body: '阶段、能力、断点。' }}
          drawer={
            <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                        creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                        cover={ASSETS.studio} title="编辑台" />
          }
        />
      )} />
    </div>
  )
}
