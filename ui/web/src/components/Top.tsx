// 页眉只属于当前地方：可选的「‹ 回上一级」、标题（可以是一枚切换片）、走到哪一句、两个镜头的开关、右端再放一个。
// 底下可以铺全站那张底图糊成一抹颜色（`banner`）；窄屏时左端放地方清单的入口（`menu`）。底边是两头渐隐的双层细线
// （index.css 的 edge-b，外层 #253），「‹ 上一级」与标题之间一道淡斜杠，读成路径。
import { CaretLeft } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import { ASSETS } from '@/assets'
import { Band } from '@/components/Band'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

/** 页眉上那对镜头开关：现在哪个、有哪几个 */
export interface Lens { value: string; options: { value: string; label: string }[]; onChange: (value: string) => void }

export function Top({ menu, back, title, note, lens, tail, banner = false }: {
  menu?: ReactNode
  /** 回上一级：写上一级的名字 */
  back?: { label: string; onClick: () => void }
  title: ReactNode
  note?: string | null
  lens?: Lens | null
  tail?: ReactNode
  /** 底下铺那张底图糊成一抹颜色；不铺就是卡片色 */
  banner?: boolean
}) {
  const row = (
    <header className="flex h-14 items-center gap-3 px-4 sm:px-5">
      {menu}
      {back && <Back {...back} />}
      {back && <span aria-hidden="true" className="-mx-1 font-light text-muted-foreground/40 select-none">/</span>}
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
  if (!banner) return <div className="edge-b relative shrink-0 bg-card">{row}</div>
  return <Band picture={ASSETS.backdrop} veil="wash" blur className="edge-b shrink-0">{row}</Band>
}

/** 「‹ 上一级的名字」：页眉里一枚；项目页没有页眉，左上角浮着同一枚回首页（外层 #250） */
export function Back({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
            className="flex h-8 shrink-0 items-center gap-0.5 rounded-md pr-2 pl-1 text-[0.875rem] text-muted-foreground transition-colors hover:bg-background/60 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
      <CaretLeft weight="bold" className="size-3.5" />
      <span className="max-w-[16rem] truncate">{label}</span>
    </button>
  )
}
