// 一行像折纸展开的字，从 reactbits 的 FoldText 捞来改装（MIT，https://reactbits.dev/text-animations/fold-text）：
// 原件靠 gsap，这里换成 motion（仓里只留一套动效库）；只留挂载时按字展开一次，折痕阴影去掉（小字看不出）；减少动效时直接出现。
// 给面板的名字用：地方栏的「工作区」、脊柱的「工作流」——一眼知道这块是什么（外层 #82，主人：没字用户不知道是啥）。
import { motion, useReducedMotion } from 'motion/react'

import { cn } from '@/lib/utils'

interface Props {
  text: string
  className?: string
  duration?: number
  stagger?: number
}

export function FoldText({ text, className, duration = 0.5, stagger = 0.05 }: Props) {
  const still = useReducedMotion() === true
  return (
    <span className={cn('inline-block', className)}>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true" className="inline-block [perspective:700px]">
        {Array.from(text).map((ch, i) => (
          <motion.span
            key={`${i}-${ch}`} className="inline-block origin-top [backface-visibility:hidden] [transform-style:preserve-3d]"
            initial={still ? false : { opacity: 0, rotateX: -92 }} animate={{ opacity: 1, rotateX: 0 }}
            transition={{ duration, delay: i * stagger, ease: [0.22, 1, 0.36, 1] }}
          >
            {ch === ' ' ? ' ' : ch}
          </motion.span>
        ))}
      </span>
    </span>
  )
}
