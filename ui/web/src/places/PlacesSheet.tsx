// 窄屏的地方栏：页眉左端那枚标就是入口，点开一张从左边拉出来的清单，和宽屏的 Rail 同一份东西——首页、编辑台、设置。
import { Blueprint, GearSix, House, type Icon } from '@phosphor-icons/react'
import { useState } from 'react'

import { BRAND } from '@/brand'
import { Logo } from '@/components/Logo'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Wordmark } from '@/components/Wordmark'
import { cn } from '@/lib/utils'

import { type PlacesProps, worldOf } from './place'

const ROW = 'flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left text-[0.9375rem] font-medium transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring'

export function PlacesSheet({ place, onHome, onStudio, settingsDot, onSettings }: PlacesProps) {
  const [open, setOpen] = useState(false)
  const world = worldOf(place)
  const go = (action: () => void) => () => { action(); setOpen(false) }
  const row = (label: string, icon: Icon, active: boolean, onClick: () => void, dot = false) => {
    const Glyph = icon
    return (
      <button type="button" onClick={go(onClick)} aria-current={active ? 'true' : undefined} className={cn(ROW, active && 'bg-accent')}>
        <span className="relative">
          <Glyph className="size-5" weight={active ? 'fill' : 'regular'} />
          {dot && <span aria-hidden="true" className="absolute -top-0.5 -right-0.5 size-2 rounded-full bg-wait" />}
        </span>
        {label}
      </button>
    )
  }
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button type="button" aria-label="换个地方"
                className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
          <Logo label={BRAND.name} className="size-8" />
        </button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[18rem] gap-0 p-0" aria-describedby={undefined}>
        <SheetHeader className="px-5 pt-5 pb-2">
          <SheetTitle><Wordmark className="text-[1.25rem]" /></SheetTitle>
          <p className="text-[0.75rem] text-muted-foreground">{BRAND.motto}</p>
        </SheetHeader>
        <div className="space-y-0.5 px-3 py-2">
          {row('首页', House, world === 'projects', onHome)}
          {row('编辑台', Blueprint, world === 'studio', onStudio)}
        </div>
        <span className="flex-1" />
        <div className="border-t px-3 py-2">
          {row('设置', GearSix, world === 'settings', onSettings, settingsDot)}
        </div>
      </SheetContent>
    </Sheet>
  )
}
