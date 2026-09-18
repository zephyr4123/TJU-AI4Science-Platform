// 输入框上的下拉片（模型、思考深度），从 reactbits 的 GlideSelect 捞来改装（MIT，https://reactbits.dev/components/glide-select）：
// 菜单从片的一角弹出，一枚高亮在行与行之间滑动、记得上次停在哪；按住拖着选、松手即选，键盘上下 / Home / End / 首字母都认。
// 改装：颜色走 tokens 不收色值，图标换 Phosphor，片上可以带一个前缀字（「模型」「思考」，菜单行里不带），
// 选项必给（没有「One Two Three」的样板），关键帧 gs-swap 挪进 index.css。减少动效时不缩放、不滑，只淡入淡出。
// 菜单挂在 body 上、按片的位置定住（原版长在片里，输入框的玻璃壳 overflow-hidden 会把六行的菜单切掉一半）；滚动、改窗口就收起。
import { CaretDown, Check } from '@phosphor-icons/react'
import {
  type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode,
  useEffect, useId, useLayoutEffect, useRef, useState,
} from 'react'
import { createPortal } from 'react-dom'

import { cn } from '@/lib/utils'

export interface GlideSelectOption {
  value: string
  label: ReactNode
  /** 行右边的一句小字：快 / 强 / 最强 */
  tag?: string
}

interface Props {
  options: GlideSelectOption[]
  value: string
  onChange: (value: string, option: GlideSelectOption) => void
  /** 片上值前面的字，说清这枚旋钮是什么 */
  prefix?: string
  /** value 不在选项里时片上写什么 */
  placeholder?: string
  size?: 'sm' | 'md'
  menuWidth?: number
  placement?: 'top' | 'bottom'
  align?: 'left' | 'right'
  disabled?: boolean
  ariaLabel: string
  className?: string
}

type Phase = 'closed' | 'open' | 'closing'

const SIZES = {
  sm: { chip: 28, row: 28, font: 12 },
  md: { chip: 32, row: 30, font: 13 },
}
const PAD = 4
const GAP = 1
const MENU_GAP = 6
const POP_MS = 180
const GLIDE_MS = 220

const textOf = (it: GlideSelectOption) => (typeof it.label === 'string' ? it.label : it.value)
const typeaheadIndex = (items: GlideSelectOption[], from: number, ch: string) => {
  const c = ch.toLowerCase()
  const n = items.length
  for (let k = 1; k <= n; k++) {
    const i = (from + k) % n
    if (textOf(items[i]).toLowerCase().startsWith(c)) return i
  }
  return from
}

export default function GlideSelect({
  options, value, onChange, prefix, placeholder = '默认', size = 'sm', menuWidth = 176,
  placement = 'top', align = 'left', disabled = false, ariaLabel, className,
}: Props) {
  const items = options
  const selected = items.findIndex((it) => it.value === value)
  const [phase, setPhase] = useState<Phase>('closed')
  const [active, setActive] = useState<number | null>(null)
  const [side, setSide] = useState<'top' | 'bottom'>(placement)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const pillRef = useRef<HTMLSpanElement>(null)
  const instant = useRef(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const scrub = useRef<{ id: number; top: number } | null>(null)
  const id = useId()
  const S = SIZES[size]
  const step = S.row + GAP
  const popOut = Math.round((POP_MS * 2) / 3)

  // 打开：先量一下往哪边弹得下、把菜单定在片的旁边，再从 closed 态过渡到 open 态；高亮先无声地落到当前选中那行
  useLayoutEffect(() => {
    if (phase !== 'open') return
    const el = menuRef.current
    const root = rootRef.current
    if (!el || !root) return
    const r = root.getBoundingClientRect()
    const need = el.offsetHeight + MENU_GAP
    const chosen = placement === 'bottom' && r.bottom + need > window.innerHeight
      ? 'top'
      : placement === 'top' && r.top - need < 0
        ? 'bottom'
        : placement
    setSide(chosen)
    el.style.minWidth = `${r.width}px`
    el.style.top = chosen === 'bottom' ? `${r.bottom + MENU_GAP}px` : ''
    el.style.bottom = chosen === 'top' ? `${window.innerHeight - r.top + MENU_GAP}px` : ''
    el.style.left = align === 'left' ? `${r.left}px` : ''
    el.style.right = align === 'right' ? `${window.innerWidth - r.right}px` : ''
    el.style.transitionDuration = instant.current ? '0ms' : ''
    el.dataset.state = 'closed'
    void el.offsetHeight
    el.dataset.state = 'open'
    const p = pillRef.current
    if (p) {
      p.style.transition = 'none'
      p.style.transform = `translateY(${Math.max(0, selected) * step}px)`
      p.style.opacity = '0'
      void p.offsetHeight
      p.style.transition = ''
    }
  }, [phase, placement, align, selected, step])

  useLayoutEffect(() => {
    const p = pillRef.current
    if (!p || phase !== 'open') return
    if (active === null) {
      p.style.opacity = '0'
      return
    }
    const jump = instant.current || p.style.opacity !== '1'
    p.style.transitionDuration = jump ? '0ms, 150ms' : ''
    p.style.transform = `translateY(${active * step}px)`
    p.style.opacity = '1'
    instant.current = false
  }, [active, phase, step])

  const open = (viaKey: boolean) => {
    if (disabled) return
    clearTimeout(closeTimer.current)
    instant.current = true
    setActive(selected >= 0 ? selected : viaKey ? 0 : null)
    setPhase('open')
  }
  const close = (mode: 'instant' | 'pop') => {
    setActive(null)
    clearTimeout(closeTimer.current)
    const el = menuRef.current
    if (mode === 'instant' || !el) {
      setPhase('closed')
      return
    }
    el.style.transitionDuration = ''
    el.dataset.state = 'closed'
    setPhase('closing')
    closeTimer.current = setTimeout(() => setPhase('closed'), popOut + 20)
  }
  const pick = (i: number, viaKey: boolean) => {
    const it = items[i]
    if (!it) {
      close('instant')
      return
    }
    if (it.value !== value) {
      onChange(it.value, it)
      if (!viaKey && rootRef.current) rootRef.current.dataset.swap = ''
    }
    close('instant')
    triggerRef.current?.focus({ preventScroll: true })
  }

  const onTriggerKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const k = e.key
    const n = items.length
    const cur = active ?? Math.max(0, selected)
    if (phase !== 'open') {
      if (k === 'Enter' || k === ' ' || k === 'ArrowDown' || k === 'ArrowUp') {
        e.preventDefault()
        open(true)
      }
      return
    }
    const go = (i: number) => {
      e.preventDefault()
      instant.current = true
      setActive(Math.min(n - 1, Math.max(0, i)))
    }
    if (k === 'ArrowDown' || k === 'ArrowUp') go(active === null ? cur : cur + (k === 'ArrowDown' ? 1 : -1))
    else if (k === 'Home' || k === 'End') go(k === 'Home' ? 0 : n - 1)
    else if (k === 'Enter' || k === ' ') {
      e.preventDefault()
      pick(cur, true)
    } else if (k === 'Escape' || k === 'Tab') {
      if (k === 'Escape') e.preventDefault()
      close('instant')
    } else if (k.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) go(typeaheadIndex(items, cur, k))
  }

  // 点到外面就收起；页面滚了、窗口变了，定住的位置就不对了，也收起
  useEffect(() => {
    if (phase === 'closed') return undefined
    const inside = (t: EventTarget | null) =>
      (rootRef.current?.contains(t as Node) ?? false) || (menuRef.current?.contains(t as Node) ?? false)
    const onDown = (e: globalThis.PointerEvent) => {
      if (!inside(e.target)) close('pop')
    }
    const onMove = (e: Event) => {
      if (!inside(e.target)) close('instant')
    }
    document.addEventListener('pointerdown', onDown, true)
    window.addEventListener('scroll', onMove, true)
    window.addEventListener('resize', onMove)
    return () => {
      document.removeEventListener('pointerdown', onDown, true)
      window.removeEventListener('scroll', onMove, true)
      window.removeEventListener('resize', onMove)
    }
    // close 每次渲染都是新函数；这里只在开合之间订阅
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase])
  useEffect(() => {
    if (disabled && phase !== 'closed') close('instant')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled])
  useEffect(() => () => clearTimeout(closeTimer.current), [])

  // 按住在菜单上拖：手指滑到哪行哪行亮，松手即选
  const rowAt = (y: number) => {
    const s = scrub.current
    if (!s) return null
    const i = Math.floor((y - s.top - PAD) / step)
    return i >= 0 && i < items.length ? i : null
  }
  const onListDown = (e: PointerEvent<HTMLDivElement>) => {
    if (scrub.current) return
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      // 指针已经不在了（比如刚被抬起）：不捕获也照样能选
    }
    scrub.current = { id: e.pointerId, top: e.currentTarget.getBoundingClientRect().top }
    instant.current = true
    setActive(rowAt(e.clientY))
  }
  const onListMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!scrub.current || scrub.current.id !== e.pointerId) return
    const i = rowAt(e.clientY)
    if (i !== active) setActive(i)
  }
  const onListUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!scrub.current || scrub.current.id !== e.pointerId) return
    const i = e.type === 'pointerup' ? rowAt(e.clientY) : null
    scrub.current = null
    if (i !== null) pick(i, false)
  }
  const onListOver = (e: PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'touch' || scrub.current) return
    const row = (e.target as HTMLElement).closest<HTMLElement>('[data-index]')
    if (!row) return
    const i = Number(row.dataset.index)
    if (i !== active) setActive(i)
  }

  const origin = `${side === 'bottom' ? 'top' : 'bottom'} ${align}`
  return (
    <div
      ref={rootRef}
      className={cn('group relative inline-block data-[disabled]:opacity-50', className)}
      data-disabled={disabled ? '' : undefined}
      style={{ '--gs-chip': `${S.chip}px`, '--gs-font': `${S.font}px` } as CSSProperties}
      onAnimationEnd={(e) => {
        if (e.animationName === 'gs-swap' && rootRef.current) delete rootRef.current.dataset.swap
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={phase === 'open'}
        aria-controls={`${id}-list`}
        aria-activedescendant={active !== null ? `${id}-${active}` : undefined}
        aria-label={ariaLabel}
        disabled={disabled}
        className="group/trigger relative inline-flex cursor-pointer touch-manipulation items-center gap-1 rounded-lg border-0 pr-1.5 pl-2 leading-none font-medium text-foreground outline-none select-none [-webkit-tap-highlight-color:transparent] [height:var(--gs-chip)] [font-size:var(--gs-font)] bg-foreground/[0.06] transition-[background-color,transform] duration-150 ease-out hover:bg-foreground/10 aria-expanded:bg-foreground/10 enabled:active:scale-[0.97] disabled:cursor-default motion-reduce:enabled:active:scale-100 motion-reduce:transition-[background-color]"
        onPointerDown={(e) => {
          if (e.button !== 0 || disabled) return
          e.currentTarget.focus({ preventScroll: true })
          if (phase === 'open') close('pop')
          else open(false)
        }}
        onKeyDown={onTriggerKey}
      >
        {prefix && <span className="text-muted-foreground">{prefix}</span>}
        <span
          key={value}
          className="data-[empty]:text-muted-foreground group-data-[swap]:animate-[gs-swap_160ms_ease] motion-reduce:group-data-[swap]:animate-none"
          data-empty={selected < 0 ? '' : undefined}
        >
          {selected >= 0 ? items[selected].label : placeholder}
        </span>
        <CaretDown weight="bold" aria-hidden="true"
                   className="size-3 text-muted-foreground transition-transform duration-200 ease-out group-aria-expanded/trigger:rotate-180 motion-reduce:transition-none" />
      </button>
      {phase !== 'closed' && createPortal(
        <div
          ref={menuRef}
          className="fixed z-50 scale-95 rounded-xl border border-border/60 bg-popover p-1 text-popover-foreground opacity-0 shadow-lg [width:var(--gs-menu-w)] [transform-origin:var(--gs-origin)] [transition:opacity_var(--gs-pop)_cubic-bezier(0.23,1,0.32,1),transform_var(--gs-pop)_cubic-bezier(0.23,1,0.32,1)] data-[state=open]:scale-100 data-[state=open]:opacity-100 data-[state=closed]:pointer-events-none data-[state=closed]:[transition-duration:var(--gs-pop-out)] motion-reduce:[transform:none]! motion-reduce:[transition:opacity_var(--gs-pop)_ease]"
          style={{
            '--gs-row': `${S.row}px`,
            '--gs-font': `${S.font}px`,
            '--gs-menu-w': `${menuWidth}px`,
            '--gs-pop': `${POP_MS}ms`,
            '--gs-pop-out': `${popOut}ms`,
            '--gs-glide': `${GLIDE_MS}ms`,
            '--gs-origin': origin,
          } as CSSProperties}
          data-state="open"
          data-side={side}
        >
          <div
            id={`${id}-list`}
            role="listbox"
            aria-label={ariaLabel}
            className="group/list relative grid touch-none gap-px"
            data-live={active !== null ? '' : undefined}
            onPointerOver={onListOver}
            onPointerDown={onListDown}
            onPointerMove={onListMove}
            onPointerUp={onListUp}
            onPointerCancel={onListUp}
            onLostPointerCapture={onListUp}
          >
            <span
              ref={pillRef}
              aria-hidden="true"
              className="pointer-events-none absolute top-0 right-0 left-0 rounded-lg bg-accent opacity-0 [height:var(--gs-row)] [transition:transform_var(--gs-glide)_cubic-bezier(0.23,1,0.32,1),opacity_150ms_ease] motion-reduce:[transition:opacity_150ms_ease]"
            />
            {items.map((it, i) => (
              <div
                key={it.value}
                id={`${id}-${i}`}
                role="option"
                aria-selected={i === selected}
                data-index={i}
                className="relative z-[1] flex cursor-pointer items-center gap-2 rounded-lg pr-2 pl-2.5 select-none [-webkit-tap-highlight-color:transparent] [height:var(--gs-row)] [font-size:var(--gs-font)] transition-colors duration-150 aria-selected:bg-accent/60 group-data-[live]/list:aria-selected:bg-transparent"
              >
                <span className="min-w-0 flex-1 truncate font-medium">{it.label}</span>
                {it.tag && <span className="shrink-0 text-[0.6875rem] text-muted-foreground">{it.tag}</span>}
                <Check weight="bold" aria-hidden="true"
                       className={cn('size-3.5 shrink-0 text-primary', i === selected ? 'visible' : 'invisible')} />
              </div>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}
