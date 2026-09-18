// 壳：左边地方栏（先选世界：工作区 / 编辑台，再选工作区），右边页眉 + 当前地方的内容（外层 #58 #64 #70 #79）。
// 页面先认工作区（一个工作区一份需求，P-15）：主页面是这个工作区的对话 + 流程脊柱。编辑台是全局一个库：造流助理的对话 + 工作流墙、
// 七段货架、拼流台，和工作区是两个平行的世界：地方栏上是一个开关，进了编辑台工作区块整段收掉，页眉也不跟着工作区换（P-16）。页面只是 `ai4sci serve` 的客户端。
import { type ReactNode, useState } from 'react'

import { api, inWorkspace, STUDIO } from '@/api/client'
import { ASSETS, coverOf } from '@/assets'
import { ChatView } from '@/chat/ChatView'
import { Band } from '@/components/Band'
import { Scene } from '@/components/Scene'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { stageSentence } from '@/lib/humanize'
import { useChats } from '@/lib/useChats'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import type { Place, World } from '@/places/place'
import { PlacesSheet } from '@/places/PlacesSheet'
import { Rail } from '@/places/Rail'
import { ChatDrawer } from '@/sidebar/ChatDrawer'
import { Spine } from '@/spine/Spine'
import { Studio } from '@/studio/Studio'
import { NewWorkspace } from '@/workspace/NewWorkspace'

export default function App() {
  const workspaces = useResource(api.workspaces, [])
  const health = useResource(api.health, [])
  const [picked, setPicked] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [studio, setStudio] = useState(false)
  const wide = useMediaQuery(WIDE)

  const newest = workspaces.data?.length
    ? [...workspaces.data].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))[0].id : null
  const wsId = picked && workspaces.data?.some((w) => w.id === picked) ? picked : newest
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
    onPick: (id: string) => { setPicked(id); setCreating(false); setStudio(false) },
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
                 note={place.kind === 'studio' ? '不分工作区' : current && place.kind === 'workspace' ? stageSentence(current) : null} />
          )}
          {place?.kind === 'studio'
            ? <StudioView healthy={healthy} />
            : place?.kind === 'door'
              ? <NewWorkspace existing={workspaces.data ?? []} onCreated={(id) => void created(id)}
                              onCancel={wsId ? () => setCreating(false) : undefined} />
              : place
                ? <MainView key={place.id} wsId={place.id} healthy={healthy} title={current?.title ?? place.id} />
                : <div className="flex-1" />}
        </div>
      </div>
    </TooltipProvider>
  )
}

/** 页眉只属于当前地方：工作区的标题 + 走到哪，底下封面糊成一抹颜色（换工作区就换色）；编辑台是库的横幅；门口宽屏不要页眉（画面铺满），窄屏留一条放入口。 */
function Top({ place, title, note, menu }: { place: Place; title: string; note: string | null; menu: ReactNode }) {
  if (place.kind === 'door' && !menu) return null
  const picture = place.kind === 'studio' ? ASSETS.studio : place.kind === 'workspace' ? coverOf(place.id) : null
  const row = (
    <header className="flex h-14 items-center gap-3 px-4 sm:px-5">
      {menu}
      <span className="min-w-0 truncate font-serif text-[1.0625rem] font-semibold tracking-[0.02em]">{title}</span>
      {note && <span className="t-label hidden whitespace-nowrap sm:inline">{note}</span>}
    </header>
  )
  if (!picture) return <div className="shrink-0 border-b bg-card">{row}</div>
  return <Band picture={picture} veil="wash" blur className="shrink-0 border-b">{row}</Band>
}

/** 主页面：这个工作区的对话 + 脊柱。换工作区时父组件用 key 重建，状态天然按工作区隔离。 */
function MainView({ wsId, title, healthy }: { wsId: string; title: string; healthy: boolean | null }) {
  const scope = inWorkspace(wsId)
  const c = useChats(scope)
  const wide = useMediaQuery(WIDE)
  // 没点过：宽屏常开、窄屏收着；窄屏上脊柱是一张从右边拉出来的抽屉
  const [boardOpen, setBoardOpen] = useState<boolean | null>(null)
  const open = boardOpen ?? wide
  const spine = <Spine workspace={wsId} epoch={c.epoch} chatId={c.chatId} />
  return (
    <div className="flex min-h-0 flex-1">
      <ChatView
        key={c.chatId ?? 'none'} scope={scope} chatId={c.chatId} current={c.current}
        boardOpen={open} onToggleBoard={() => setBoardOpen(!open)}
        autoSend={c.opening} onAutoSent={c.opened} onStart={(text) => void c.start(text)} onTurnDone={c.turnDone}
        intro={{ lede: '先说清课题。', body: '想解决什么、数据在哪、什么算好。' }}
        hints={['说说你的课题', '数据在哪', '什么算好']}
        welcome={{
          headline: '把实验交给助理。',
          body: '你只做两件事：发布需求，验收结果。',
        }}
        drawer={
          <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                      creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                      cover={coverOf(wsId)} title={title} description="这个工作区的对话" />
        }
      />
      {wide ? (
        <aside
          className={cn('relative h-full shrink-0 border-l transition-[width] duration-200',
                        open ? 'w-[27.5rem]' : 'w-0 overflow-hidden border-l-0')}
          aria-label="工作流" aria-hidden={!open}
        >
          <Scene picture={ASSETS.board} veil="mist" />
          <div className="relative h-full w-[27.5rem]">{spine}</div>
        </aside>
      ) : (
        <Sheet open={open} onOpenChange={setBoardOpen}>
          <SheetContent side="right"
                        className="gap-0 p-0 data-[side=right]:w-[100vw] data-[side=right]:sm:w-[27.5rem] data-[side=right]:sm:max-w-[27.5rem]">
            <SheetHeader className="sr-only"><SheetTitle>工作流</SheetTitle></SheetHeader>
            <Scene picture={ASSETS.board} veil="mist" />
            <div className="relative h-full">{spine}</div>
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
          autoSend={c.opening} onAutoSent={c.opened} onStart={(text) => void c.start(text)} onTurnDone={c.turnDone}
          intro={{ lede: '说清要拼什么流。', body: '给谁用、从哪步起、要不要验证。' }}
          hints={['说说要拼的流', '给谁用', '要不要验证']}
          welcome={{
            headline: '把能力拼成流。',
            body: '存进库，研究者取走就能跑。',
          }}
          drawer={
            <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                        creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                        cover={ASSETS.studio} title="编辑台" description="编辑台的对话" />
          }
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto"><Studio epoch={c.epoch} /></div>
    </div>
  )
}
