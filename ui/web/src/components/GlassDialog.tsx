// 居中的玻璃悬浮窗（外层 #242，主人 2026-10-05：侧滑没有边角、像粘在屏幕边上，视觉上割裂；改成上下左右居中、圆角、
// 苹果那种玻璃）。产出窗与需求全文两处用它。卡片色压到六成、背后糊 28px 提饱和 1.8，一圈亮边 `--glass-rim`、顶上一道
// 高光 `--glass-shine`（深浅两套在 index.css），投影长而软；遮罩只压暗不糊（components/ui/dialog.tsx）。46rem 宽，
// 最高到屏幕留 1.5rem，内容在窗里滚，右上角一枚圆的关闭。标题用 `GlassTitle`（无障碍要求窗里有一个 Dialog 标题）。
import { X } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogTitle } from '@/components/ui/dialog'

export function GlassDialog({ open, onOpenChange, children }: {
  open: boolean; onOpenChange: (open: boolean) => void; children: ReactNode
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} aria-describedby={undefined}
                     className={'flex max-h-[calc(100dvh-3rem)] w-[min(46rem,calc(100vw-2rem))] max-w-none flex-col gap-0 overflow-hidden rounded-[28px] p-0 duration-200 sm:max-w-none '
                                + 'bg-[color-mix(in_oklab,var(--card)_62%,transparent)] ring-1 ring-[var(--glass-rim)] backdrop-blur-[28px] backdrop-saturate-[1.8] '
                                + 'shadow-[inset_0_1px_0_0_var(--glass-shine),0_1px_2px_rgb(0_0_0/0.06),0_28px_72px_-18px_rgb(0_0_0/0.38)]'}>
        <DialogClose asChild>
          <Button variant="ghost" size="icon-sm" className="absolute top-4 right-4 z-10 rounded-full" aria-label="关闭">
            <X />
          </Button>
        </DialogClose>
        <div className="min-h-0 overflow-y-auto">{children}</div>
      </DialogContent>
    </Dialog>
  )
}

/** 窗的标题：宋体大一号，右边让出关闭键的位置 */
export function GlassTitle({ children }: { children: ReactNode }) {
  return <DialogTitle className="pr-10 font-serif text-[1.25rem] leading-snug font-semibold">{children}</DialogTitle>
}
