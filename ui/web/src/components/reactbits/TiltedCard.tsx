// 一张跟着鼠标歪的卡，从 reactbits 的 TiltedCard 捞来改装（MIT，https://reactbits.dev/components/tilted-card）：
// 图是工作区封面，换名字就换张（淡入淡出）；脚下压成纸色给字站（.veil-foot），字浮在图前面一点；
// 去掉 caption 与「手机上看不到效果」那行；减少动效时不歪也不淡。
import { AnimatePresence, motion, useReducedMotion, useSpring } from 'motion/react'
import { type MouseEvent, type ReactNode, useRef } from 'react'

import type { Cover } from '@/assets'
import { cn } from '@/lib/utils'

const SPRING = { damping: 30, stiffness: 100, mass: 2 }

interface Props {
  cover: Cover
  /** 最多歪几度 */
  amplitude?: number
  className?: string
  children?: ReactNode
}

export function TiltedCard({ cover, amplitude = 12, className, children }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const rotateX = useSpring(0, SPRING)
  const rotateY = useSpring(0, SPRING)
  const scale = useSpring(1, SPRING)
  const still = useReducedMotion() === true

  const move = (event: MouseEvent<HTMLDivElement>) => {
    if (still || !ref.current) return
    const rect = ref.current.getBoundingClientRect()
    const dx = event.clientX - rect.left - rect.width / 2
    const dy = event.clientY - rect.top - rect.height / 2
    rotateX.set((dy / (rect.height / 2)) * -amplitude)
    rotateY.set((dx / (rect.width / 2)) * amplitude)
  }
  const reset = () => { rotateX.set(0); rotateY.set(0); scale.set(1) }

  return (
    <div ref={ref} className={cn('[perspective:800px]', className)}
         onMouseMove={move} onMouseEnter={() => { if (!still) scale.set(1.04) }} onMouseLeave={reset}>
      <motion.div style={{ rotateX, rotateY, scale }}
                  className="relative size-full overflow-hidden rounded-2xl bg-muted shadow-[0_24px_48px_-20px_rgba(20,24,40,0.45)] [transform-style:preserve-3d]">
        <AnimatePresence initial={false}>
          <motion.img key={cover.key} src={cover.src} alt="" decoding="async"
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                      transition={{ duration: still ? 0 : 0.35 }}
                      className="absolute inset-0 size-full object-cover" />
        </AnimatePresence>
        <div aria-hidden="true" className="veil-foot absolute inset-0" />
        <div className="absolute inset-x-0 bottom-0 [transform:translateZ(24px)]">{children}</div>
      </motion.div>
    </div>
  )
}
