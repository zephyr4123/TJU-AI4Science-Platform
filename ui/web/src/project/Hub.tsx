// 项目页（主人 2026-09-22）：正中间一只对话输入框——一个项目只有一位助理，对话入口就这一个，放在正中间（像 Claude 的首页：
// 上面一句话，下面输入框）。上面是项目名与目标一句；输入框里打的第一句话开一段新对话，页面随即变成整屏的对话（ProjectPlace）。
// 输入框底下是这个项目的工作区，一行一个：名字、现在到哪一步（一个词，颜色照三态）、走到第几步与产出几次；点一行进工作区页。
// 「新建」在清单那一行，点了才展开表单（project/NewWorkspace）。过去的对话在「对话 · N」的抽屉里。右上角「…」里是删除项目。
import { DotsThree, Plus, Trash } from '@phosphor-icons/react'
import { type ReactNode, useState } from 'react'

import type { Backend, ProjectDetail, WorkspaceRow } from '@/api/types'
import { coverOf } from '@/assets'
import { Composer } from '@/chat/Composer'
import { useTuning } from '@/chat/useTuning'
import { ErrorNote } from '@/components/bits'
import HoldButton from '@/components/reactbits/HoldButton'
import { StatusMark } from '@/components/reactbits/StatusMark'
import { Scene } from '@/components/Scene'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { Tuning } from '@/api/types'
import type { Tone } from '@/components/bits'
import { cn } from '@/lib/utils'

import { rowState } from './derive'
import { NewWorkspace } from './NewWorkspace'

const TONE: Record<Tone, string> = {
  neutral: 'text-muted-foreground', ok: 'text-ok', warn: 'text-wait', bad: 'text-bad', primary: 'text-primary',
}

export function Hub({ project, backends, busy, onStart, drawer, onOpenWorkspace, onCreatedWorkspace, onRemove, menu }: {
  project: ProjectDetail
  backends: Backend[] | null
  /** 正在开一段对话：输入框先不许再发 */
  busy: boolean
  /** 输入框里的第一句：开一段（带上选的哪家、模型与思考深度），页面随即切成整屏的对话 */
  onStart: (text: string, tuning: Tuning, backend: string | null) => void
  /** 「对话 · N」那只抽屉 */
  drawer: ReactNode
  onOpenWorkspace: (id: string) => void
  onCreatedWorkspace: (id: string) => void
  /** 删整个项目：连工作区、对话及其会话、机器上的镜像 */
  onRemove: () => Promise<void>
  /** 窄屏时地方清单的入口 */
  menu?: ReactNode
}) {
  const t = useTuning(backends, null)
  const [creating, setCreating] = useState(false)
  return (
    <div className="relative h-full overflow-y-auto">
      <Scene picture={coverOf(project.id)} veil="mist" />
      <div className="absolute top-3 right-4 z-10"><ProjectMenu title={project.title} onRemove={onRemove} /></div>
      {menu && <div className="absolute top-3 left-4 z-10">{menu}</div>}
      <div className="relative mx-auto flex min-h-full w-full max-w-[44rem] flex-col px-6 pt-[12vh] pb-16">
        <h1 className="text-center font-serif text-[2rem] leading-[1.25] font-semibold tracking-tight text-balance">{project.title}</h1>
        {project.goal && <p className="t-body mx-auto mt-3 text-center text-muted-foreground">{project.goal}</p>}

        <Composer className="mt-8 px-0 pt-0 pb-0" placeholder="要做什么？" busy={busy}
                  thinking={t.thinking} knobs={t.knobs} tuning={t.tuning} onTune={t.onTune}
                  who={backends ? { options: backends, value: t.backendName ?? '', onChange: t.choose } : undefined}
                  onSend={(text) => onStart(text, t.tuning, t.backendName)} />

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
          {failed && <ErrorNote text={failed} className="py-1" />}
        </div>
      </PopoverContent>
    </Popover>
  )
}
