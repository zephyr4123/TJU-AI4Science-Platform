// 设置板上「移除」一台算力的键，从 reactbits 的 HoldButton 捞来改装（MIT，https://reactbits.dev/components/hold-button）：
// 按住不放，红色从左往右像水一样涨满才算数，中途松手就退回去——删东西不该一点就没。原版三档尺寸都太大，
// 加一档 xs 配这一行；颜色走 tokens（底是站内的片色、涨的是 --bad）；不发光；减少动效时不画水波、只淡入。
import { type CSSProperties, type ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'

interface Props {
  children?: ReactNode
  doneLabel?: ReactNode
  /** 按满要多久（毫秒） */
  holdTime?: number
  disabled?: boolean
  onHold?: () => void
  className?: string
}

type Phase = 'idle' | 'holding' | 'done'
type Input = 'pointer' | 'key' | null
interface Motion { raf: number; p: number; from: number; to: number; start: number }
interface Gesture { pointerId: number | null; start: number; rect: DOMRect | null }

const HIT_PAD = 10
const RELEASE_MS = 200
const WAVE = 4
const LINEAR = (t: number) => t
const EASE_OUT = (t: number) => 1 - Math.pow(1 - t, 3)
const LABEL = '[grid-area:1/1] inline-flex items-center gap-1 whitespace-nowrap [transition:opacity_200ms_ease,filter_200ms_ease]'
const CREST_MASK = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='200' viewBox='0 0 20 200' preserveAspectRatio='none'%3E%3Cpath d='M0 0H10C18 8 18 25.3 10 33.3S2 58.7 10 66.7S18 92 10 100S2 125.3 10 133.3S18 158.7 10 166.7S2 192 10 200H0Z'/%3E%3C/svg%3E\")"
const STYLE = `
.hb-root{--hb-w:0px;--hb-h:0px;--hb-cycles:2;--hb-p:0}
.hb-fill{clip-path:inset(0 calc((1 - var(--hb-p)) * (100% + 0.75 * var(--hb-wave)) - var(--hb-p) * 0.25 * var(--hb-wave)) 0 0)}
.hb-crest{-webkit-mask-image:${CREST_MASK};mask-image:${CREST_MASK};-webkit-mask-repeat:repeat-y;mask-repeat:repeat-y;-webkit-mask-size:var(--hb-wave) calc(var(--hb-h) * 2);mask-size:var(--hb-wave) calc(var(--hb-h) * 2);-webkit-mask-position-x:calc(-1 * var(--hb-wave) + var(--hb-p) * (var(--hb-w) + var(--hb-wave)));mask-position-x:calc(-1 * var(--hb-wave) + var(--hb-p) * (var(--hb-w) + var(--hb-wave)));-webkit-mask-position-y:calc(-1 * var(--hb-p) * var(--hb-cycles) * var(--hb-h));mask-position-y:calc(-1 * var(--hb-p) * var(--hb-cycles) * var(--hb-h))}
@media (prefers-reduced-motion:reduce){
.hb-root{transform:none!important}
.hb-fill{clip-path:inset(0)!important;opacity:0;transition:opacity var(--hb-release) ease!important}
.hb-crest{display:none}
.hb-root[data-phase=holding] .hb-fill,.hb-root[data-phase=done] .hb-fill{opacity:1;transition:opacity var(--hb-hold) linear!important}
.hb-label>span{filter:none!important;transition:opacity 200ms ease!important}
}`

export default function HoldButton({ children = '移除', doneLabel = '已移除', holdTime = 1000, disabled = false, onHold, className = '' }: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [input, setInput] = useState<Input>(null)
  const phaseRef = useRef<Phase>('idle')
  const inputRef = useRef<Input>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const gesture = useRef<Gesture>({ pointerId: null, start: 0, rect: null })
  const timers = useRef({ complete: 0 })
  const hintId = useId()

  const go = (next: Phase, kind: Input = null) => {
    phaseRef.current = next
    inputRef.current = kind
    setPhase(next)
    setInput(kind)
  }
  const motion = useRef<Motion>({ raf: 0, p: 0, from: 0, to: 0, start: 0 })
  const drive = (to: number, duration: number, ease: (t: number) => number) => {
    const m = motion.current
    cancelAnimationFrame(m.raf)
    m.from = m.p
    m.to = to
    m.start = 0  // 第一帧再记起点：render 里不读时钟
    const step = (now: number) => {
      if (!m.start) m.start = now
      const t = duration > 0 ? Math.min(1, (now - m.start) / duration) : 1
      m.p = m.from + (m.to - m.from) * ease(t)
      buttonRef.current?.style.setProperty('--hb-p', m.p.toFixed(4))
      if (t < 1) {
        m.raf = requestAnimationFrame(step)
        return
      }
      m.raf = 0
      if (m.to === 1) complete()
    }
    m.raf = requestAnimationFrame(step)
  }
  const complete = () => {
    if (phaseRef.current !== 'holding') return
    if (performance.now() - gesture.current.start < holdTime - 50) return
    clearTimeout(timers.current.complete)
    go('done', inputRef.current)
    onHold?.()
  }
  const begin = (kind: Input) => {
    if (disabled || phaseRef.current !== 'idle') return false
    const button = buttonRef.current
    if (!button) return false
    gesture.current.start = performance.now()
    gesture.current.rect = button.getBoundingClientRect()
    go('holding', kind)
    drive(1, holdTime, LINEAR)
    timers.current.complete = window.setTimeout(complete, holdTime + 100)
    return true
  }
  const release = () => {
    if (phaseRef.current !== 'holding') return
    clearTimeout(timers.current.complete)
    go('idle')
    drive(0, RELEASE_MS, EASE_OUT)
  }
  const releaseRef = useRef(release)
  useEffect(() => { releaseRef.current = release })

  const handlePointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0 || !e.isPrimary || gesture.current.pointerId !== null) return
    if (!begin('pointer')) return
    gesture.current.pointerId = e.pointerId
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* 某些浏览器不许 */ }
  }
  const endPointer = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.pointerId !== gesture.current.pointerId) return
    gesture.current.pointerId = null
    try { if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId) } catch { /* 同上 */ }
    release()
  }
  const handlePointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.pointerId !== gesture.current.pointerId) return
    const r = gesture.current.rect
    if (!r) return
    const out = e.clientX < r.left - HIT_PAD || e.clientX > r.right + HIT_PAD || e.clientY < r.top - HIT_PAD || e.clientY > r.bottom + HIT_PAD
    if (out) endPointer(e)
  }
  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'Escape') { if (inputRef.current === 'key') release(); return }
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); if (!e.repeat) begin('key') }
  }
  const handleKeyUp = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); if (inputRef.current === 'key') release() }
  }

  useLayoutEffect(() => {
    const button = buttonRef.current
    if (!button) return undefined
    const measure = () => {
      button.style.setProperty('--hb-w', `${button.offsetWidth}px`)
      button.style.setProperty('--hb-h', `${button.offsetHeight}px`)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(button)
    return () => ro.disconnect()
  }, [])
  useEffect(() => {
    if (phase !== 'holding') return undefined
    const cancel = () => releaseRef.current()
    const onVisibility = () => { if (document.hidden) cancel() }
    window.addEventListener('blur', cancel)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('blur', cancel)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [phase])
  useEffect(() => {
    const t = timers.current
    const m = motion.current
    return () => { clearTimeout(t.complete); cancelAnimationFrame(m.raf) }
  }, [])

  const labels = (
    <>
      <span className={`${LABEL} group-data-[phase=done]:opacity-0 group-data-[phase=done]:blur-[2px]`} aria-hidden={phase === 'done'}>{children}</span>
      <span className={`${LABEL} opacity-0 blur-[2px] group-data-[phase=done]:opacity-100 group-data-[phase=done]:blur-none`} aria-hidden={phase !== 'done'}>{doneLabel}</span>
    </>
  )
  const vars = {
    '--hb-hold': `${holdTime}ms`, '--hb-cycles': holdTime / 1100, '--hb-release': `${RELEASE_MS}ms`, '--hb-wave': `${WAVE}px`,
  } as CSSProperties
  return (
    <button ref={buttonRef} type="button" disabled={disabled} data-phase={phase} data-input={input ?? undefined}
            aria-describedby={hintId} style={vars}
            className={`hb-root group relative isolate m-0 inline-grid h-7 cursor-pointer touch-manipulation place-items-center rounded-lg border-0 bg-foreground/[0.06] px-2.5 text-[0.8rem] leading-none font-medium text-muted-foreground outline-none select-none [-webkit-tap-highlight-color:transparent] [transition:transform_160ms_cubic-bezier(0.23,1,0.32,1),background-color_150ms_ease] hover:bg-foreground/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring data-[phase=holding]:data-[input=pointer]:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 ${className}`}
            onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={endPointer}
            onPointerCancel={endPointer} onLostPointerCapture={endPointer}
            onPointerLeave={(e) => { if (e.pointerType !== 'touch') endPointer(e) }}
            onKeyDown={handleKeyDown} onKeyUp={handleKeyUp} onContextMenu={(e) => e.preventDefault()}>
      <style>{STYLE}</style>
      <span className="hb-label relative z-[2] grid place-items-center">{labels}</span>
      <span className="pointer-events-none absolute inset-0 z-[3] [clip-path:inset(0_round_0.5rem)]" aria-hidden="true">
        <span className="hb-fill absolute inset-0 grid place-items-center bg-bad text-white">
          <span className="hb-label grid place-items-center">{labels}</span>
        </span>
        <span className="hb-crest absolute inset-0 grid place-items-center bg-bad text-white">
          <span className="hb-label grid place-items-center">{labels}</span>
        </span>
      </span>
      <span id={hintId} className="sr-only">按住 {Math.round(holdTime / 100) / 10} 秒确认</span>
    </button>
  )
}
