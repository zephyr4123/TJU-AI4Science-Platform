// 页眉上的深浅色开关，从 reactbits 的 SquishSwitch 捞来改装（MIT，https://reactbits.dev/components/squish-switch）：
// 滑块拖得越快拉得越长，过中线就翻，甩到头挤扁一下；点一下也翻。改装：颜色走 tokens 不收色值、去掉 label、尺寸缺省做小；
// 减少动效时不拉伸、直接跳到位。
import { animate, motion, useMotionValue, useReducedMotion, useSpring, useTransform, useVelocity } from 'motion/react'
import { type CSSProperties, type KeyboardEvent, type PointerEvent, useEffect, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

interface Props {
  checked: boolean
  onChange: (checked: boolean) => void
  ariaLabel: string
  disabled?: boolean
  width?: number
  height?: number
  className?: string
}

interface Grip {
  id: number
  grab: number | null
  moved: boolean
  startX: number
  onAtPress: boolean
  slop: number
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const FLOW_SPRING = { stiffness: 320, damping: 40, mass: 0.6 }
const SWELL_SPRING = { stiffness: 520, damping: 34, mass: 0.6 }
const MAX_STRETCH = 0.4
const STRETCH_SPEED = 600
const TAP_SLOP = { fine: 4, coarse: 8 }
const STRETCH = 0.36
const HOVER_SCALE = 1.035

export default function SquishSwitch({ checked, onChange, ariaLabel, disabled = false, width = 40, height = 22, className }: Props) {
  const reduce = useReducedMotion() === true
  const inset = Math.max(2, Math.round(height * 0.11))
  const thumb = height - inset * 2
  const min = inset
  const max = width - inset - thumb
  const mid = (min + max) / 2
  const trackRadius = height / 2
  const thumbRadius = Math.max(2, trackRadius - inset)

  const on = checked
  const [dragging, setDragging] = useState(false)
  const trackRef = useRef<HTMLSpanElement>(null)
  const grip = useRef<Grip | null>(null)
  const onRef = useRef(on)
  useEffect(() => {
    onRef.current = on
  }, [on])
  const skipClick = useRef(false)

  const x = useMotionValue(on ? max : min)
  const flow = useSpring(useVelocity(x), FLOW_SPRING)
  const swell = useSpring(1, SWELL_SPRING)
  const gain = reduce ? 0 : STRETCH
  const stretchOf = (v: number) => 1 + Math.min(MAX_STRETCH, Math.abs(v) / STRETCH_SPEED) * gain
  const scaleX = useTransform([flow, swell], ([v, h]: number[]) => stretchOf(v) * h)
  const scaleY = useTransform([flow, swell], ([v, h]: number[]) => h / stretchOf(v))

  const commit = (next: boolean) => {
    if (next === onRef.current) return
    onRef.current = next
    onChange(next)
  }

  useEffect(() => {
    if (dragging) return undefined
    const target = on ? max : min
    if (reduce) {
      x.jump(target)
      return undefined
    }
    const controls = animate(x, target, {
      type: 'spring', stiffness: 170, damping: 21.5, mass: 0.9, restDelta: 0.001, restSpeed: 0.01,
    })
    return () => controls.stop()
  }, [on, dragging, min, max, reduce, x])

  const localX = (clientX: number) => {
    const el = trackRef.current
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    const scale = rect.width / (el.offsetWidth || rect.width) || 1
    return (clientX - rect.left) / scale
  }
  const down = (e: PointerEvent<HTMLButtonElement>) => {
    if (disabled || grip.current || e.button !== 0) return
    grip.current = {
      id: e.pointerId, grab: null, moved: false, startX: e.clientX, onAtPress: onRef.current,
      slop: e.pointerType === 'touch' ? TAP_SLOP.coarse : TAP_SLOP.fine,
    }
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      // 指针已经不在了：不捕获也能点
    }
    setDragging(true)
  }
  const move = (e: PointerEvent<HTMLButtonElement>) => {
    const g = grip.current
    if (!g || g.id !== e.pointerId) return
    const lx = localX(e.clientX)
    if (g.grab === null) {
      g.grab = lx - x.get()
      return
    }
    if (!g.moved && Math.abs(e.clientX - g.startX) > g.slop) g.moved = true
    if (!g.moved) return
    const nx = clamp(lx - g.grab, min, max)
    x.set(nx)
    commit(nx > mid)
  }
  const up = (e: { pointerId: number; currentTarget: HTMLButtonElement }, cancelled: boolean) => {
    const g = grip.current
    if (!g || g.id !== e.pointerId) return
    grip.current = null
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // 没捕获到也没事
    }
    if (cancelled) commit(g.onAtPress)
    else if (!g.moved) commit(!onRef.current)
    skipClick.current = true
    setTimeout(() => {
      skipClick.current = false
    }, 0)
    setDragging(false)
  }
  const click = () => {
    if (skipClick.current) {
      skipClick.current = false
      return
    }
    if (!disabled) commit(!onRef.current)
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-disabled={disabled || undefined}
      aria-label={ariaLabel}
      className={cn(
        "group relative inline-block cursor-pointer touch-pan-y rounded-full border-0 bg-transparent p-0 outline-none select-none [-webkit-tap-highlight-color:transparent] after:absolute after:-inset-2 after:content-[''] data-[held]:cursor-grabbing aria-disabled:cursor-not-allowed aria-disabled:opacity-50",
        className,
      )}
      data-on={on ? '' : undefined}
      data-held={dragging ? '' : undefined}
      style={{
        '--ss-w': `${width}px`,
        '--ss-h': `${height}px`,
        '--ss-inset': `${inset}px`,
        '--ss-thumb': `${thumb}px`,
        '--ss-r': `${trackRadius}px`,
        '--ss-thumb-r': `${thumbRadius}px`,
      } as CSSProperties}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={(e) => up(e, false)}
      onPointerCancel={(e) => up(e, true)}
      onPointerEnter={(e: PointerEvent<HTMLButtonElement>) => {
        if (e.pointerType === 'mouse' && !disabled && !reduce) swell.set(HOVER_SCALE)
      }}
      onPointerLeave={() => swell.set(1)}
      onKeyDown={(e: KeyboardEvent<HTMLButtonElement>) => {
        if (e.key === 'Escape' && grip.current) up({ pointerId: grip.current.id, currentTarget: e.currentTarget }, true)
      }}
      onClick={click}
    >
      <span
        ref={trackRef}
        className="relative block bg-foreground/15 transition-colors duration-300 ease-out [width:var(--ss-w)] [height:var(--ss-h)] [border-radius:var(--ss-r)] group-data-[on]:bg-primary motion-reduce:transition-none"
      >
        <motion.span
          aria-hidden="true"
          className="absolute left-0 bg-background shadow-sm transition-colors duration-300 ease-out [top:var(--ss-inset)] [width:var(--ss-thumb)] [height:var(--ss-thumb)] [border-radius:var(--ss-thumb-r)] motion-reduce:transition-none"
          style={{ x, scaleX, scaleY }}
        />
      </span>
    </button>
  )
}
