// 首页项目清单、首页右栏与工作区看板共用的一块抬起的面（外层 #249 #255 #256）：玻璃底下垫两团静态的光、边上一圈渐变细线。
// 三种调子：cool 靛压左上、青压右下（项目清单、流程）；warm 玫红压右上、杏色压左下（首页右栏的花费，与左边的冷色对着映衬）；
// quiet 只留玻璃与投影（次一级的面，比如看板上单独运行的产出）。全是静态的，不起动画。
// 面里的一行可以跟着鼠标亮一团淡靛光（`Spot` + `follow`）：只在鼠标动时写 CSS 变量，不起帧循环。
import type { MouseEvent, ReactNode } from 'react'

import { GLASS } from '@/components/glass'
import { cn } from '@/lib/utils'

export type AuroraTone = 'cool' | 'warm' | 'quiet'

// 两团光（位置、颜色、浓度）与一圈细线的两端；warm 把位置镜像过来，左右两栏的光不撞在一处
const TONES: Record<Exclude<AuroraTone, 'quiet'>, { glow: string; rim: string }> = {
  cool: {
    glow: 'radial-gradient(65% 95% at 0% 0%, color-mix(in oklab, var(--aurora-1) 26%, transparent), transparent 70%), '
        + 'radial-gradient(60% 90% at 100% 100%, color-mix(in oklab, var(--aurora-2) 24%, transparent), transparent 70%)',
    rim: 'linear-gradient(135deg, color-mix(in oklab, var(--aurora-1) 85%, transparent), transparent 42%, transparent 58%, color-mix(in oklab, var(--aurora-2) 80%, transparent))',
  },
  warm: {
    glow: 'radial-gradient(70% 80% at 100% 0%, color-mix(in oklab, var(--spend) 22%, transparent), transparent 70%), '
        + 'radial-gradient(65% 85% at 0% 100%, color-mix(in oklab, var(--spend-glow) 22%, transparent), transparent 70%)',
    rim: 'linear-gradient(225deg, color-mix(in oklab, var(--spend) 80%, transparent), transparent 42%, transparent 58%, color-mix(in oklab, var(--spend-glow) 75%, transparent))',
  },
}

export function Aurora({ children, tone = 'cool', className }: { children: ReactNode; tone?: AuroraTone; className?: string }) {
  const look = tone === 'quiet' ? null : TONES[tone]
  return (
    <div className={cn('relative isolate overflow-hidden rounded-[22px] shadow-[inset_0_1px_0_0_var(--glass-shine),0_1px_2px_rgb(0_0_0/0.04),0_18px_48px_-24px_rgb(0_0_0/0.22)]', GLASS, className)}>
      {look && (
        <>
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10" style={{ background: look.glow }} />
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-[22px] p-px"
               style={{
                 background: look.rim,
                 WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor',
                 mask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', maskComposite: 'exclude',
               }} />
        </>
      )}
      {children}
    </div>
  )
}

/** 鼠标在元素里的位置写进 CSS 变量，`Spot` 那团光跟着走 */
export function follow(e: MouseEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--spot-x', `${e.clientX - r.left}px`)
  e.currentTarget.style.setProperty('--spot-y', `${e.clientY - r.top}px`)
}

/** 跟着鼠标的一团淡靛光：放在 `relative isolate` 的行里，行带 `group/<group>`，悬停或聚焦时亮 */
export function Spot({ group, size = '26rem' }: { group: 'row' | 'out'; size?: string }) {
  return (
    <span aria-hidden="true"
          className={cn('pointer-events-none absolute inset-0 -z-10 rounded-[inherit] opacity-0 transition-opacity duration-200 ease-out',
                        group === 'row' ? 'group-hover/row:opacity-100 group-focus-within/row:opacity-100' : 'group-hover/out:opacity-100 group-focus-visible/out:opacity-100')}
          style={{ background: `radial-gradient(${size} circle at var(--spot-x, 50%) var(--spot-y, 50%), color-mix(in oklab, var(--primary) 9%, transparent), transparent 72%)` }} />
  )
}
