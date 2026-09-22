// 地方栏（外层 #79 #80 #136）：只剩三个键——首页、编辑台、设置。项目不在这里列（主人 2026-09-22：侧边栏展示项目很鸡肋），
// 首页就是项目墙，进了项目再往下走。首页 / 编辑台是两个平行的世界（纲领 P-15 P-16），设置是全局的一块（P-25），归人，
// 沉在最底下，旁边一个点，有一项自检没过才亮。每个键都带字（主人：没字用户不知道是啥）。
// 宽屏常驻最左一列；窄屏收进页眉的玻璃标记里，点开是一张清单（PlacesSheet）。
import { Blueprint, Flask, GearSix, House, type Icon } from '@phosphor-icons/react'

import { GlassIcon } from '@/components/reactbits/GlassIcon'
import { cn } from '@/lib/utils'

import { type PlacesProps, worldOf } from './place'

export function Rail({ place, onHome, onStudio, settingsOpen, settingsDot, onSettings }: PlacesProps) {
  const world = settingsOpen ? null : worldOf(place)
  return (
    <nav aria-label="地方" className="flex w-[4.5rem] shrink-0 flex-col items-center border-r bg-sidebar">
      <div className="flex h-14 shrink-0 items-center">
        <GlassIcon icon={<Flask weight="fill" className="size-[1.05em]" />} label="AI4Science" />
      </div>
      <div className="flex flex-col items-center gap-3 pt-1">
        <Key label="首页" icon={House} active={world === 'projects'} onClick={onHome} />
        <Key label="编辑台" icon={Blueprint} active={world === 'studio'} onClick={onStudio} />
      </div>
      <span className="flex-1" />
      <div className="pb-3">
        <Key label="设置" icon={GearSix} active={settingsOpen} onClick={onSettings}
             title={settingsDot ? '设置：有一项没过检查' : undefined} dot={settingsDot} />
      </div>
    </nav>
  )
}

/** 一个键：方块 + 底下两个字；开着的填实 */
function Key({ label, icon, active, onClick, title, dot = false }: {
  label: string; icon: Icon; active: boolean; onClick: () => void; title?: string; dot?: boolean
}) {
  const Glyph = icon
  return (
    <button type="button" onClick={onClick} aria-pressed={active} aria-label={title ?? label}
            className="flex flex-col items-center gap-1.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
      <span className={cn('relative flex size-11 items-center justify-center rounded-xl border transition-colors',
                          active ? 'border-primary bg-primary text-primary-foreground'
                                 : 'border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground')}>
        <Glyph weight={active ? 'fill' : 'regular'} className="size-[50%]" />
        {dot && <span aria-hidden="true" className="absolute -top-0.5 -right-0.5 size-2.5 rounded-full bg-wait ring-2 ring-sidebar" />}
      </span>
      <span className={cn('text-[0.6875rem] leading-none', active ? 'text-foreground' : 'text-muted-foreground')}>{label}</span>
    </button>
  )
}
