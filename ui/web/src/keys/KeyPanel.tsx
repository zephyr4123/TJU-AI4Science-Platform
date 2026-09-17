// 键所在的那一块：琥珀底（等你按键），标题、一句提示、下面放署名与键。
import type { ReactNode } from 'react'

export function KeyPanel({ title, hint, children }: { title: string; hint: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-wait/40 bg-wait-soft p-4">
      <h3 className="t-step text-wait">{title}</h3>
      <div className="mt-1 text-[0.875rem] leading-relaxed text-foreground/85">{hint}</div>
      <div className="mt-3">{children}</div>
    </section>
  )
}
