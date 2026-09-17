// 两颗人按的键的质感，从 reactbits 的 StarBorder 捞来改装（MIT，https://reactbits.dev/animations/star-border）：
// 改成 button 专用、颜色走 tokens（琥珀 = 等你按键），动画 keyframes 在 index.css。全页只有这两颗键有它。
import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** 星光的颜色（tokens 的值） */
  glow: string
  speed?: string
  children: ReactNode
}

export function StarBorder({ glow, speed = '6s', className, children, disabled, ...rest }: Props) {
  return (
    <button
      type="button"
      disabled={disabled}
      className={cn('relative inline-block overflow-hidden rounded-[14px] py-px', className,
                    disabled && 'opacity-50')}
      {...rest}
    >
      {!disabled && (
        <>
          <span aria-hidden className="animate-star-movement-bottom absolute right-[-250%] bottom-[-11px] h-1/2 w-[300%] rounded-full opacity-70"
                style={{ background: `radial-gradient(circle, ${glow}, transparent 10%)`, animationDuration: speed }} />
          <span aria-hidden className="animate-star-movement-top absolute top-[-10px] left-[-250%] h-1/2 w-[300%] rounded-full opacity-70"
                style={{ background: `radial-gradient(circle, ${glow}, transparent 10%)`, animationDuration: speed }} />
        </>
      )}
      <span className="relative z-[1] block rounded-[13px] border border-wait bg-wait px-5 py-2.5 text-center text-[0.9375rem] font-medium text-white">
        {children}
      </span>
    </button>
  )
}
