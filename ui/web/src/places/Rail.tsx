// 地方栏（外层 #79 #80 #136）：只剩三个键——首页、编辑台、设置。项目不在这里列（主人 2026-09-22：侧边栏展示项目很鸡肋），
// 首页就是项目清单，进了项目再往下走。首页 / 编辑台是两个平行的世界（纲领 P-15 P-16），设置是全局的一块（P-25），归人，
// 沉在最底下，旁边一个点，有一项自检没过才亮。每个键都带字（主人：没字用户不知道是啥）。
// 宽屏常驻最左一列；窄屏收进页眉的玻璃标记里，点开是一张清单（PlacesSheet）。
// 外层 #253（主人 2026-10-06：分割线太普通、看着劣质）：底与页眉同一种磨砂（底图糊开 + 纱幕），两块连成一个 L 形框；
// 右边是两头渐隐的双层细线（index.css 的 edge-r，页眉那一段淡掉，左上角不交成「T」）。键：开着的靛色上亮下深、
// 顶边一道高光、底下一团淡靛光；关着的去掉框，半透明软底，悬停变实，按下轻轻缩一下。
import { Blueprint, GearSix, House, type Icon } from '@phosphor-icons/react'

import { ASSETS } from '@/assets'
import { Band } from '@/components/Band'
import { Logo } from '@/components/Logo'
import { GlassIcon } from '@/components/reactbits/GlassIcon'
import { cn } from '@/lib/utils'

import { type PlacesProps, worldOf } from './place'

export function Rail({ place, onHome, onStudio, settingsOpen, settingsDot, onSettings }: PlacesProps) {
  const world = settingsOpen ? null : worldOf(place)
  return (
    <Band picture={ASSETS.backdrop} veil="wash" blur className="edge-r w-[4.5rem] shrink-0">
      <nav aria-label="地方" className="flex h-full flex-col items-center">
        <div className="flex h-14 shrink-0 items-center">
          <GlassIcon icon={<Logo className="size-[1.15em]" />} label="AI4Science" />
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
    </Band>
  )
}

/** 一个键：圆角方块 + 底下两个字；开着的填实 */
function Key({ label, icon, active, onClick, title, dot = false }: {
  label: string; icon: Icon; active: boolean; onClick: () => void; title?: string; dot?: boolean
}) {
  const Glyph = icon
  return (
    <button type="button" onClick={onClick} aria-pressed={active} aria-label={title ?? label}
            className="group flex flex-col items-center gap-1.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
      <span className={cn('relative flex size-11 items-center justify-center rounded-[14px] transition-[background-color,box-shadow,color,scale] duration-200 ease-out group-active:scale-[0.94]',
                          active
                            ? 'bg-[linear-gradient(180deg,color-mix(in_oklab,var(--primary)_82%,white),var(--primary))] text-primary-foreground '
                              + 'shadow-[inset_0_1px_0_rgb(255_255_255/0.28),0_10px_20px_-10px_color-mix(in_oklab,var(--primary)_75%,transparent)]'
                            : 'bg-card/50 text-muted-foreground shadow-[inset_0_1px_0_var(--key-shine),0_0_0_1px_rgb(0_0_0/0.04)] backdrop-blur-sm '
                              + 'group-hover:bg-card group-hover:text-foreground group-hover:shadow-[inset_0_1px_0_var(--key-shine),0_0_0_1px_rgb(0_0_0/0.05),0_4px_12px_-6px_rgb(0_0_0/0.18)]')}>
        <Glyph weight={active ? 'fill' : 'regular'} className="size-[50%]" />
        {dot && <span aria-hidden="true" className="absolute -top-0.5 -right-0.5 size-2.5 rounded-full bg-wait ring-2 ring-background" />}
      </span>
      <span className={cn('text-[0.6875rem] leading-none transition-colors', active ? 'font-medium text-foreground' : 'text-muted-foreground group-hover:text-foreground')}>{label}</span>
    </button>
  )
}
