// 对话列表收在左侧抽屉里：平时只占一个按钮的位置，对话本身才是主角。
// 抽屉顶上是这个工作区的封面（编辑台是库的横幅），清单逐条浮现（reactbits AnimatedList 改装）。
import { ChatCenteredText, NotePencil, SidebarSimple } from '@phosphor-icons/react'
import { useState } from 'react'

import type { ChatMeta } from '@/api/types'
import type { Picture } from '@/assets'
import { Band } from '@/components/Band'
import { Dot } from '@/components/bits'
import { AnimatedList } from '@/components/reactbits/AnimatedList'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { chatTitle, usd, when } from '@/lib/format'
import { cn } from '@/lib/utils'

interface Props {
  chats: ChatMeta[] | null
  error: string | null
  selected: string | null
  healthy: boolean | null
  creating: boolean
  onSelect: (chatId: string) => void
  onNew: () => void
  /** 抽屉顶上那张：工作区的封面或库的横幅 */
  cover: Picture
  /** 这一边是谁的对话：工作区的标题或「编辑台」 */
  title: string
  /** 这一边的对话是干什么的，一句话 */
  description: string
}

export function ChatDrawer({ chats, error, selected, healthy, creating, onSelect, onNew, cover, title, description }: Props) {
  const [open, setOpen] = useState(false)
  const ordered = chats ? [...chats].sort((a, b) => b.chat_id.localeCompare(a.chat_id)) : null
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="打开对话列表">
          <SidebarSimple />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[20rem] gap-0 p-0">
        <Band picture={cover} veil="foot" className="h-36 shrink-0">
          <div className="flex h-full flex-col justify-end px-5 pb-4">
            <SheetTitle className="font-serif text-[1.125rem] font-semibold">{title}</SheetTitle>
            <SheetDescription className="mt-0.5">{description}</SheetDescription>
          </div>
        </Band>
        <div className="px-4 py-3">
          <Button variant="outline" size="sm" className="w-full justify-start"
                  disabled={creating} onClick={() => { onNew(); setOpen(false) }}>
            <NotePencil data-icon="inline-start" />新对话
          </Button>
        </div>
        {error && <p className="px-5 pb-2 text-xs text-bad">{error}</p>}
        {ordered?.length === 0 && (
          <p className="px-5 py-3 text-sm leading-relaxed text-muted-foreground">没有对话</p>
        )}
        <AnimatedList
          items={ordered ?? []} keyOf={(c) => c.chat_id} fade="background"
          className="min-h-0 flex-1" listClassName="h-full space-y-0.5 px-3 pb-3"
          render={(chat) => (
            <button
              type="button"
              onClick={() => { onSelect(chat.chat_id); setOpen(false) }}
              aria-current={chat.chat_id === selected ? 'true' : undefined}
              className={cn('flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors duration-150',
                            'hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-ring',
                            chat.chat_id === selected && 'bg-sidebar-accent')}
            >
              <ChatCenteredText weight={chat.chat_id === selected ? 'fill' : 'regular'}
                                className={cn('mt-0.5 size-4 shrink-0', chat.chat_id === selected ? 'text-primary' : 'text-muted-foreground')} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{chatTitle(chat)}</span>
                <span className="t-label mt-0.5 flex items-center gap-1.5">
                  <span>{when(chat.created_at)}</span><span>·</span>
                  <span className="tabular">{chat.turns} 轮</span><span>·</span>
                  <span className="tabular">{usd(chat.cost_usd)}</span>
                </span>
              </span>
            </button>
          )}
        />
        <div className="flex items-center gap-2 border-t px-5 py-3 text-xs text-muted-foreground">
          <Dot tone={healthy === null ? 'neutral' : healthy ? 'ok' : 'bad'} />
          {healthy === null ? '连接中' : healthy ? '服务在线' : '服务不可达'}
        </div>
      </SheetContent>
    </Sheet>
  )
}
