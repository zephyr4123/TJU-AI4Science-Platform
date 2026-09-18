// 地方栏的一列块，从 reactbits 的 Dock 捞来改装（MIT，https://reactbits.dev/components/dock）：
// 横着的程序坞改成竖的，鼠标沿 y 靠近哪块哪块放大（motion 的 useSpring）；块是真按钮不是 div，名字用 shadcn Tooltip 靠右说；
// 块与块之间可以夹别的东西（隔空、分线），所以放大参数走 context 而不是 items 数组；减少动效时不放大。
import { motion, type MotionValue, type SpringOptions, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react'
import { createContext, type MouseEvent, type ReactNode, useContext, useMemo, useRef } from 'react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface Settings {
  mouseY: MotionValue<number>
  /** 平时的边长、凑近时的边长（px），离多远开始放大 */
  base: number
  magnified: number
  distance: number
  spring: SpringOptions
  still: boolean
}

const DockContext = createContext<Settings | null>(null)

function useDock(): Settings {
  const settings = useContext(DockContext)
  if (!settings) throw new Error('DockItem 必须放在 Dock 里')
  return settings
}

interface DockProps {
  label: string
  base?: number
  magnified?: number
  distance?: number
  spring?: SpringOptions
  className?: string
  children: ReactNode
}

export function Dock({ label, base = 44, magnified = 60, distance = 96, spring = { mass: 0.1, stiffness: 170, damping: 14 },
                       className, children }: DockProps) {
  const mouseY = useMotionValue(Infinity)
  const still = useReducedMotion() === true
  const settings = useMemo<Settings>(() => ({ mouseY, base, magnified, distance, spring, still }),
                                     [mouseY, base, magnified, distance, spring, still])
  return (
    <div role="toolbar" aria-orientation="vertical" aria-label={label}
         onMouseMove={(event: MouseEvent) => mouseY.set(event.clientY)} onMouseLeave={() => mouseY.set(Infinity)}
         className={cn('flex flex-col items-center', className)}>
      <DockContext.Provider value={settings}>{children}</DockContext.Provider>
    </div>
  )
}

interface ItemProps {
  label: string
  active?: boolean
  onClick: () => void
  className?: string
  children: ReactNode
}

export function DockItem({ label, active = false, onClick, className, children }: ItemProps) {
  const dock = useDock()
  const ref = useRef<HTMLButtonElement>(null)
  // 鼠标离这块中心多远：块的位置随邻居放大而动，所以每次都现量
  const offset = useTransform(dock.mouseY, (y) => {
    const rect = ref.current?.getBoundingClientRect()
    return rect ? y - rect.top - rect.height / 2 : Infinity
  })
  const target = useTransform(offset, [-dock.distance, 0, dock.distance], [dock.base, dock.magnified, dock.base])
  const size = useSpring(target, dock.spring)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <motion.button
          ref={ref} type="button" onClick={onClick} aria-label={label} aria-current={active ? 'true' : undefined}
          style={dock.still ? { width: dock.base, height: dock.base } : { width: size, height: size }}
          className={cn('relative flex shrink-0 items-center justify-center overflow-hidden rounded-xl transition-[box-shadow,opacity,border-color] duration-150',
                        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring', className)}
        >
          {children}
        </motion.button>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={10}>{label}</TooltipContent>
    </Tooltip>
  )
}
