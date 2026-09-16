import { FlaskConical, MessageSquarePlus } from 'lucide-react'

import type { ChatMeta } from '@/api/types'
import { Dot } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { usd, when } from '@/lib/format'
import { cn } from '@/lib/utils'

interface Props {
  chats: ChatMeta[] | null
  error: string | null
  selected: string | null
  healthy: boolean | null
  creating: boolean
  onSelect: (chatId: string) => void
  onNew: () => void
}

/** 列表里的名字：第一句话；还没说话就按开始时间叫它。 */
export function chatTitle(chat: Pick<ChatMeta, 'title' | 'created_at'>): string {
  return chat.title ?? `${when(chat.created_at)} 的对话`
}

export function Sidebar({ chats, error, selected, healthy, creating, onSelect, onNew }: Props) {
  // 新的在上：目录名带 UTC 时间戳，倒序就是时间倒序
  const ordered = chats ? [...chats].sort((a, b) => b.chat_id.localeCompare(a.chat_id)) : null
  return (
    <nav className="flex h-full flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-4 pt-4 pb-3">
        <FlaskConical className="size-4 text-primary" />
        <span className="text-sm font-semibold tracking-tight">AI4Science 工作台</span>
      </div>
      <div className="px-3 pb-2">
        <Button variant="outline" size="sm" className="w-full justify-start" onClick={onNew}
                disabled={creating}>
          <MessageSquarePlus data-icon="inline-start" />
          新对话
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <ul className="space-y-0.5 px-2 pb-2">
          {error && <li className="px-2 py-1 text-xs text-bad">{error}</li>}
          {ordered?.length === 0 && (
            <li className="px-2 py-3 text-xs leading-relaxed text-muted-foreground">
              还没有对话。每段对话对应一个课题：告诉助理你想做什么、数据在哪、想要什么效果。
            </li>
          )}
          {ordered?.map((chat) => (
            <li key={chat.chat_id}>
              <button
                type="button"
                onClick={() => onSelect(chat.chat_id)}
                aria-current={chat.chat_id === selected ? 'true' : undefined}
                className={cn(
                  'w-full rounded-md px-2 py-1.5 text-left transition-colors duration-150',
                  'hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-ring',
                  chat.chat_id === selected && 'bg-sidebar-accent',
                )}
              >
                <div className="truncate text-[13px] font-medium">{chatTitle(chat)}</div>
                <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{when(chat.created_at)}</span>
                  <span>·</span>
                  <span className="tabular">{chat.turns} 轮</span>
                  <span>·</span>
                  <span className="tabular">{usd(chat.cost_usd)}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </ScrollArea>
      <div className="flex items-center gap-2 border-t border-sidebar-border px-4 py-2.5 text-xs text-muted-foreground">
        <Dot tone={healthy === null ? 'neutral' : healthy ? 'ok' : 'bad'} />
        {healthy === null ? '连接中…' : healthy ? '服务在线' : '服务不可达：先 ai4sci serve'}
      </div>
    </nav>
  )
}
