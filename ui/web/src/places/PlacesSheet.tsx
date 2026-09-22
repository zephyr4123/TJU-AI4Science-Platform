// 窄屏的地方栏：页眉左端的玻璃标记就是入口，点开一张从左边拉出来的清单。和宽屏的 Rail 同一个结构——先「工作区 / 编辑台」两个世界，
// 再列当前世界的内容：主页面世界是逐条浮现的工作区（reactbits AnimatedList 改装）与末行「新建」，编辑台世界里没有可切的东西，这段就空着。
import { Blueprint, Flask, FolderSimplePlus, Folders, GearSix } from '@phosphor-icons/react'
import { useState } from 'react'

import { coverOf } from '@/assets'
import { AnimatedList } from '@/components/reactbits/AnimatedList'
import { GlassIcon } from '@/components/reactbits/GlassIcon'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { stageSentence } from '@/lib/humanize'
import { cn } from '@/lib/utils'

import { newestFirst, type PlacesProps, type World, worldOf } from './place'

const ROW = 'flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring'
const TAB = 'flex h-9 items-center justify-center gap-1.5 rounded-full border text-[0.875rem] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-ring'

export function PlacesSheet({ workspaces, place, onPick, onNew, onWorld, settingsOpen, settingsDot, onSettings }: PlacesProps) {
  const [open, setOpen] = useState(false)
  const world = worldOf(place)
  const go = (action: () => void) => () => { action(); setOpen(false) }
  const tab = (w: World) => cn(TAB, world === w ? 'border-primary bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground')
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button type="button" aria-label="换个地方"
                className="rounded-[28%] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
          <GlassIcon icon={<Flask weight="fill" className="size-[1.05em]" />} label="AI4Science" />
        </button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[20rem] gap-0 p-0" aria-describedby={undefined}>
        <SheetHeader className="px-5 pt-5 pb-2">
          <SheetTitle className="font-serif text-[1.125rem] font-semibold">AI4Science</SheetTitle>
        </SheetHeader>
        <div role="tablist" aria-label="世界" className="grid grid-cols-2 gap-2 px-5 pt-2 pb-3">
          <button type="button" role="tab" aria-selected={world === 'workspace'} onClick={go(() => onWorld('workspace'))} className={tab('workspace')}>
            <Folders className="size-[1.125rem]" weight={world === 'workspace' ? 'fill' : 'regular'} />主页面
          </button>
          <button type="button" role="tab" aria-selected={world === 'studio'} onClick={go(() => onWorld('studio'))} className={tab('studio')}>
            <Blueprint className="size-[1.125rem]" weight={world === 'studio' ? 'fill' : 'regular'} />编辑台
          </button>
        </div>
        {world === 'workspace' ? (
          <>
            <p className="px-5 pt-1 text-[0.6875rem] text-muted-foreground">工作区</p>
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
            <div className="border-t px-3 py-2">
              <button type="button" onClick={go(onNew)} className={cn(ROW, 'text-primary', place.kind === 'door' && 'bg-accent')}>
                <FolderSimplePlus className="size-5" />新建工作区
              </button>
            </div>
          </>
        ) : null}
        {world === 'studio' && <span className="flex-1" />}
        <div className="border-t px-3 py-2">
          <button type="button" onClick={go(onSettings)} className={cn(ROW, settingsOpen && 'bg-accent')}>
            <span className="relative">
              <GearSix className="size-5" weight={settingsOpen ? 'fill' : 'regular'} />
              {settingsDot && <span aria-hidden="true" className="absolute -top-0.5 -right-0.5 size-2 rounded-full bg-wait" />}
            </span>
            设置
          </button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
