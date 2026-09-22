// 一枚 20px 的状态符，从 reactbits 的 StatusMark 捞来改装（MIT，https://reactbits.dev/components/status-mark）：
// 原地从虚线空环变成转圈的弧、再画成一个勾或一个叉；项目页上每个工作区那一行的第一个字符就是它。
// 改装：颜色走 tokens（勾是铜绿、叉是红，其余跟文字色），去掉自带的文字与划线（词由那一行自己写），减少动效时不转只呼吸。
import { animate, useMotionValue, useReducedMotion } from 'motion/react'
import { type CSSProperties, useEffect, useLayoutEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

export type StatusMarkStatus = 'pending' | 'running' | 'done' | 'failed'

const UI = { type: 'spring' as const, duration: 0.3, bounce: 0 }
const MORPH = { duration: 0.3, ease: [0.77, 0, 0.175, 1] as [number, number, number, number] }
const CHECK = 'M7.5 12.25 10.5 15.25 16.75 8.75'
const CROSS = 'M8.5 8.5 15.5 15.5M15.5 8.5 8.5 15.5'
const SPOKEN: Record<StatusMarkStatus, string> = { pending: '未开始', running: '运行中', done: '完成', failed: '失败' }
const IDLE_DASH = 0.3
const DASHES = 8
const ARC = 0.68
const SPIN_MS = 1100
const STROKE = 2

export function StatusMark({ status, size = 20, className }: { status: StatusMarkStatus; size?: number; className?: string }) {
  const reduce = useReducedMotion() === true
  const r = 10 - STROKE / 2
  const C = 2 * Math.PI * r
  const P = C / DASHES
  const running = status === 'running'
  const solid = status !== 'pending'
  const targetArc = running ? ARC : 1

  const mode = useMotionValue(solid ? 1 : 0)
  const arc = useMotionValue(targetArc)
  const travel = useMotionValue(0)
  const ring = useRef<SVGCircleElement>(null)
  const gen = useRef(0)

  const writeDash = () => {
    const m = mode.get()
    const a = arc.get()
    const dash = IDLE_DASH * P + (a * C - IDLE_DASH * P) * m
    const gap = (1 - IDLE_DASH) * P + ((1 - a) * C - (1 - IDLE_DASH) * P) * m
    ring.current?.setAttribute('stroke-dasharray', `${Math.max(0, dash)} ${Math.max(0, gap)}`)
  }
  useLayoutEffect(() => {
    writeDash()
    ring.current?.setAttribute('stroke-dashoffset', String(travel.get()))
  })
  useEffect(() => {
    const offs = [
      mode.on('change', writeDash),
      arc.on('change', writeDash),
      travel.on('change', (v: number) => ring.current?.setAttribute('stroke-dashoffset', String(v))),
    ]
    return () => { offs.forEach((off) => off()); mode.stop(); arc.stop(); travel.stop() }
    // 三个 motion value 的身份不变，只在挂上 / 卸下时接线
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const g = ++gen.current
    if (reduce) { mode.jump(solid ? 1 : 0); arc.jump(targetArc); travel.jump(0); return }
    if (mode.get() === 0) arc.jump(targetArc)
    animate(mode, solid ? 1 : 0, MORPH)
    animate(arc, targetArc, UI)
    if (running) {
      const t0 = travel.get()
      animate(travel, [t0, t0 - C], { duration: SPIN_MS / 1000, ease: 'linear', repeat: Infinity })
      return
    }
    const to = Math.floor(travel.get() / P) * P
    animate(travel, to, UI).then(() => { if (gen.current === g) travel.jump(0) })
    // 形状只随状态变
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, reduce])

  const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: STROKE, strokeLinecap: 'round', strokeLinejoin: 'round' } as const
  const drawn = (on: boolean): CSSProperties => ({
    strokeDasharray: '1 2', strokeDashoffset: on ? 0 : 1.05, opacity: on ? 1 : 0,
    transition: on ? 'stroke-dashoffset 240ms cubic-bezier(0.23,1,0.32,1) 120ms, opacity 0ms linear 120ms'
                   : 'stroke-dashoffset 160ms cubic-bezier(0.23,1,0.32,1), opacity 0ms linear 160ms',
  })
  return (
    <svg role="img" aria-label={SPOKEN[status]} viewBox="0 0 24 24" width={size} height={size}
         data-status={status}
         className={cn('shrink-0 overflow-visible transition-colors duration-200',
                       status === 'done' && 'text-ok', status === 'failed' && 'text-bad',
                       running && !reduce ? undefined : running ? 'animate-pulse' : undefined, className)}>
      <circle cx="12" cy="12" r={r} transform="rotate(-90 12 12)"
              style={{ fill: 'currentColor', stroke: 'currentColor', strokeWidth: STROKE,
                       fillOpacity: status === 'done' || status === 'failed' ? 0.08 : 0,
                       strokeOpacity: running ? 0.2 : 0, transition: 'fill-opacity 180ms ease, stroke-opacity 200ms ease' }} />
      <circle ref={ring} cx="12" cy="12" r={r} transform="rotate(-90 12 12)"
              style={{ ...stroke, opacity: solid ? 1 : 0.55, transition: 'opacity 200ms ease' }} />
      <path d={CHECK} pathLength="1" style={{ ...stroke, ...drawn(status === 'done') }} />
      <path d={CROSS} pathLength="1" style={{ ...stroke, ...drawn(status === 'failed') }} />
    </svg>
  )
}
