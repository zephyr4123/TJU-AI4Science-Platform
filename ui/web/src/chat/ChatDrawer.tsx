// 对话列表收在左侧抽屉里，对话本身才是主角；入口是一枚带字的大圆角按钮「对话 · N」（reactbits GlareHover 改装，外层 #79 #80 #136：
// 原来一个小图标谁都看不见）。项目页与工作区页都是它（对话归项目）；抽屉顶上是项目的封面（编辑台是库的横幅），清单逐条浮现（reactbits AnimatedList 改装）。
import { ChatCenteredText, ChatsCircle, NotePencil, Trash } from '@phosphor-icons/react'
import { useState } from 'react'

import type { ChatMeta } from '@/api/types'
import type { Picture } from '@/assets'
import { Band } from '@/components/Band'
import { Dot } from '@/components/bits'
import { AnimatedList } from '@/components/reactbits/AnimatedList'
import { GlareHover } from '@/components/reactbits/GlareHover'
import HoldButton from '@/components/reactbits/HoldButton'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
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
  /** 删一段（主人 2026-09-22）：按住才算数；正在跑的那段服务会拒，错误一句摆在清单顶上 */
  onRemove: (chatId: string) => Promise<void>
  /** 抽屉顶上那张：项目的封面或库的横幅 */
  cover: Picture
  /** 这一边是谁的对话：项目的标题或「编辑台」 */
  title: string
  /** 这一边的对话是干什么的，一句话 */
}

export function ChatDrawer({ chats, error, selected, healthy, creating, onSelect, onNew, onRemove, cover, title }: Props) {
  const [open, setOpen] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const remove = (chatId: string) => {
    setFailed(null)
    onRemove(chatId).catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  const ordered = chats ? [...chats].sort((a, b) => b.chat_id.localeCompare(a.chat_id)) : null
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <GlareHover aria-label="打开对话列表"
                    className="h-9 rounded-full border bg-background/70 px-3.5 text-[0.875rem] font-medium backdrop-blur-sm transition-colors hover:border-primary/50 focus-visible:outline-2 focus-visible:outline-ring">
          <ChatsCircle weight="fill" className="size-[1.125rem] text-primary" />
          <span>对话</span>
          {ordered && ordered.length > 0 && <span className="tabular text-muted-foreground">{ordered.length}</span>}
        </GlareHover>
      </SheetTrigger>
      <SheetContent side="left" className="w-[20rem] gap-0 p-0" aria-describedby={undefined}>
        <Band picture={cover} veil="foot" className="h-36 shrink-0">
          <div className="flex h-full flex-col justify-end px-5 pb-4">
            <SheetTitle className="font-serif text-[1.125rem] font-semibold">{title}</SheetTitle>
          </div>
        </Band>
        <div className="px-4 py-3">
          <Button variant="outline" size="sm" className="w-full justify-start"
                  disabled={creating} onClick={() => { onNew(); setOpen(false) }}>
            <NotePencil data-icon="inline-start" />新对话
          </Button>
        </div>
        {(error || failed) && <p className="px-5 pb-2 text-xs text-bad">{error ?? failed}</p>}
        {ordered?.length === 0 && (
          <p className="px-5 py-3 text-sm leading-relaxed text-muted-foreground">没有对话</p>
        )}
        <AnimatedList
          items={ordered ?? []} keyOf={(c) => c.chat_id} fade="background"
          className="min-h-0 flex-1" listClassName="h-full space-y-0.5 px-3 pb-3"
          render={(chat) => (
            <div className={cn('group/row flex items-start gap-1 rounded-md pr-1 transition-colors duration-150 hover:bg-sidebar-accent',
                               chat.chat_id === selected && 'bg-sidebar-accent')}>
              <button
                type="button"
                onClick={() => { onSelect(chat.chat_id); setOpen(false) }}
                aria-current={chat.chat_id === selected ? 'true' : undefined}
                className="flex min-w-0 flex-1 items-start gap-2.5 rounded-md px-2.5 py-2 text-left focus-visible:outline-2 focus-visible:outline-ring"
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
              {/* 悬停或键盘落到这一行才出现；按住一秒才删 */}
              <span className="mt-1.5 shrink-0 opacity-0 transition-opacity group-focus-within/row:opacity-100 group-hover/row:opacity-100">
                <HoldButton holdTime={800} doneLabel={<Trash weight="fill" className="size-3.5" />} className="px-2"
                            onHold={() => remove(chat.chat_id)}>
                  <Trash className="size-3.5" aria-label="删除这段对话" />
                </HoldButton>
              </span>
            </div>
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
