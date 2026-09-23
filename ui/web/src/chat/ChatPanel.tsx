// 对话那块板，工作区与编辑台同一个组件、两种摆法（主人 2026-09-22：两边一个组件复用，尺寸照工作区的；2026-09-23：编辑台
// 那边既然是浮窗，底下就别再分栏，画布铺到底、板浮在上面——拆开就拆开）：宽屏是右边一块悬在雾景上的板（30rem，四周留 12px、
// 圆角 2xl、长而软的投影、一圈 6% 的 ring，和看板的内容面同一种材料），窄屏是从右边滑出的抽屉；默认开着，人关了剩右下角一枚
// 带字的玻璃键。**beside**（工作区页）：板占一列，正文在它左边，板和看板之间露出的雾景就是分隔（主人：border-l 一刀切出来的
// 全高一列像拼上去的）；**float**（编辑台）：正文铺满整行，板绝对定位浮在右边，正文里要躲开板的东西（画布右上角的键、取景）
// 从 `useChatInset()` 读板现在占的宽度（px，关着或窄屏是 0）。板里装什么（哪段对话、哪个抽屉）由外面给：`chat(close)` 渲染
// ChatView，`children` 是板旁边 / 底下的正文（看板 / 文件 / 画布）。
import { ChatsCircle } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { createContext, type ReactNode, useContext, useState } from 'react'

import SpecularButton from '@/components/reactbits/SpecularButton'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useToken } from '@/lib/tokens'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'

/** 板那一列的宽度（板 30rem + 右边 12px 的留白），rem */
const COLUMN_REM = 31.5

/** 浮着的板现在占掉右边多少 px：关着、beside 或窄屏都是 0 */
const ChatInset = createContext(0)
export function useChatInset(): number { return useContext(ChatInset) }

function remInPx(): number {
  const size = typeof document === 'undefined' ? NaN : parseFloat(getComputedStyle(document.documentElement).fontSize)
  return Number.isFinite(size) && size > 0 ? size : 16
}

const CARD = 'relative my-3 mr-3 h-[calc(100%-1.5rem)] w-[30rem] overflow-hidden rounded-2xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.05),0_18px_44px_-22px_rgb(0_0_0/0.28)] ring-1 ring-foreground/[0.06]'

export function ChatPanel({ chat, children, float = false }: {
  chat: (close: () => void) => ReactNode
  children: ReactNode
  /** 板浮在正文上面（编辑台），不占一列 */
  float?: boolean
}) {
  const wide = useMediaQuery(WIDE)
  const [open, setOpen] = useState(true)
  const close = () => setOpen(false)
  const inset = float && wide && open ? COLUMN_REM * remInPx() : 0
  return (
    <div className="relative flex min-h-0 min-w-0 flex-1">
      {/* 正文是一列纵向的 flex：看板 / 文件用 h-full 撑满，编辑台的画布用 flex-1 撑满；正文再宽也不许把板挤出屏幕
          （看板那张表自己横向滚），所以这一列 overflow-hidden */}
      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <ChatInset.Provider value={inset}>{children}</ChatInset.Provider>
        {!open && <ChatEntry onOpen={() => setOpen(true)} />}
      </main>
      {wide ? (float ? (
        <aside aria-label="对话" aria-hidden={!open}
               className={cn('absolute inset-y-0 right-0 z-10 w-[31.5rem] transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-none',
                             open ? 'opacity-100' : 'pointer-events-none translate-x-3 opacity-0')}>
          <div className={CARD}>{chat(close)}</div>
        </aside>
      ) : (
        <aside className={cn('relative h-full shrink-0 transition-[width] duration-200', open ? 'w-[31.5rem]' : 'w-0 overflow-hidden')}
               aria-label="对话" aria-hidden={!open}>
          <div className={CARD}>{chat(close)}</div>
        </aside>
      )) : (
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
