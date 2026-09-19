// 人确认的那一块：琥珀底（等你），标题、一句提示、下面放署名与那颗键。
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function KeyPanel({ title, hint, children, compact = false }: { title: string; hint: ReactNode; children: ReactNode; compact?: boolean }) {
  return (
    <section className={cn('rounded-xl border border-wait/40 bg-wait-soft', compact ? 'p-3' : 'p-4')}>
      <h3 className="t-step text-wait">{title}</h3>
      <div className="mt-1 text-[0.875rem] leading-relaxed text-foreground/85">{hint}</div>
      <div className="mt-3">{children}</div>
    </section>
  )
}
