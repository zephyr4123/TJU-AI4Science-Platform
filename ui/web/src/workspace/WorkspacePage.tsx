// 工作区页：这个工作区的两个镜头——看板（需求没确认就是需求文档，确认了是一条流程一张表）与文件（盘上的目录树与文件内容，
// 只读），页眉上切换；对话在右边那块板上，是项目的那一段（一个项目一位助理，工作区是它的工位；外层 #136），边看看板边说话。
// 页眉写「‹ 项目名  工作区 ▾」：项目名回项目页，工作区那一片下拉列兄弟工作区，直接换工位不用回项目页；右端「…」里是删除工作区。
import { DotsThree, Trash } from '@phosphor-icons/react'
import { type ReactNode, useEffect, useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { Capability, ProjectDetail, SkillEntry } from '@/api/types'
import { ASSETS, coverOf } from '@/assets'
import { Board } from '@/board/Board'
import { ChatPanel } from '@/chat/ChatPanel'
import { ErrorNote } from '@/components/bits'
import HoldButton from '@/components/reactbits/HoldButton'
import GlideSelect from '@/components/reactbits/GlideSelect'
import { Scene } from '@/components/Scene'
import { Top } from '@/components/Top'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Files } from '@/files/Files'
import { stageSentence } from '@/lib/humanize'
import { type Resource, useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

/** 两个镜头：看板（做到哪了、在等谁）与文件（盘上有什么） */
type View = 'board' | 'files'
/** 有作业在跑时多久重拉一次：别的对话起的作业跑完，这边才看得见 */
const POLL_MS = 10_000

export function WorkspacePage({ ws, project, epoch, caps, skills, chat, menu, onBack, onSwitch, onRemoved }: {
  ws: WorkspaceClient
  /** 所在的项目那一整份：页眉要项目名与兄弟工作区；还没回来就先只写 id */
  project: ProjectDetail | null
  /** 对话的轮次：每轮结束加一，看板与文件跟着重读 */
  epoch: number
  caps: Resource<Capability[]>
  skills: Resource<SkillEntry[]>
  /** 右边那块板里装的对话（项目的那一段） */
  chat: (close: () => void) => ReactNode
  menu?: ReactNode
  onBack: () => void
  onSwitch: (id: string) => void
  onRemoved: (leftovers: string[]) => Promise<void>
}) {
  const [view, setView] = useState<View>('board')
  // 从看板「打开目录」跳到文件镜头时定位到哪个产出；从文件镜头「在看板打开」回来时侧滑里开哪次产出
  const [focus, setFocus] = useState<string | null>(null)
  const [opened, setOpened] = useState<string | null>(null)
  // 这个工作区那一整份（需求、产出、流程的进度、作业）两个镜头共用，拉一次；有作业在跑时轮询；对话每一轮结束重读
  const doc = useResource(ws.detail, [ws.key, epoch])
  const busy = (doc.data?.running ?? 0) > 0
  const reload = doc.reload
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(() => { void reload() }, POLL_MS)
    return () => clearInterval(timer)
  }, [busy, reload])

  const row = project?.workspaces.find((w) => w.id === ws.id) ?? null
  const title = row?.title ?? doc.data?.title ?? ws.id
  const siblings = project?.workspaces ?? []
  return (
    <>
      <Top menu={menu} back={{ label: project?.title ?? ws.project, onClick: onBack }} picture={coverOf(ws.project)}
           title={siblings.length > 1
             ? <GlideSelect ariaLabel="换个工作区" size="md" value={ws.id} placeholder={title} menuWidth={240}
                            options={siblings.map((w) => ({ value: w.id, label: w.title }))}
                            onChange={(id) => { if (id !== ws.id) onSwitch(id) }}
                            className="min-w-0 font-serif text-[1.0625rem] font-semibold tracking-[0.02em]" />
             : title}
           note={row ? stageSentence(row) : null}
           lens={{ value: view, options: [{ value: 'board', label: '看板' }, { value: 'files', label: '文件' }],
                   onChange: (v) => { setView(v as View); setOpened(null) } }}
           tail={<WorkspaceMenu ws={ws} onRemoved={onRemoved} />} />
      <div className="relative flex min-h-0 flex-1">
        <Scene picture={ASSETS.board} veil="mist" />
        <ChatPanel chat={chat}>
          {/* 两个镜头都常驻，切换只是显示 / 隐藏：不重新挂载、不重新拉数据，树的展开与滚动位置也都保住 */}
          <div className={cn('relative h-full', view !== 'board' && 'hidden')}>
            <Board workspace={ws} doc={doc} caps={caps} skills={skills} opened={opened} onOpen={setOpened}
                   onOpenFiles={(path) => { setFocus(path); setView('files') }} />
          </div>
          <div className={cn('relative h-full', view !== 'files' && 'hidden')}>
            <Files key={focus ?? ''} workspace={ws} doc={doc} caps={caps} epoch={epoch} focus={focus}
                   onOpenBoard={(oid) => { setOpened(oid); setView('board') }} />
          </div>
        </ChatPanel>
      </div>
    </>
  )
}

/** 页眉右端的「…」：里面只有一件事——删除工作区（连产出、机器上的镜像一起；对话归项目，不动）；按住一秒才删 */
function WorkspaceMenu({ ws, onRemoved }: { ws: WorkspaceClient; onRemoved: (leftovers: string[]) => Promise<void> }) {
  const [open, setOpen] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const remove = () => {
    setFailed(null)
    ws.remove()
      .then(async (removed) => { setOpen(false); await onRemoved(removed.leftovers) })
      .catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="更多"><DotsThree weight="bold" /></Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[18rem] space-y-3 p-4">
        <p className="text-[0.875rem] font-medium">删除工作区</p>
        <p className="text-[0.75rem] text-muted-foreground">需求、原件、全部产出、机器上的镜像一起删，回不来；被兄弟工作区读过的删不了。</p>
        <div className="flex items-center gap-3">
          <HoldButton onHold={remove} doneLabel="已删除"><Trash className="size-3.5" />删除</HoldButton>
        </div>
        {failed && <ErrorNote text={failed} />}
      </PopoverContent>
    </Popover>
  )
}
