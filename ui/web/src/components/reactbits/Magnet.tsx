// 磁吸：鼠标靠近时元素被轻轻拉过去，从 reactbits 的 Magnet 捞来改装（MIT，https://reactbits.dev/animations/magnet）：
// 编辑台右下角的对话入口用它。改装点：只在指针靠近时挂 pointermove、系统要求减少动效就不动、触屏不动。
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'motion/react'

import { cn } from '@/lib/utils'

interface Props {
  children: ReactNode
  /** 距离元素边缘多少像素内开始吸 */
  padding?: number
  /** 越大吸得越轻 */
  strength?: number
  className?: string
}

export function Magnet({ children, padding = 60, strength = 3, className }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [near, setNear] = useState(false)
  const still = useReducedMotion() === true

  useEffect(() => {
    if (still || !window.matchMedia('(pointer: fine)').matches) return
    const move = (e: PointerEvent) => {
      const el = ref.current
      if (!el) return
      const { left, top, width, height } = el.getBoundingClientRect()
      const cx = left + width / 2
      const cy = top + height / 2
      if (Math.abs(cx - e.clientX) < width / 2 + padding && Math.abs(cy - e.clientY) < height / 2 + padding) {
        setNear(true)
        setOffset({ x: (e.clientX - cx) / strength, y: (e.clientY - cy) / strength })
      } else if (near) {
        setNear(false)
        setOffset({ x: 0, y: 0 })
      }
    }
    window.addEventListener('pointermove', move, { passive: true })
    return () => window.removeEventListener('pointermove', move)
  }, [padding, strength, still, near])

  return (
    <div ref={ref} className={cn('relative inline-block', className)}>
      <div style={{ transform: `translate3d(${offset.x}px, ${offset.y}px, 0)`, transition: near ? 'transform 0.25s ease-out' : 'transform 0.5s ease-in-out', willChange: 'transform' }}>
        {children}
      </div>
    </div>
  )
}
