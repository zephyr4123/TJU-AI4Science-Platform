// 顶栏的工作区：一枚胶囊——封面小图 + 标题 + 走到哪，点开是一张逐条浮现的清单（reactbits AnimatedList 改装），
// 每个工作区一行带封面缩略图；末行「新建」。工作区是页面认路的第一件事（纲领 P-15），封面按名字稳定地挑。
import { CaretDown, FolderSimplePlus } from '@phosphor-icons/react'
import { useState } from 'react'

import type { WorkspaceSummary } from '@/api/types'
import { coverOf } from '@/assets'
import { AnimatedList } from '@/components/reactbits/AnimatedList'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { STAGE_LABEL } from '@/lib/humanize'
import { cn } from '@/lib/utils'

interface Props {
  workspaces: WorkspaceSummary[] | null
  selected: string | null
  onPick: (id: string) => void
  onNew: () => void
}

/** 一行里说这份需求走到哪：还没起需求、需求还在聊、已发布…、跑了几次实验。 */
export function stageSentence(w: WorkspaceSummary): string {
  if (!w.task) return '还没有需求'
  if (w.task.stage === 'baselined' && w.runs > 0) return `跑了 ${w.runs} 次实验`
  return STAGE_LABEL[w.task.stage]
}

export function WorkspaceSwitcher({ workspaces, selected, onPick, onNew }: Props) {
  const [open, setOpen] = useState(false)
  const ordered = workspaces ? [...workspaces].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? '')) : []
  const current = ordered.find((w) => w.id === selected) ?? null
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button" aria-label="切换工作区"
          className={cn('flex h-9 max-w-[13rem] min-w-0 items-center gap-2 rounded-full border bg-background/70 pr-3 pl-1.5 backdrop-blur-sm sm:max-w-[24rem]',
                        'text-left transition-colors hover:border-primary/50 focus-visible:outline-2 focus-visible:outline-ring')}
        >
          {current
            ? <img src={coverOf(current.id).thumb} alt="" className="size-6 shrink-0 rounded-full object-cover" />
            : <span className="size-6 shrink-0 rounded-full border border-dashed" aria-hidden="true" />}
          <span className={cn('truncate font-serif text-[0.9375rem] font-semibold', !current && 'text-muted-foreground')}>
            {current ? current.title : ordered.length ? '选工作区' : '无工作区'}
          </span>
          {current && <span className="t-label hidden whitespace-nowrap sm:inline">{stageSentence(current)}</span>}
          <CaretDown className="size-4 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={8} className="w-[24rem] p-2">
        <p className="px-3 pt-2 pb-2 font-serif text-[0.9375rem] font-semibold">工作区</p>
        <AnimatedList
          items={ordered} keyOf={(w) => w.id} fade="popover" listClassName="max-h-[22rem]"
          render={(w) => (
            <button
              type="button" onClick={() => { onPick(w.id); setOpen(false) }}
              aria-current={w.id === selected ? 'true' : undefined}
              className={cn('flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors',
                            'hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring',
                            w.id === selected && 'bg-accent')}
            >
              <img src={coverOf(w.id).thumb} alt="" width={56} height={36}
                   className={cn('h-9 w-14 shrink-0 rounded-md object-cover', w.id === selected && 'ring-2 ring-primary ring-offset-1 ring-offset-popover')} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[0.9375rem] font-medium">{w.title}</span>
                <span className="block text-[0.75rem] text-muted-foreground">
                  <span className="font-mono">{w.id}</span>，{stageSentence(w)}
                </span>
              </span>
            </button>
          )}
        />
        <button
          type="button" onClick={() => { onNew(); setOpen(false) }}
          className="mt-1 flex w-full items-center gap-2 rounded-lg border-t px-3 py-2.5 text-left text-[0.875rem] text-primary hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          <FolderSimplePlus className="size-4" />新建
        </button>
      </PopoverContent>
    </Popover>
  )
}
