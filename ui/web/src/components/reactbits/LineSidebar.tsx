// 能力详情页左边的目录，从 reactbits 的 LineSidebar 捞来改装（MIT，https://reactbits.dev/components/line-sidebar）：
// 一列条目，鼠标靠近的条目往右挪、变靛。改动：颜色走 tokens（父组件用 useToken 读值传进来）、当前项由外面控制
// （`active`，按滚动位置算）、去掉序号与左边的刻度线（主人：边上的东西砍掉）、减少动效时不挪。别的原样。
import { type CSSProperties, useCallback, useEffect, useRef } from 'react'

type Falloff = 'linear' | 'smooth' | 'sharp'

export interface LineSidebarProps {
  items: string[]
  /** 当前项：由父组件按滚动位置算，点了也是父组件改 */
  active: number | null
  onItemClick: (index: number) => void
  accentColor: string
  textColor: string
  proximityRadius?: number
  maxShift?: number
  falloff?: Falloff
  itemGap?: number
  fontSize?: number
  smoothing?: number
  still?: boolean
  className?: string
}

const FALLOFF_CURVES: Record<Falloff, (p: number) => number> = {
  linear: (p) => p,
  smooth: (p) => p * p * (3 - 2 * p),
  sharp: (p) => p * p * p,
}

export default function LineSidebar({
  items, active, onItemClick, accentColor, textColor,
  proximityRadius = 100, maxShift = 30, falloff = 'smooth', itemGap = 20, fontSize = 1.1, smoothing = 100, still = false,
  className = '',
}: LineSidebarProps) {
  const listRef = useRef<HTMLUListElement>(null)
  const itemRefs = useRef<(HTMLLIElement | null)[]>([])
  const targetsRef = useRef<number[]>([])
  const currentRef = useRef<number[]>([])
  const rafRef = useRef<number | null>(null)
  const lastRef = useRef(0)
  const activeRef = useRef<number | null>(active)
  const smoothingRef = useRef(smoothing)

  useEffect(() => {
    activeRef.current = active
    smoothingRef.current = smoothing
  })

  // Single rAF loop that eases every item's --effect toward its target using
  // frame-rate independent exponential smoothing, so color, shift and scale
  // all move together without staggering CSS transitions.
  const runFrame = useCallback(function frame(now: number) {
    const dt = Math.min((now - lastRef.current) / 1000, 0.05)
    lastRef.current = now
    const tau = Math.max(smoothingRef.current, 1) / 1000
    const k = 1 - Math.exp(-dt / tau)

    let moving = false
    const els = itemRefs.current
    for (let i = 0; i < els.length; i++) {
      const el = els[i]
      if (!el) continue
      const target = Math.max(targetsRef.current[i] || 0, activeRef.current === i ? 1 : 0)
      const cur = currentRef.current[i] || 0
      const next = cur + (target - cur) * k
      const settled = Math.abs(target - next) < 0.0015
      const value = settled ? target : next
      currentRef.current[i] = value
      el.style.setProperty('--effect', value.toFixed(4))
      if (!settled) moving = true
    }

    rafRef.current = moving ? requestAnimationFrame(frame) : null
  }, [])

  const startLoop = useCallback(() => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    lastRef.current = performance.now()
    rafRef.current = requestAnimationFrame(runFrame)
  }, [runFrame])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLUListElement>) => {
    const list = listRef.current
    if (!list || still) return
    const rect = list.getBoundingClientRect()
    const pointerY = e.clientY - rect.top
    const ease = FALLOFF_CURVES[falloff] ?? FALLOFF_CURVES.linear
    const els = itemRefs.current
    for (let i = 0; i < els.length; i++) {
      const el = els[i]
      if (!el) continue
      const center = el.offsetTop + el.offsetHeight / 2
      const distance = Math.abs(pointerY - center)
      targetsRef.current[i] = ease(Math.max(0, 1 - distance / proximityRadius))
    }
    startLoop()
  }, [falloff, proximityRadius, startLoop, still])

  const handlePointerLeave = useCallback(() => {
    targetsRef.current = targetsRef.current.map(() => 0)
    startLoop()
  }, [startLoop])

  useEffect(() => {
    startLoop()
  }, [active, startLoop])

  useEffect(() => () => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
  }, [])

  return (
    <nav
      className={`relative flex justify-start${className ? ` ${className}` : ''}`}
      style={{
        '--accent-color': accentColor,
        '--text-color': textColor,
        '--max-shift': `${still ? 0 : maxShift}px`,
        '--item-gap': `${itemGap}px`,
        '--font-size': `${fontSize}rem`,
      } as CSSProperties}
    >
      <ul ref={listRef} onPointerMove={handlePointerMove} onPointerLeave={handlePointerLeave}
          className="m-0 flex list-none flex-col py-2 [gap:var(--item-gap)]">
        {items.map((label, index) => (
          <li key={`${label}-${index}`} ref={(el) => { itemRefs.current[index] = el }}
              className="relative before:absolute before:-inset-x-12 before:-inset-y-[6px] before:content-['']">
            <button type="button" aria-current={active === index ? 'true' : undefined} onClick={() => onItemClick(index)}
                    className="relative inline-flex cursor-pointer items-baseline leading-[1.2] [color:color-mix(in_srgb,var(--accent-color)_calc(var(--effect,0)*100%),var(--text-color))] [font-size:var(--font-size)] [transform:translateX(calc(var(--effect,0)*var(--max-shift)))] focus-visible:outline-2 focus-visible:outline-ring">
              {label}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}
