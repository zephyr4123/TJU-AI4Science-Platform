// 窄屏的地方栏：页眉左端的玻璃标记就是入口，点开一张从左边拉出来的清单——工作区逐条浮现（reactbits AnimatedList 改装）、末行「新建」，
// 分线下面是编辑台。和宽屏的 Rail 认同一份 Place。
import { Blueprint, Flask, FolderSimplePlus } from '@phosphor-icons/react'
import { useState } from 'react'

import { coverOf } from '@/assets'
import { AnimatedList } from '@/components/reactbits/AnimatedList'
import { GlassIcon } from '@/components/reactbits/GlassIcon'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { stageSentence } from '@/lib/humanize'
import { cn } from '@/lib/utils'

import { newestFirst, type PlacesProps } from './place'

const ROW = 'flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring'

export function PlacesSheet({ workspaces, place, onPick, onNew, onStudio }: PlacesProps) {
  const [open, setOpen] = useState(false)
  const go = (action: () => void) => () => { action(); setOpen(false) }
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button type="button" aria-label="换个地方"
                className="rounded-[28%] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
          <GlassIcon icon={<Flask weight="fill" className="size-[1.05em]" />} label="AI4Science" />
        </button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[20rem] gap-0 p-0">
        <SheetHeader className="px-5 pt-5 pb-2">
          <SheetTitle className="font-serif text-[1.125rem] font-semibold">AI4Science</SheetTitle>
          <SheetDescription>工作区各有自己的对话，编辑台只有一个。</SheetDescription>
        </SheetHeader>
        <AnimatedList
          items={newestFirst(workspaces)} keyOf={(w) => w.id} fade="popover"
          className="min-h-0 flex-1" listClassName="h-full px-3 py-1"
          render={(w) => {
            const active = place.kind === 'workspace' && place.id === w.id
            return (
              <button type="button" onClick={go(() => onPick(w.id))} aria-current={active ? 'true' : undefined}
                      className={cn(ROW, active && 'bg-accent')}>
                <img src={coverOf(w.id).thumb} alt="" width={56} height={35}
                     className={cn('h-9 w-14 shrink-0 rounded-md object-cover', active && 'ring-2 ring-primary ring-offset-1 ring-offset-popover')} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.9375rem] font-medium">{w.title}</span>
                  <span className="block text-[0.75rem] text-muted-foreground">{stageSentence(w)}</span>
                </span>
              </button>
            )
          }}
        />
        <div className="space-y-0.5 border-t px-3 py-2">
          <button type="button" onClick={go(onNew)} className={cn(ROW, 'text-primary', place.kind === 'door' && 'bg-accent')}>
            <FolderSimplePlus className="size-5" />新建工作区
          </button>
          <button type="button" onClick={go(onStudio)} aria-current={place.kind === 'studio' ? 'true' : undefined}
                  className={cn(ROW, place.kind === 'studio' && 'bg-accent')}>
            <Blueprint className="size-5" weight={place.kind === 'studio' ? 'fill' : 'regular'} />编辑台
          </button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
