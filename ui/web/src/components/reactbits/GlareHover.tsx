// 一枚会闪一道光的按钮，从 reactbits 的 GlareHover 捞来改装（MIT，https://reactbits.dev/animations/glare-hover）：
// 容器改成真按钮（Sheet 的 trigger 要拿到 ref），光的颜色走 tokens（很淡的一道靛），尺寸与圆角交给 className；减少动效时不闪。
import { useReducedMotion } from 'motion/react'
import { type ButtonHTMLAttributes, forwardRef, type MouseEvent, useRef } from 'react'

import { cn } from '@/lib/utils'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** 光扫过去要多久（ms） */
  duration?: number
}

const START = '-100% -100%'
const END = '100% 100%'

export const GlareHover = forwardRef<HTMLButtonElement, Props>(function GlareHover(
  { duration = 650, className, children, onMouseEnter, onMouseLeave, ...rest }, ref,
) {
  const glare = useRef<HTMLSpanElement>(null)
  const still = useReducedMotion() === true

  const enter = (event: MouseEvent<HTMLButtonElement>) => {
    const el = glare.current
    if (el && !still) {
      // 每次都从头扫：先无过渡地回到起点，量一下强制排版，再带过渡扫到终点
      el.style.transition = 'none'
      el.style.backgroundPosition = START
      el.getBoundingClientRect()
      el.style.transition = `background-position ${duration}ms ease`
      el.style.backgroundPosition = END
    }
    onMouseEnter?.(event)
  }
  const leave = (event: MouseEvent<HTMLButtonElement>) => {
    const el = glare.current
    if (el && !still) {
      el.style.transition = `background-position ${duration}ms ease`
      el.style.backgroundPosition = START
    }
    onMouseLeave?.(event)
  }

  return (
    <button ref={ref} type="button" {...rest} onMouseEnter={enter} onMouseLeave={leave}
            className={cn('relative inline-flex items-center overflow-hidden', className)}>
      <span
        ref={glare} aria-hidden="true" className="pointer-events-none absolute inset-0"
        style={{
          background: 'linear-gradient(-45deg, transparent 60%, color-mix(in oklab, var(--primary) 22%, transparent) 70%, transparent 100%)',
          backgroundSize: '250% 250%', backgroundRepeat: 'no-repeat', backgroundPosition: START,
        }}
      />
      <span className="relative inline-flex items-center gap-2">{children}</span>
    </button>
  )
})
