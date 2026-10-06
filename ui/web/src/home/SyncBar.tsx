// 首页右上角一行同步（外层 #256，主人 2026-10-06 照 cc-switch 用量页要的）：上次同步多久以前、「立即同步」、自动刷新隔多久。
// 管的是整个首页读盘的数：项目清单、待你确认 / 运行中、花费。宽屏摆在右半边顶上、与「项目」那行齐，窄屏落在清单与右半边之间。
// 自动刷新只在页面看得见时刷（切到别的标签页不白读盘），隔多久记在本机。
import { ArrowsClockwise, CaretDown, Check } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useNow } from '@/lib/clock'
import { cn } from '@/lib/utils'

import { EVERY, type Every, everyLabel, everyOption, syncedLabel } from './sync'

export function SyncBar({ busy, syncedAt, onSync, every, onEvery, className }: {
  /** 有一份还在取 */
  busy: boolean
  /** 上次同步：几份数里最旧的那份是几时取到的（都至少这么新）；还有没取到过的是 null */
  syncedAt: number | null
  onSync: () => void
  every: Every
  onEvery: (every: Every) => void
  className?: string
}) {
  useEffect(() => {
    if (every === 0) return
    const timer = setInterval(() => { if (!document.hidden) onSync() }, every * 1000)
    return () => clearInterval(timer)
  }, [every, onSync])
  const now = useNow(true, 15_000)
  const [open, setOpen] = useState(false)
  return (
    <div className={cn('flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[0.8125rem] text-muted-foreground', className)}>
      {/* 前面写它属于哪一块（主人 2026-10-06：照 cc-switch「会话日志 · 刚刚同步」，让人知道是哪个板块的）；
          刷新时不换成「同步中」：每 30 秒闪一下字很吵，转的箭头够了 */}
      <span aria-live="polite" title={syncedAt ? new Date(syncedAt).toLocaleString('zh-CN', { hour12: false }) : undefined}
            className="mr-1 tabular">
        统计面板 · {syncedLabel(syncedAt, now)}
      </span>
      <Button variant="outline" onClick={onSync} disabled={busy}
              className="rounded-full bg-card/70 backdrop-blur-sm disabled:opacity-100">
        <ArrowsClockwise data-icon="inline-start" className={cn(busy && 'motion-safe:animate-spin')} />立即同步
      </Button>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="ghost" className="rounded-full text-muted-foreground hover:text-foreground">
            {everyLabel(every)}<CaretDown data-icon="inline-end" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-40 gap-0 p-1">
          <div role="radiogroup" aria-label="自动刷新">
            {EVERY.map((e) => (
              <button key={e} type="button" role="radio" aria-checked={e === every}
                      onClick={() => { onEvery(e); setOpen(false) }}
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[0.8125rem] outline-none hover:bg-accent focus-visible:bg-accent">
                <Check className={cn('size-3.5 shrink-0 text-primary', e !== every && 'invisible')} aria-hidden="true" />
                {everyOption(e)}
              </button>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}
