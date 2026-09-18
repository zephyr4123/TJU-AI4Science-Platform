import { MessageSquarePlus, PanelLeft } from 'lucide-react'
import { useState } from 'react'

import type { ChatMeta } from '@/api/types'
import { Dot } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
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
  /** 这一边的对话是干什么的，一句话 */
  description: string
}

/** 对话列表收在左侧抽屉里：平时只占一个按钮的位置，对话本身才是主角。 */
export function ChatDrawer({ chats, error, selected, healthy, creating, onSelect, onNew, description }: Props) {
  const [open, setOpen] = useState(false)
  const ordered = chats ? [...chats].sort((a, b) => b.chat_id.localeCompare(a.chat_id)) : null
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="打开对话列表">
          <PanelLeft />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[20rem] gap-0 p-0">
        <SheetHeader className="px-5 pt-5 pb-3">
          <SheetTitle className="text-base">对话</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-3">
          <Button variant="outline" size="sm" className="w-full justify-start"
                  disabled={creating} onClick={() => { onNew(); setOpen(false) }}>
            <MessageSquarePlus data-icon="inline-start" />新对话
          </Button>
        </div>
        <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
          {error && <li className="px-2 py-1 text-xs text-bad">{error}</li>}
          {ordered?.length === 0 && (
            <li className="px-2 py-3 text-sm leading-relaxed text-muted-foreground">还没有对话。</li>
          )}
          {ordered?.map((chat) => (
            <li key={chat.chat_id}>
              <button
                type="button"
                onClick={() => { onSelect(chat.chat_id); setOpen(false) }}
                aria-current={chat.chat_id === selected ? 'true' : undefined}
                className={cn('w-full rounded-md px-2.5 py-2 text-left transition-colors duration-150',
                              'hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-ring',
                              chat.chat_id === selected && 'bg-sidebar-accent')}
              >
                <div className="truncate text-sm font-medium">{chatTitle(chat)}</div>
                <div className="t-label mt-0.5 flex items-center gap-1.5">
                  <span>{when(chat.created_at)}</span><span>·</span>
                  <span className="tabular">{chat.turns} 轮</span><span>·</span>
                  <span className="tabular">{usd(chat.cost_usd)}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2 border-t px-5 py-3 text-xs text-muted-foreground">
          <Dot tone={healthy === null ? 'neutral' : healthy ? 'ok' : 'bad'} />
          {healthy === null ? '连接中…' : healthy ? '服务在线' : '服务不可达，先起 ai4sci serve'}
        </div>
      </SheetContent>
    </Sheet>
  )
}
