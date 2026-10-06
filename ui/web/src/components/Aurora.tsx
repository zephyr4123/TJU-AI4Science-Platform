// 首页项目清单与工作区看板共用的一块抬起的面（外层 #249 #255）：玻璃底下垫两团静态极光（靛在左上、青在右下）、
// 边上一圈从靛渐到青的细线；`quiet` 只留玻璃与投影（次一级的面，比如看板上流程外的产出）。全是静态的，不起动画。
// 面里的一行可以跟着鼠标亮一团淡靛光（`Spot` + `follow`）：只在鼠标动时写 CSS 变量，不起帧循环。
import type { MouseEvent, ReactNode } from 'react'

import { GLASS } from '@/components/glass'
import { cn } from '@/lib/utils'

export function Aurora({ children, quiet = false, className }: { children: ReactNode; quiet?: boolean; className?: string }) {
  return (
    <div className={cn('relative isolate overflow-hidden rounded-[22px] shadow-[inset_0_1px_0_0_var(--glass-shine),0_1px_2px_rgb(0_0_0/0.04),0_18px_48px_-24px_rgb(0_0_0/0.22)]', GLASS, className)}>
      {!quiet && (
        <>
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10"
               style={{ background: 'radial-gradient(65% 95% at 0% 0%, color-mix(in oklab, var(--aurora-1) 26%, transparent), transparent 70%), '
                                  + 'radial-gradient(60% 90% at 100% 100%, color-mix(in oklab, var(--aurora-2) 24%, transparent), transparent 70%)' }} />
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-[22px] p-px"
               style={{
                 background: 'linear-gradient(135deg, color-mix(in oklab, var(--aurora-1) 85%, transparent), transparent 42%, transparent 58%, color-mix(in oklab, var(--aurora-2) 80%, transparent))',
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
