// 项目页（主人 2026-09-22）：正中间一只对话输入框——一个项目只有一位助理，对话入口就这一个，放在正中间（像 Claude 的首页：
// 平台的标、上面一句话，下面输入框）。输入框里打的第一句话就开始对话：输入框动画下沉到底，正文接在上面，这一轮从按下回车起就在屏上
// （主人：不要闪一下再切过去）；「‹ 项目名」回来。输入框底下是这个项目的工作区，一行一个：名字、现在到哪一步（一个词，颜色照
// 三态）、走到第几步与产出几次；点一行进工作区页。「新建」在清单那一行，点了才展开表单（project/NewWorkspace）。过去的对话
// 在「对话 · N」的抽屉里，挑一段也切成整屏的对话。右上角「…」里是删除项目。
import { DotsThree, Plus, Trash } from '@phosphor-icons/react'
import { LayoutGroup, motion, useReducedMotion } from 'motion/react'
import { type ReactNode, useState } from 'react'

import { inProject } from '@/api/client'
import type { Backend, ProjectDetail, WorkspaceRow } from '@/api/types'
import { coverOf } from '@/assets'
import { ChatDrawer } from '@/chat/ChatDrawer'
import { Composer } from '@/chat/Composer'
import { Transcript } from '@/chat/Transcript'
import { useConversation } from '@/chat/useConversation'
import { WELCOME } from '@/chat/Welcome'
import { ErrorNote, type Tone } from '@/components/bits'
import { Logo } from '@/components/Logo'
import HoldButton from '@/components/reactbits/HoldButton'
import { StatusMark } from '@/components/reactbits/StatusMark'
import { Scene } from '@/components/Scene'
import { Top } from '@/components/Top'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { usd } from '@/lib/format'
import type { useChats } from '@/lib/useChats'
import { cn } from '@/lib/utils'

import { rowState } from './derive'
import { NewWorkspace } from './NewWorkspace'

const TONE: Record<Tone, string> = {
  neutral: 'text-muted-foreground', ok: 'text-ok', warn: 'text-wait', bad: 'text-bad', primary: 'text-primary',
}

export function ProjectPage({ project, chats: c, backends, healthy, onOpenWorkspace, onCreatedWorkspace, onRemove, menu }: {
  project: ProjectDetail
  chats: ReturnType<typeof useChats>
  backends: Backend[] | null
  healthy: boolean | null
  onOpenWorkspace: (id: string) => void
  onCreatedWorkspace: (id: string) => void
  /** 删整个项目：连工作区、对话及其会话、机器上的镜像 */
  onRemove: () => Promise<void>
  /** 窄屏时地方清单的入口 */
  menu?: ReactNode
}) {
  const still = useReducedMotion() === true
  // 两个样子：正中间输入框的那页（shown 为 null，第一句开新的一段），和整屏的对话（看 shown 那段）
  const [talking, setTalking] = useState(false)
  const [shown, setShown] = useState<string | null>(null)
  const current = shown ? c.chats.data?.find((x) => x.chat_id === shown) ?? null : null
  const conv = useConversation({
    scope: inProject(project.id), chatId: shown, current, backends,
    create: async (tuning, backend) => { const meta = await c.newChat(tuning, backend); setShown(meta.chat_id); return meta },
    onTurnDone: c.turnDone,
  })
  const t = conv.tuning
  const [creating, setCreating] = useState(false)

  const drawer = (
    <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={shown} healthy={healthy} creating={c.creating}
                onSelect={(id) => { setShown(id); setTalking(true) }}
                onNew={() => { void c.newChat().then((meta) => { setShown(meta.chat_id); setTalking(true) }) }}
                onRemove={async (id) => { await c.remove(id); if (id === shown) { setShown(null); setTalking(false) } }}
                cover={coverOf(project.id)} title={project.title} />
  )
  // 同一只输入框在两个样子里各站一处，layoutId 让它从正中间竖直滑到底（减少动效时直接出现）。
  // 两边带 layoutId 的盒子都要紧贴玻璃框、同宽（44rem）：动画按盒子的左上角算，盒子比玻璃框宽就会斜着走
  const composer = (className?: string) => (
    <motion.div layoutId={`composer-${project.id}`} layout={still ? false : 'position'} className={cn('w-full max-w-[44rem]', className)}>
      <Composer busy={conv.busy} placeholder={talking ? 'Enter 发送，Shift + Enter 换行' : '要做什么？'}
                thinking={t.thinking} knobs={t.knobs} tuning={t.tuning} onTune={t.onTune} className="px-0 pt-0 pb-0"
                who={shown || !backends ? undefined : { options: backends, value: t.backendName ?? '', onChange: t.choose }}
                onSend={(text) => { setTalking(true); void conv.send(text) }} />
    </motion.div>
  )

  return (
    <LayoutGroup id={`project-${project.id}`}>
      {talking && (
        <Top menu={menu} picture={coverOf(project.id)}
             back={{ label: project.title, onClick: () => { setTalking(false); setShown(null) } }}
             title={current?.title ?? '新对话'}
             tail={<span className="ml-auto flex items-center gap-3">
               {current && current.cost_usd > 0 && <span className="t-label whitespace-nowrap">{usd(current.cost_usd)}</span>}
               {drawer}
             </span>} />
      )}
      <div className="relative flex min-h-0 flex-1 flex-col">
        <Scene picture={coverOf(project.id)} veil="mist" />
        {talking ? (
          <>
            <motion.div initial={still ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}
                        className="relative flex min-h-0 flex-1 flex-col">
              <Transcript doc={conv.doc} turns={conv.turns} thinking={t.thinking} welcome={WELCOME.research} error={conv.error} />
            </motion.div>
            <div className="relative z-10 px-6 pt-3 pb-6">{composer('mx-auto')}</div>
          </>
        ) : (
          <div className="relative min-h-0 flex-1 overflow-y-auto">
            <div className="absolute top-3 right-4 z-10"><ProjectMenu title={project.title} onRemove={onRemove} /></div>
            {menu && <div className="absolute top-3 left-4 z-10">{menu}</div>}
            <div className="relative mx-auto flex min-h-full w-full max-w-[47rem] flex-col px-6 pt-[10vh] pb-16">
              {/* 平台的标在正中、项目名在下（外层 #139）：像 Claude 的首页，标先于字 */}
              <Logo className="mx-auto size-12 text-primary" />
              <h1 className="mt-5 text-center font-serif text-[2rem] leading-[1.25] font-semibold tracking-tight text-balance">{project.title}</h1>
              {project.goal && <p className="t-body mx-auto mt-3 text-center text-muted-foreground">{project.goal}</p>}
              {composer('mt-8')}
              <section className="mt-12">
                <div className="flex items-center gap-3">
                  <h2 className="t-step">工作区</h2>
                  {project.workspaces.length > 0 && <span className="t-label tabular">{project.workspaces.length}</span>}
                  {!creating && (
                    <Button variant="outline" size="sm" className="ml-auto rounded-full bg-card/70 backdrop-blur-sm" onClick={() => setCreating(true)}>
                      <Plus data-icon="inline-start" />新建
                    </Button>
                  )}
                </div>
                {creating && (
                  <div className="mt-4">
                    <NewWorkspace project={project.id} existing={project.workspaces.map((w) => w.id)}
                                  onCreated={(id) => { setCreating(false); onCreatedWorkspace(id) }} onCancel={() => setCreating(false)} />
                  </div>
                )}
                {project.workspaces.length === 0 && !creating && (
                  <p className="t-label mt-4">还没有工作区。跟助理说要做什么，或按「新建」。</p>
                )}
                {project.workspaces.length > 0 && (
                  <ul className="mt-3 divide-y divide-border/60">
                    {project.workspaces.map((row) => <li key={row.id}><Row row={row} onOpen={() => onOpenWorkspace(row.id)} /></li>)}
                  </ul>
                )}
              </section>
              <section className="mt-10 flex items-center">{drawer}</section>
            </div>
          </div>
        )}
      </div>
    </LayoutGroup>
  )
}

/** 一行工作区：状态符、名字与两句小字、状态一个词 */
function Row({ row, onOpen }: { row: WorkspaceRow; onOpen: () => void }) {
  const s = rowState(row)
  return (
    <button type="button" onClick={onOpen}
            className="-mx-3 flex w-[calc(100%+1.5rem)] items-center gap-4 rounded-xl px-3 py-3.5 text-left transition-colors hover:bg-card/70 focus-visible:outline-2 focus-visible:outline-ring">
      <StatusMark status={s.mark} className={cn(TONE[s.tone])} />
      <span className="min-w-0 flex-1">
        <span className="block truncate t-step">{row.title}</span>
        {s.details.length > 0 && (
          <span className="t-label mt-0.5 flex flex-wrap gap-x-4 tabular">
            {s.details.map((d) => <span key={d}>{d}</span>)}
          </span>
        )}
      </span>
      <span className={cn('shrink-0 text-[0.8125rem] whitespace-nowrap', TONE[s.tone])}>{s.word}</span>
    </button>
  )
}

/** 右上角的「…」：里面只有一件事——删除项目；按住一秒才删 */
function ProjectMenu({ title, onRemove }: { title: string; onRemove: () => Promise<void> }) {
  const [open, setOpen] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const remove = () => {
    setFailed(null)
    onRemove().then(() => setOpen(false)).catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="更多" className="bg-card/60 backdrop-blur-sm"><DotsThree weight="bold" /></Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[18rem] space-y-3 p-4">
        <p className="text-[0.875rem] font-medium">删除项目</p>
        <p className="line-clamp-2 text-[0.8125rem]">{title}</p>
        <p className="text-[0.75rem] text-muted-foreground">全部工作区、对话及其会话、机器上的镜像一起删，回不来。</p>
        <div className="flex items-center gap-3">
          <HoldButton onHold={remove} doneLabel="已删除"><Trash className="size-3.5" />删除</HoldButton>
        </div>
        {failed && <ErrorNote text={failed} />}
      </PopoverContent>
    </Popover>
  )
}
