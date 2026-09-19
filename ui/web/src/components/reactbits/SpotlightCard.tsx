// 画布上阶段节点的卡，从 reactbits 的 SpotlightCard 捞来改装（MIT，https://reactbits.dev/components/spotlight-card）：
// 底色与描边走 tokens，聚光的颜色由调用方给（靛的淡光）。
import { type MouseEventHandler, type ReactNode, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

export function SpotlightCard({ children, className, spotlight }: {
  children: ReactNode; className?: string; spotlight: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [opacity, setOpacity] = useState(0)
  const move: MouseEventHandler<HTMLDivElement> = (e) => {
    if (!ref.current) return
    const rect = ref.current.getBoundingClientRect()
    setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
  }
  return (
    <div ref={ref} onMouseMove={move} onMouseEnter={() => setOpacity(1)} onMouseLeave={() => setOpacity(0)}
         className={cn('relative overflow-hidden rounded-2xl border bg-card', className)}>
      <div aria-hidden className="pointer-events-none absolute inset-0 transition-opacity duration-500 ease-in-out"
           style={{ opacity, background: `radial-gradient(circle at ${pos.x}px ${pos.y}px, ${spotlight}, transparent 70%)` }} />
      <div className="relative">{children}</div>
    </div>
  )
}
