// 顶栏的工作区：一枚胶囊写着当前工作区的标题，点开是一张清单——每个工作区一行，说它走到哪了；
// 末行「起一个新的」。工作区是页面认路的第一件事（纲领 P-15）。
import { Check, ChevronDown, Plus } from 'lucide-react'
import { useState } from 'react'

import type { WorkspaceSummary } from '@/api/types'
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
          className={cn('flex h-9 max-w-[22rem] min-w-0 items-center gap-2 rounded-full border bg-background pr-3 pl-4',
                        'text-left transition-colors hover:border-primary/50 focus-visible:outline-2 focus-visible:outline-ring')}
        >
          <span className={cn('truncate font-serif text-[0.9375rem] font-semibold', !current && 'text-muted-foreground')}>
            {current ? current.title : ordered.length ? '选工作区' : '无工作区'}
          </span>
          {current && <span className="t-label hidden whitespace-nowrap sm:inline">{stageSentence(current)}</span>}
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={8} className="w-[24rem] p-2">
        <p className="px-3 pt-2 pb-2 font-serif text-[0.9375rem] font-semibold">工作区</p>
        <ul className="max-h-[22rem] overflow-y-auto">
          {ordered.map((w) => (
            <li key={w.id}>
              <button
                type="button" onClick={() => { onPick(w.id); setOpen(false) }}
                aria-current={w.id === selected ? 'true' : undefined}
                className={cn('flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left transition-colors',
                              'hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring',
                              w.id === selected && 'bg-accent')}
              >
                <span className="grid size-5 shrink-0 place-items-center pt-0.5">
                  {w.id === selected && <Check className="size-4 text-primary" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.9375rem] font-medium">{w.title}</span>
                  <span className="block text-[0.75rem] text-muted-foreground">
                    <span className="font-mono">{w.id}</span>，{stageSentence(w)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button" onClick={() => { onNew(); setOpen(false) }}
          className="mt-1 flex w-full items-center gap-2 rounded-lg border-t px-3 py-2.5 text-left text-[0.875rem] text-primary hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          <Plus className="size-4" />新建
        </button>
      </PopoverContent>
    </Popover>
  )
}
