// 首页项目墙的格子，从 reactbits 的 MagicBento 捞来改装（MIT，https://reactbits.dev/components/magic-bento）：
// 鼠标在墙上走，离哪格近哪格的边缘亮起一圈、格里跟着一团淡光——就这一个效果，星星粒子、磁吸、倾斜、点击涟漪都不要
// （主人：图不是主角，字是）。原版用 gsap 逐帧写样式，这里只写 CSS 变量，动画全靠 transition；颜色走 tokens（靛）；
// 减少动效或触屏上不亮。格里装什么由调用方给：格子本身只管材料。
import { type MouseEvent, type ReactNode, useCallback, useEffect, useRef } from 'react'

import { useReducedMotion } from 'motion/react'

import { cn } from '@/lib/utils'

/** 离格子边缘多近算「近」、到多远淡完（px） */
const NEAR = 40
const FAR = 120

export function BentoGrid({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const still = useReducedMotion() === true

  const paint = useCallback((clientX: number, clientY: number) => {
    const grid = ref.current
    if (!grid) return
    for (const el of grid.querySelectorAll<HTMLElement>('[data-bento]')) {
      const r = el.getBoundingClientRect()
      const dx = Math.max(r.left - clientX, 0, clientX - r.right)
      const dy = Math.max(r.top - clientY, 0, clientY - r.bottom)
      const d = Math.hypot(dx, dy)
      const glow = d <= NEAR ? 1 : d >= FAR ? 0 : (FAR - d) / (FAR - NEAR)
      el.style.setProperty('--glow', glow.toFixed(3))
      el.style.setProperty('--glow-x', `${(((clientX - r.left) / r.width) * 100).toFixed(1)}%`)
      el.style.setProperty('--glow-y', `${(((clientY - r.top) / r.height) * 100).toFixed(1)}%`)
    }
  }, [])
  const clear = useCallback(() => {
    for (const el of ref.current?.querySelectorAll<HTMLElement>('[data-bento]') ?? []) el.style.setProperty('--glow', '0')
  }, [])
  useEffect(() => () => clear(), [clear])

  const onMove = (e: MouseEvent<HTMLDivElement>) => { if (!still) paint(e.clientX, e.clientY) }
  return (
    <div ref={ref} onMouseMove={onMove} onMouseLeave={clear} className={cn('grid gap-4', className)}>
      {children}
    </div>
  )
}

/** 一格：底是卡片色，边缘那一圈光与格里的那团光都随 --glow 亮；`backdrop` 是压在最底下的画（封面压暗当底） */
export function BentoCard({ children, backdrop, className, onClick, label }: {
  children: ReactNode; backdrop?: ReactNode; className?: string; onClick?: () => void; label?: string
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag type={onClick ? 'button' : undefined} onClick={onClick} aria-label={label} data-bento=""
         className={cn('bento group relative isolate overflow-hidden rounded-2xl border bg-card text-left ring-1 ring-foreground/[0.04] transition-[box-shadow,transform] duration-200',
                       onClick && 'hover:shadow-[0_18px_44px_-22px_rgb(0_0_0/0.28)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                       className)}
         style={{ '--glow': 0, '--glow-x': '50%', '--glow-y': '50%' } as React.CSSProperties}>
      {backdrop && <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">{backdrop}</div>}
      {/* 格里那团淡光 */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 opacity-[calc(var(--glow)*1)] transition-opacity duration-200"
           style={{ background: 'radial-gradient(16rem circle at var(--glow-x) var(--glow-y), color-mix(in oklab, var(--primary) 14%, transparent), transparent 70%)' }} />
      {/* 边缘那一圈光：两层遮罩相减只留边 */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-2xl opacity-[calc(var(--glow)*1)] transition-opacity duration-200"
           style={{
             padding: 2,
             background: 'radial-gradient(14rem circle at var(--glow-x) var(--glow-y), color-mix(in oklab, var(--primary) 70%, transparent), color-mix(in oklab, var(--primary) 25%, transparent) 40%, transparent 70%)',
             WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
             WebkitMaskComposite: 'xor',
             mask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
             maskComposite: 'exclude',
           }} />
      {children}
    </Tag>
  )
}
