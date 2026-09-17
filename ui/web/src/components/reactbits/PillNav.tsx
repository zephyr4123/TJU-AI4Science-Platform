// 顶栏的胶囊切换，从 reactbits 的 PillNav 捞来改装（MIT，https://reactbits.dev/components/pill-nav）：
// 去掉了 logo、react-router 与移动端菜单——这里只是两块看板之间切换，不是站点导航；
// 留下它的滑圆 hover 动效（gsap），颜色改走 tokens。
import { gsap } from 'gsap'
import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

export interface PillNavItem<K extends string = string> {
  id: K
  label: string
}

interface Props<K extends string> {
  items: PillNavItem<K>[]
  active: K
  onSelect: (id: K) => void
  className?: string
  ease?: string
}

export function PillNav<K extends string>({ items, active, onSelect, className, ease = 'power3.easeOut' }: Props<K>) {
  const circleRefs = useRef<Array<HTMLSpanElement | null>>([])
  const tlRefs = useRef<Array<gsap.core.Timeline | null>>([])
  const activeTweenRefs = useRef<Array<gsap.core.Tween | null>>([])

  useEffect(() => {
    const layout = () => {
      circleRefs.current.forEach((circle) => {
        if (!circle?.parentElement) return
        const pill = circle.parentElement as HTMLElement
        const { width: w, height: h } = pill.getBoundingClientRect()
        // 从胶囊底边中点鼓起一个圆，圆心算到刚好盖住整颗胶囊
        const R = (w * w / 4 + h * h) / (2 * h)
        const D = Math.ceil(2 * R) + 2
        const delta = Math.ceil(R - Math.sqrt(Math.max(0, R * R - w * w / 4))) + 1
        circle.style.width = `${D}px`
        circle.style.height = `${D}px`
        circle.style.bottom = `-${delta}px`
        gsap.set(circle, { xPercent: -50, scale: 0, transformOrigin: `50% ${D - delta}px` })
        const label = pill.querySelector<HTMLElement>('.pill-label')
        const hover = pill.querySelector<HTMLElement>('.pill-label-hover')
        if (label) gsap.set(label, { y: 0 })
        if (hover) gsap.set(hover, { y: h + 12, opacity: 0 })
        const i = circleRefs.current.indexOf(circle)
        if (i === -1) return
        tlRefs.current[i]?.kill()
        const tl = gsap.timeline({ paused: true })
        tl.to(circle, { scale: 1.2, xPercent: -50, duration: 2, ease, overwrite: 'auto' }, 0)
        if (label) tl.to(label, { y: -(h + 8), duration: 2, ease, overwrite: 'auto' }, 0)
        if (hover) {
          gsap.set(hover, { y: Math.ceil(h + 100), opacity: 0 })
          tl.to(hover, { y: 0, opacity: 1, duration: 2, ease, overwrite: 'auto' }, 0)
        }
        tlRefs.current[i] = tl
      })
    }
    layout()
    window.addEventListener('resize', layout)
    document.fonts?.ready.then(layout).catch(() => {})
    return () => window.removeEventListener('resize', layout)
  }, [items, ease])

  const enter = (i: number) => {
    const tl = tlRefs.current[i]
    if (!tl) return
    activeTweenRefs.current[i]?.kill()
    activeTweenRefs.current[i] = tl.tweenTo(tl.duration(), { duration: 0.3, ease, overwrite: 'auto' })
  }
  const leave = (i: number) => {
    const tl = tlRefs.current[i]
    if (!tl) return
    activeTweenRefs.current[i]?.kill()
    activeTweenRefs.current[i] = tl.tweenTo(0, { duration: 0.2, ease, overwrite: 'auto' })
  }

  return (
    <div role="tablist" className={cn('flex h-9 items-center gap-0.5 rounded-full border bg-background p-[3px]', className)}>
      {items.map((item, i) => {
        const on = item.id === active
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onSelect(item.id)}
            onMouseEnter={() => enter(i)}
            onMouseLeave={() => leave(i)}
            className={cn(
              'relative inline-flex h-full items-center justify-center overflow-hidden rounded-full px-4 text-[0.875rem] font-medium',
              on ? 'bg-foreground text-background' : 'text-muted-foreground',
            )}
          >
            <span
              aria-hidden
              ref={(el) => { circleRefs.current[i] = el }}
              className="pointer-events-none absolute bottom-0 left-1/2 z-[1] block rounded-full bg-foreground"
              style={{ willChange: 'transform' }}
            />
            <span className="relative z-[2] inline-block leading-none">
              <span className="pill-label relative z-[2] inline-block leading-none" style={{ willChange: 'transform' }}>
                {item.label}
              </span>
              <span
                aria-hidden
                className="pill-label-hover absolute top-0 left-0 z-[3] inline-block leading-none text-background"
                style={{ willChange: 'transform, opacity' }}
              >
                {item.label}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
