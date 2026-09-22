// 壳：左边地方栏（先选世界：工作区 / 编辑台，再选工作区），右边页眉 + 当前地方的内容（外层 #58 #64 #70 #79 #104 #111）。
// 页面先认工作区（一个工作区一份需求，P-15）：主页面是这个工作区的两个镜头——看板（需求没确认就是需求文档，确认了是一条流程
// 一张表）与文件（盘上的目录树与文件内容，只读），页眉上切换，对话在右边两个镜头都在。编辑台是全局一个流程库，也是两个镜头——
// 流程（画布）与能力（陈列与详情，外层 #112）——加流程助理的悬浮对话窗（外层 #100）；和工作区是两个平行的世界：地方栏上是一个
// 开关，进了编辑台工作区块整段收掉，页眉也不跟着工作区换（P-16）。设置（P-25，外层 #134）是压在当前地方上的一块悬浮板，
// 入口在地方栏的脚，主题开关也在里面。页面只是 `ai4sci serve` 的客户端。
import { ChatsCircle } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { type ReactNode, useEffect, useState } from 'react'

import { api, inWorkspace, STUDIO } from '@/api/client'
import type { Backend } from '@/api/types'
import { ASSETS, coverOf } from '@/assets'
import { Board } from '@/board/Board'
import { ChatView } from '@/chat/ChatView'
import { Band } from '@/components/Band'
import { Scene } from '@/components/Scene'
import SpecularButton from '@/components/reactbits/SpecularButton'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Files } from '@/files/Files'
import { stageSentence } from '@/lib/humanize'
import { useToken } from '@/lib/tokens'
import { useChats } from '@/lib/useChats'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import type { Place, World } from '@/places/place'
import { PlacesSheet } from '@/places/PlacesSheet'
import { Rail } from '@/places/Rail'
import { SettingsBoard } from '@/settings/SettingsBoard'
import { ChatDrawer } from '@/sidebar/ChatDrawer'
import { Studio, type StudioView } from '@/studio/Studio'
import { NewWorkspace } from '@/workspace/NewWorkspace'

const PICKED_KEY = 'ai4sci.workspace'

/** 工作区页面的两个镜头：看板（做到哪了、在等谁）与文件（盘上有什么） */
type View = 'board' | 'files'
/** 页眉上那对镜头开关：哪个地方、现在哪个、有哪几个 */
interface Lens { value: string; options: { value: string; label: string }[]; onChange: (value: string) => void }
/** 有作业在跑时多久重拉一次：别的对话起的作业跑完，这边才看得见 */
const POLL_MS = 10_000

export default function App() {
  const workspaces = useResource(api.workspaces, [])
  const health = useResource(api.health, [])
  // 每家 agent 的旋钮清单与新对话用的值（外层 #86，P-25）：对话用哪家就摆哪家的；设置里改了缺省要重拉
  const backends = useResource(api.backends, [])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsDot = health.data ? health.data.checks_ok === false : false
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
  // 编辑台的镜头与「能力」镜头里打开的详情：从画布 / 配置板点一个能力的名字过来时两样一起设
  const [studioView, setStudioView] = useState<StudioView>('flow')
  const [capFocus, setCapFocus] = useState<string | null>(null)
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
    // 挑了地方就是要看那个地方：设置板跟着收
    onPick: (id: string) => { setPicked(id); setCreating(false); setStudio(false); setFocus(null); setOpened(null); setSettingsOpen(false) },
    onNew: () => { setCreating(true); setStudio(false); setSettingsOpen(false) },
    onWorld: (world: World) => { setStudio(world === 'studio'); setSettingsOpen(false) },
    settingsOpen,
    settingsDot,
    onSettings: () => setSettingsOpen((open) => !open),
  }
  // 设置里检查过、改过：/health 的那一位与每家新对话用的值都可能变了
  const settingsChanged = () => { void health.reload(); void backends.reload() }

  return (
    <TooltipProvider>
      <div className="flex h-dvh overflow-hidden">
        {wide && <Rail {...places} />}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* 设置是全局的，不挂在哪个地方底下（主人 2026-09-22）：开着时地方的页眉（工作区标题、看板 / 文件）整个让开，
              宽屏没有页眉，窄屏只留一条放地方清单的入口——与门口那一屏同一条规矩 */}
          {settingsOpen && !wide && (
            <Top place={{ kind: 'door' }} menu={<PlacesSheet {...places} />} title="设置" note={null} lens={null} />
          )}
          {place && !settingsOpen && (
            <Top place={place} menu={wide ? null : <PlacesSheet {...places} />}
                 title={place.kind === 'studio' ? '编辑台' : place.kind === 'door' ? '新建工作区' : current?.title ?? place.id}
                 note={current && place.kind === 'workspace' ? stageSentence(current) : null}
                 lens={place.kind === 'workspace'
                   ? { value: view, options: [{ value: 'board', label: '看板' }, { value: 'files', label: '文件' }],
                       onChange: (v) => { setView(v as View); setOpened(null) } }
                   : place.kind === 'studio'
                     ? { value: studioView, options: [{ value: 'flow', label: '流程' }, { value: 'caps', label: '能力' }],
                         onChange: (v) => { setStudioView(v as StudioView); setCapFocus(null) } }
                     : null} />
          )}
          <div className="relative flex min-h-0 flex-1 flex-col">
            {settingsOpen
              ? (
                // 设置占满地方栏右边整块：底下铺一层雾景，板四周留边、悬在上面
                <div className="relative flex min-h-0 flex-1">
                  <Scene picture={ASSETS.board} veil="mist" />
                  <SettingsBoard onClose={() => setSettingsOpen(false)} onChanged={settingsChanged} />
                </div>
              )
              : place?.kind === 'studio'
              ? <StudioPlace healthy={healthy} backends={backends.data} view={studioView} focus={capFocus}
                             onFocus={(name) => { setCapFocus(name); if (name) setStudioView('caps') }} />
              : place?.kind === 'door'
                ? <NewWorkspace existing={workspaces.data ?? []} onCreated={(id) => void created(id)}
                                onCancel={wsId ? () => setCreating(false) : undefined} />
                : place
                  ? (
                    // 雾景挂在这一层：换工作区只重建里面的 MainView，底图不重贴（主人：切换那一瞬闪屏）
                    <div className="relative flex min-h-0 flex-1">
                      <Scene picture={ASSETS.board} veil="mist" />
                      <MainView key={place.id} wsId={place.id} healthy={healthy} backends={backends.data} title={current?.title ?? place.id}
                                view={view} focus={focus} opened={opened} onOpen={setOpened}
                                onOpenFiles={(path) => { setFocus(path); setView('files') }}
                                onOpenBoard={(oid) => { setOpened(oid); setView('board') }} />
                    </div>
                  )
                  : <div className="flex-1" />}
          </div>
        </div>
      </div>
    </TooltipProvider>
  )
}

/** 页眉只属于当前地方：标题 + 走到哪 + 两个镜头的开关（工作区是看板 / 文件，编辑台是流程 / 能力），底下封面糊成一抹颜色
 *  （换工作区就换色）；门口宽屏不要页眉（画面铺满），窄屏留一条放入口。主题开关搬进了设置（P-25）。 */
function Top({ place, title, note, menu, lens }: {
  place: Place; title: string; note: string | null; menu: ReactNode; lens: Lens | null
}) {
  if (place.kind === 'door' && !menu) return null
  const picture = place.kind === 'studio' ? ASSETS.studio : place.kind === 'workspace' ? coverOf(place.id) : null
  const row = (
    <header className="flex h-14 items-center gap-3 px-4 sm:px-5">
      {menu}
      <span className="min-w-0 truncate font-serif text-[1.0625rem] font-semibold tracking-[0.02em]">{title}</span>
      {note && <span className="t-label hidden whitespace-nowrap sm:inline">{note}</span>}
      {lens && (
        <Tabs value={lens.value} onValueChange={lens.onChange} className="ml-auto">
          <TabsList aria-label="镜头" className="bg-background/70 backdrop-blur-sm">
            {lens.options.map((o) => <TabsTrigger key={o.value} value={o.value} className="px-3">{o.label}</TabsTrigger>)}
          </TabsList>
        </Tabs>
      )}
    </header>
  )
  if (!picture) return <div className="shrink-0 border-b bg-card">{row}</div>
  return <Band picture={picture} veil="wash" blur className="shrink-0 border-b">{row}</Band>
}

/** 主页面：这个工作区的看板或文件铺满，对话在右边一列（宽屏常开、可收；窄屏是从右边拉出来的抽屉）。
 *  换工作区时父组件用 key 重建，状态天然按工作区隔离。 */
function MainView({ wsId, title, healthy, backends, view, focus, opened, onOpen, onOpenFiles, onOpenBoard }: {
  wsId: string; title: string; healthy: boolean | null; backends: Backend[] | null
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
      autoSend={c.opening} onAutoSent={c.opened} onStart={(text, tuning, backend) => void c.start(text, tuning, backend)}
      onTurnDone={c.turnDone}
      backends={backends}
      intro={{ lede: '课题', body: '问题、材料、评价标准。' }}
      welcome={{ headline: '课题', body: '问题、材料、评价标准。' }}
      drawer={
        <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                    creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                    cover={coverOf(wsId)} title={title} />
      }
    />
  )
  // 这个工作区那一整份（需求、产出、流程的进度、作业）两个镜头共用，拉一次；有作业在跑时轮询；对话每一轮结束重读。
  // 能力表也拉一次：看板每一列底下的能力、产出记录里能力的名与参数的 label 都从它查（P-21：翻译在源头，页面只查表）
  const doc = useResource(() => api.workspace(wsId), [wsId, c.epoch])
  const caps = useResource(api.capabilities, [])
  const skills = useResource(api.skills, [])
  const busy = (doc.data?.running ?? 0) > 0
  const reload = doc.reload
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => { void reload() }, POLL_MS)
    return () => clearInterval(timer)
  }, [busy, reload])
  return (
    <div className="relative flex min-h-0 flex-1">
      <main className="relative min-w-0 flex-1">
        {/* 两个镜头都常驻，切换只是显示 / 隐藏：不重新挂载、不重新拉数据，树的展开与滚动位置也都保住 */}
        <div className={cn('relative h-full', view !== 'board' && 'hidden')}>
          <Board workspace={wsId} doc={doc} caps={caps} skills={skills} opened={opened} onOpen={onOpen} onOpenFiles={onOpenFiles} />
        </div>
        <div className={cn('relative h-full', view !== 'files' && 'hidden')}>
          <Files key={focus ?? ''} workspace={wsId} doc={doc} caps={caps} epoch={c.epoch} focus={focus} onOpenBoard={onOpenBoard} />
        </div>
        {!open && <ChatEntry onOpen={() => setChatOpen(true)} />}
      </main>
      {wide ? (
        // 对话是一块悬在雾景上的板，不是一列（主人：border-l 一刀切出来的全高区域像拼上去的）：四周留 12px，
        // 和文件镜头的内容面同一种材料——圆角、长而软的投影、一圈 6% 的 ring；板和看板之间露出的雾景就是分隔
        <aside className={cn('relative h-full shrink-0 transition-[width] duration-200',
                             open ? 'w-[31.5rem]' : 'w-0 overflow-hidden')}
               aria-label="对话" aria-hidden={!open}>
          <div className="relative my-3 mr-3 h-[calc(100%-1.5rem)] w-[30rem] overflow-hidden rounded-2xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.05),0_18px_44px_-22px_rgb(0_0_0/0.28)] ring-1 ring-foreground/[0.06]">
            {chat}
          </div>
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

/** 对话收起后右下角的入口：一颗带字的玻璃键（主人：小圆钮太小、看不出是干什么的），工作区与编辑台同一颗 */
export function ChatEntry({ onOpen }: { onOpen: () => void }) {
  const still = useReducedMotion() === true
  const indigo = useToken('--primary')
  const card = useToken('--card')
  const ink = useToken('--foreground')
  return (
    <div className="absolute right-5 bottom-5 z-10">
      <SpecularButton size="lg" radius={18} tint={card} tintOpacity={0.78} blur={12} textColor={ink} lineColor={indigo} baseColor={ink}
                      intensity={1.1} speed={still ? 0 : 0.35} followMouse={!still} autoAnimate={false} onClick={onOpen}
                      className="shadow-lg ring-1 ring-foreground/10">
        <span className="inline-flex items-center gap-2"><ChatsCircle weight="fill" className="size-5 text-primary" />打开对话</span>
      </SpecularButton>
    </div>
  )
}

/** 编辑台：两个镜头铺满，流程助理的对话是右下角的悬浮窗（对话的状态在这儿，窗口在画布上）。 */
function StudioPlace({ healthy, backends, view, focus, onFocus }: {
  healthy: boolean | null; backends: Backend[] | null; view: StudioView; focus: string | null; onFocus: (name: string | null) => void
}) {
  const c = useChats(STUDIO)
  return (
    <div className="flex min-h-0 flex-1">
      <Studio epoch={c.epoch} view={view} focus={focus} onFocus={onFocus} chat={(close) => (
        <ChatView
          key={c.chatId ?? 'none'} scope={STUDIO} chatId={c.chatId} current={c.current} onClose={close}
          autoSend={c.opening} onAutoSent={c.opened} onStart={(text, tuning, backend) => void c.start(text, tuning, backend)}
          onTurnDone={c.turnDone}
          backends={backends}
          intro={{ lede: '流程', body: '阶段、能力、断点。' }}
          welcome={{ headline: '流程', body: '阶段、能力、断点。' }}
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
