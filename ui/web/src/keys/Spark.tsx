// 键按下去的那一下火花；系统要求减少动效时就只剩那颗键。
import { useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'

import ClickSpark from '@/components/ClickSpark'

export function Spark({ color, children }: { color: string; children: ReactNode }) {
  const still = useReducedMotion()
  if (still) return <>{children}</>
  return <ClickSpark sparkColor={color} sparkRadius={20} sparkCount={8} duration={420}>{children}</ClickSpark>
}
