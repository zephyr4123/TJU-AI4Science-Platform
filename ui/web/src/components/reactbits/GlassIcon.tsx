// 一枚玻璃图标，从 reactbits 的 GlassIcons 捞来改装（MIT，https://reactbits.dev/components/glass-icons）：
// 只留一枚当顶栏的标记；底色走 tokens（靛到铜绿），hover 的翻起留着，下面那行标签去掉（名字就在旁边）。
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface Props {
  icon: ReactNode
  label: string
  size?: string
  className?: string
}

export function GlassIcon({ icon, label, size = '2rem', className }: Props) {
  return (
    <span role="img" aria-label={label} style={{ width: size, height: size }}
          className={cn('group relative block shrink-0 [perspective:24em] [transform-style:preserve-3d]', className)}>
      <span
        aria-hidden="true"
        className="absolute inset-0 block origin-[100%_100%] rotate-[10deg] rounded-[28%] transition-transform duration-300 ease-[cubic-bezier(0.83,0,0.17,1)] group-hover:[transform:rotate(18deg)_translate3d(-0.25em,-0.25em,0.25em)]"
        style={{ background: 'linear-gradient(135deg, var(--primary), var(--ok))', boxShadow: '0.4em -0.4em 0.6em hsl(223 10% 10% / 0.15)' }}
      />
      <span
        aria-hidden="true"
        className="absolute inset-0 flex origin-[80%_50%] items-center justify-center rounded-[28%] bg-white/15 text-white backdrop-blur-[0.75em] transition-transform duration-300 ease-[cubic-bezier(0.83,0,0.17,1)] group-hover:[transform:translate3d(0,0,1.5em)]"
        style={{ boxShadow: '0 0 0 0.1em hsl(0 0% 100% / 0.3) inset' }}
      >
        {icon}
      </span>
    </span>
  )
}
