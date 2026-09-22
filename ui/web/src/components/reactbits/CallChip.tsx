// 设置板上的「检查」键，从 reactbits 的 CallChip 捞来改装（MIT，https://reactbits.dev/components/call-chip）：
// 一枚小片，按下去开始检查——底色从左往右慢慢填（预计几秒）、毫秒数跳着走，过了整片洗成铜绿、图标翻成 ✓，
// 没过洗成红、抖一下、图标翻成「再来」。原版是只读的状态片（role=status），这里改成真按钮：闲着、过了、没过都能再按；
// 图标换 Phosphor、颜色走 tokens 不收色值；计时只在跑着时显示（几秒是状态行的事）；减少动效时不填不抖。
import { ArrowCounterClockwise, ArrowsClockwise, Check } from '@phosphor-icons/react'
import { type CSSProperties, useEffect, useLayoutEffect, useRef, useState } from 'react'

export type CallChipStatus = 'idle' | 'running' | 'done' | 'error'

interface Props {
  label: string
  status: CallChipStatus
  /** 预计要跑多久：填到九成用这么久，真跑完再填满 */
  expectedMs?: number
  disabled?: boolean
  onPress: () => void
  className?: string
}

type Glyph = 'tool' | 'check' | 'retry'
const HOLD_AT = 0.9
const SHAKE = [0, -1, 1, -0.66, 0.66, -0.33, 0]
const glyphOf = (s: CallChipStatus): Glyph => (s === 'done' ? 'check' : s === 'error' ? 'retry' : 'tool')
const fmt = (ms: number) => (ms < 10000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`)
const reduceMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

const GLYPH = 'absolute inset-0 grid place-items-center opacity-0 blur-[3px] [transform:translateY(70%)] data-[state=in]:opacity-100 data-[state=in]:blur-none data-[state=in]:[transform:none] data-[state=in]:[transition:opacity_240ms_cubic-bezier(0.23,1,0.32,1),transform_240ms_cubic-bezier(0.23,1,0.32,1),filter_240ms_cubic-bezier(0.23,1,0.32,1)] data-[state=out]:[transform:translateY(-70%)] data-[state=out]:[transition:opacity_160ms_cubic-bezier(0.23,1,0.32,1),transform_160ms_cubic-bezier(0.23,1,0.32,1),filter_160ms_cubic-bezier(0.23,1,0.32,1)] group-data-[status=done]:data-[state=in]:text-ok group-data-[status=error]:data-[state=in]:text-bad motion-reduce:[transform:none]! motion-reduce:[filter:none]! group-not-data-[mounted]:transition-none!'

export default function CallChip({ label, status, expectedMs = 8000, disabled = false, onPress, className = '' }: Props) {
  const rootRef = useRef<HTMLButtonElement>(null)
  const fillRef = useRef<HTMLSpanElement>(null)
  const timerRef = useRef<HTMLSpanElement>(null)
  const mountedRef = useRef(false)
  const fraction = useRef(0)
  const shakeAnim = useRef<Animation | null>(null)
  const statusRef = useRef(status)
  statusRef.current = status
  const [mounted, setMounted] = useState(false)
  const roll = useRef<{ cur: Glyph; prev: Glyph | null }>({ cur: glyphOf(status), prev: null })
  if (glyphOf(status) !== roll.current.cur) roll.current = { cur: glyphOf(status), prev: roll.current.cur }

  const setFraction = (f: number, instant: boolean) => {
    const fill = fillRef.current
    if (!fill) return
    fraction.current = f
    if (instant) fill.style.transition = 'none'
    fill.style.transform = `scaleX(${f})`
    if (instant) {
      void fill.getBoundingClientRect()
      fill.style.transition = ''
    }
  }
  const apply = (s: CallChipStatus, animate: boolean) => {
    if (s === 'running') {
      shakeAnim.current?.cancel()
      setFraction(0, true)
      if (animate) setFraction(HOLD_AT, false)
    } else if (s === 'done') {
      setFraction(1, !animate)
    } else if (s === 'error') {
      const fill = fillRef.current
      const live = fill ? new DOMMatrix(getComputedStyle(fill).transform).a : fraction.current
      setFraction(Math.min(1, Math.max(0, live)), true)
      if (animate && !reduceMotion() && rootRef.current) {
        shakeAnim.current = rootRef.current.animate(
          SHAKE.map((k) => ({ transform: `translateX(${k * 6}px)`, easing: 'cubic-bezier(0.77, 0, 0.175, 1)' })),
          { duration: 450, composite: 'add' })
      }
    } else {
      setFraction(0, true)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    setMounted(true)
    apply(statusRef.current, statusRef.current === 'running')
    return () => {
      mountedRef.current = false
      shakeAnim.current?.cancel()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useLayoutEffect(() => {
    if (mountedRef.current) apply(status, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  // 跑着时毫秒数跳着走；停了就收
  useEffect(() => {
    if (status !== 'running') return undefined
    const startedAt = performance.now()
    const write = () => { if (timerRef.current) timerRef.current.textContent = fmt(performance.now() - startedAt) }
    write()
    if (reduceMotion()) {
      const id = setInterval(write, 100)
      return () => clearInterval(id)
    }
    let raf = 0
    const tick = () => { write(); raf = requestAnimationFrame(tick) }
    tick()
    return () => cancelAnimationFrame(raf)
  }, [status])

  const state = (g: Glyph) => (g === roll.current.cur ? 'in' : g === roll.current.prev ? 'out' : undefined)
  const word = status === 'running' ? '检查中' : status === 'done' ? '已检查' : status === 'error' ? '没过，再检查' : label
  return (
    <button ref={rootRef} type="button" disabled={disabled || status === 'running'} onClick={onPress} aria-label={word}
            aria-busy={status === 'running' || undefined} data-status={status} data-mounted={mounted ? '' : undefined}
            className={`group relative box-border inline-flex h-7 cursor-pointer items-center gap-1.5 overflow-hidden rounded-lg border-0 bg-foreground/[0.06] px-2.5 text-[0.8rem] leading-none font-medium whitespace-nowrap text-foreground/80 outline-none select-none [transition:transform_160ms_cubic-bezier(0.23,1,0.32,1),background-color_150ms_ease] hover:bg-foreground/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring enabled:active:scale-[0.97] disabled:cursor-default disabled:opacity-70 motion-reduce:enabled:active:scale-100 ${className}`}
            style={{ '--cc-expected': `${expectedMs}ms` } as CSSProperties}>
      <span ref={fillRef} aria-hidden="true"
            className="pointer-events-none absolute inset-0 origin-left scale-x-0 bg-primary/10 [clip-path:inset(0_0_0_0)] group-data-[status=running]:[transition:transform_var(--cc-expected)_linear] group-data-[status=done]:bg-ok/15 group-data-[status=done]:[clip-path:inset(100%_0_0_0)] group-data-[status=done]:[transition:transform_200ms_cubic-bezier(0.23,1,0.32,1),background-color_120ms_ease,clip-path_400ms_cubic-bezier(0.23,1,0.32,1)_200ms] group-data-[status=error]:bg-bad/15 group-data-[status=error]:[transition:background-color_200ms_ease] motion-reduce:group-data-[status=done]:[clip-path:inset(0_0_0_0)] motion-reduce:group-data-[status=done]:[transition:background-color_120ms_ease] group-not-data-[mounted]:transition-none!" />
      <span className="relative size-3.5 flex-none overflow-hidden" aria-hidden="true">
        <span className={GLYPH} data-state={state('tool')}><ArrowsClockwise className="size-3.5 group-data-[status=running]:animate-spin motion-reduce:animate-none" /></span>
        <span className={GLYPH} data-state={state('check')}><Check weight="bold" className="size-3.5" /></span>
        <span className={GLYPH} data-state={state('retry')}><ArrowCounterClockwise weight="bold" className="size-3.5" /></span>
      </span>
      <span className="relative">{label}</span>
      {status === 'running' && <span ref={timerRef} className="relative min-w-[5ch] text-right tabular-nums opacity-60" aria-hidden="true">0 ms</span>}
    </button>
  )
}
