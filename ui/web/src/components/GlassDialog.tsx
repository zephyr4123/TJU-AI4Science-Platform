// 居中的玻璃悬浮窗（外层 #242，主人 2026-10-05：侧滑没有边角、像粘在屏幕边上，视觉上割裂；改成上下左右居中、圆角、
// 苹果那种玻璃）。产出窗、需求全文与「助理还不能说话」三处用它。材质是 `glass.ts` 的 GLASS，顶上一道高光 `--glass-shine`，投影长而软；
// 遮罩只压暗不糊（components/ui/dialog.tsx）。46rem 宽，最高到屏幕留 1.5rem，内容在窗里滚，右上角一枚圆的关闭。
// 「助理还不能说话」（settings/KeyPrompt，外层 #282）窄一些、没有关闭（「跳过」就是关）。
// 标题用 `GlassTitle`（无障碍要求窗里有一个 Dialog 标题）。
import { X } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import { GLASS } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

export function GlassDialog({ open, onOpenChange, children, showCloseButton = true, className, describedBy, onOpenAutoFocus }: {
  open: boolean; onOpenChange: (open: boolean) => void; children: ReactNode
  /** 右上角那枚关闭；窗里自己有关的键时不要 */
  showCloseButton?: boolean
  /** 换宽度之类，压过缺省的 */
  className?: string
  /** 窗里那句说明的 id：弹出来时读屏跟着标题念它 */
  describedBy?: string
  /** 弹出来时焦点去哪（缺省进第一个能聚焦的）；自己弹出来的窗不该抢走人正在打字的焦点 */
  onOpenAutoFocus?: (event: Event) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} aria-describedby={describedBy} onOpenAutoFocus={onOpenAutoFocus}
                     className={cn('flex max-h-[calc(100dvh-3rem)] w-[min(46rem,calc(100vw-2rem))] max-w-none flex-col gap-0 overflow-hidden rounded-[28px] p-0 duration-200 sm:max-w-none',
                                   GLASS, 'shadow-[inset_0_1px_0_0_var(--glass-shine),0_1px_2px_rgb(0_0_0/0.06),0_28px_72px_-18px_rgb(0_0_0/0.38)]', className)}>
        {showCloseButton && (
          <DialogClose asChild>
            <Button variant="ghost" size="icon-sm" className="absolute top-4 right-4 z-10 rounded-full" aria-label="关闭">
              <X />
            </Button>
          </DialogClose>
        )}
        <div className="min-h-0 overflow-y-auto">{children}</div>
      </DialogContent>
    </Dialog>
  )
}

/** 窗的标题：宋体大一号，右边让出关闭键的位置 */
export function GlassTitle({ children }: { children: ReactNode }) {
  return <DialogTitle className="pr-10 font-serif text-[1.25rem] leading-snug font-semibold">{children}</DialogTitle>
}
