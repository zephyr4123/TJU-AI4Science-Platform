// 对话那块板，工作区与编辑台同一个（主人 2026-09-22：两边一个组件复用，尺寸照工作区的）：宽屏是右边一块悬在雾景上的板
// （30rem，四周留 12px、圆角 2xl、长而软的投影、一圈 6% 的 ring，和看板的内容面同一种材料，板和看板之间露出的雾景就是分隔；
// 主人：border-l 一刀切出来的全高一列像拼上去的），窄屏是从右边滑出的抽屉；默认开着，人关了剩右下角一枚带字的玻璃键。
// 板里装什么（哪段对话、哪个抽屉）由外面给：`chat(close)` 渲染 ChatView，`children` 是板旁边的正文（看板 / 文件 / 画布）。
import { ChatsCircle } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { type ReactNode, useState } from 'react'

import SpecularButton from '@/components/reactbits/SpecularButton'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useToken } from '@/lib/tokens'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'

export function ChatPanel({ chat, children }: { chat: (close: () => void) => ReactNode; children: ReactNode }) {
  const wide = useMediaQuery(WIDE)
  const [open, setOpen] = useState(true)
  const close = () => setOpen(false)
  return (
    <div className="relative flex min-h-0 flex-1">
      <main className="relative min-w-0 flex-1">
        {children}
        {!open && <ChatEntry onOpen={() => setOpen(true)} />}
      </main>
      {wide ? (
        <aside className={cn('relative h-full shrink-0 transition-[width] duration-200', open ? 'w-[31.5rem]' : 'w-0 overflow-hidden')}
               aria-label="对话" aria-hidden={!open}>
          <div className="relative my-3 mr-3 h-[calc(100%-1.5rem)] w-[30rem] overflow-hidden rounded-2xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.05),0_18px_44px_-22px_rgb(0_0_0/0.28)] ring-1 ring-foreground/[0.06]">
            {chat(close)}
          </div>
        </aside>
      ) : (
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent side="right" className="gap-0 p-0 data-[side=right]:w-[100vw] data-[side=right]:sm:w-[30rem] data-[side=right]:sm:max-w-[30rem]">
            <SheetHeader className="sr-only"><SheetTitle>对话</SheetTitle></SheetHeader>
            <div className="relative h-full">{chat(close)}</div>
          </SheetContent>
        </Sheet>
      )}
    </div>
  )
}

/** 对话收起后右下角的入口：一颗带字的玻璃键（主人：小圆钮太小、看不出是干什么的） */
export function ChatEntry({ onOpen }: { onOpen: () => void }) {
  const still = useReducedMotion() === true
  const indigo = useToken('--primary')
  const card = useToken('--card')
  const ink = useToken('--foreground')
  return (
    <div className="absolute right-5 bottom-5 z-10">
      <SpecularButton size="lg" radius={18} tint={card} tintOpacity={0.78} blur={12} textColor={ink} lineColor={indigo} baseColor={ink}
                      intensity={1.1} speed={still ? 0 : 0.35} followMouse={!still} autoAnimate={false} onClick={onOpen}
                      className="shadow-lg ring-1 ring-foreground/10">
        <span className="inline-flex items-center gap-2"><ChatsCircle weight="fill" className="size-5 text-primary" />打开对话</span>
      </SpecularButton>
    </div>
  )
}
