// 页眉只属于当前地方：可选的「‹ 回上一级」、标题（可以是一枚切换片）、走到哪一句、两个镜头的开关、右端再放一个。
// 底下可以铺一张封面糊成一抹颜色（换项目就换色）；窄屏时左端放地方清单的入口（`menu`）。
import { CaretLeft } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import type { Picture } from '@/assets'
import { Band } from '@/components/Band'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

/** 页眉上那对镜头开关：现在哪个、有哪几个 */
export interface Lens { value: string; options: { value: string; label: string }[]; onChange: (value: string) => void }

export function Top({ menu, back, title, note, lens, tail, picture }: {
  menu?: ReactNode
  /** 回上一级：写上一级的名字 */
  back?: { label: string; onClick: () => void }
  title: ReactNode
  note?: string | null
  lens?: Lens | null
  tail?: ReactNode
  picture?: Picture | null
}) {
  const row = (
    <header className="flex h-14 items-center gap-3 px-4 sm:px-5">
      {menu}
      {back && (
        <button type="button" onClick={back.onClick}
                className="flex h-8 shrink-0 items-center gap-0.5 rounded-md pr-2 pl-1 text-[0.875rem] text-muted-foreground transition-colors hover:bg-background/60 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
          <CaretLeft weight="bold" className="size-3.5" />
          <span className="max-w-[16rem] truncate">{back.label}</span>
        </button>
      )}
      {typeof title === 'string'
        ? <span className="min-w-0 truncate font-serif text-[1.0625rem] font-semibold tracking-[0.02em]">{title}</span>
        : title}
      {note && <span className="t-label hidden whitespace-nowrap sm:inline">{note}</span>}
      {lens && (
        <Tabs value={lens.value} onValueChange={lens.onChange} className="ml-auto">
          <TabsList aria-label="镜头" className="bg-background/70 backdrop-blur-sm">
            {lens.options.map((o) => <TabsTrigger key={o.value} value={o.value} className="px-3">{o.label}</TabsTrigger>)}
          </TabsList>
        </Tabs>
      )}
      {tail}
    </header>
  )
  if (!picture) return <div className="shrink-0 border-b bg-card">{row}</div>
  return <Band picture={picture} veil="wash" blur className="shrink-0 border-b">{row}</Band>
}
