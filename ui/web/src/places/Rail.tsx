// 地方栏：页面认路的第一件事（外层 #79 #80）。上半是工作区——一个工作区一块封面（按名字稳定地挑，assets.coverOf），点即切换，末尾「新建」；
// 隔一道空，底下一块是编辑台。编辑台是全局一个库，不在任何工作区里，所以不和工作区并排、也不跟着工作区换（纲领 P-15 P-16）。
// 宽屏常驻最左一列（reactbits Dock 改成竖排，靠近放大）；窄屏收进页眉的玻璃标记里，点开是一张清单（PlacesSheet）。
import { Blueprint, Flask, Plus } from '@phosphor-icons/react'

import { coverOf } from '@/assets'
import { Dock, DockItem } from '@/components/reactbits/Dock'
import { GlassIcon } from '@/components/reactbits/GlassIcon'
import { cn } from '@/lib/utils'

import { newestFirst, type PlacesProps } from './place'

export function Rail({ workspaces, place, onPick, onNew, onStudio }: PlacesProps) {
  const inStudio = place.kind === 'studio'
  return (
    <nav aria-label="地方" className="flex w-[4.5rem] shrink-0 flex-col items-center border-r bg-sidebar">
      <div className="flex h-14 shrink-0 items-center">
        <GlassIcon icon={<Flask weight="fill" className="size-[1.05em]" />} label="AI4Science" />
      </div>
      <Dock label="工作区与编辑台" className="min-h-0 flex-1 self-stretch">
        <div className="flex min-h-0 flex-1 flex-col items-center gap-2.5 overflow-y-auto py-2 [scrollbar-width:none]">
          {newestFirst(workspaces).map((w) => {
            const active = place.kind === 'workspace' && place.id === w.id
            return (
              <DockItem key={w.id} label={w.title} active={active} onClick={() => onPick(w.id)}
                        className={cn('bg-muted', active ? 'ring-2 ring-primary ring-offset-2 ring-offset-sidebar' : 'opacity-85 hover:opacity-100',
                                      inStudio && 'opacity-55')}>
                <img src={coverOf(w.id).thumb} alt="" className="size-full object-cover" />
              </DockItem>
            )
          })}
          <DockItem label="新建工作区" active={place.kind === 'door'} onClick={onNew}
                    className={cn('border border-dashed hover:border-primary hover:text-primary',
                                  place.kind === 'door' ? 'border-primary text-primary' : 'border-muted-foreground/50 text-muted-foreground')}>
            <Plus weight="bold" className="size-[42%]" />
          </DockItem>
        </div>
        <div className="flex shrink-0 flex-col items-center pt-3 pb-4">
          <span aria-hidden="true" className="mb-3 h-px w-6 bg-border" />
          <DockItem label="编辑台" active={inStudio} onClick={onStudio}
                    className={cn('border', inStudio ? 'border-primary bg-primary text-primary-foreground' : 'bg-card text-foreground hover:border-primary/50')}>
            <Blueprint weight={inStudio ? 'fill' : 'regular'} className="size-[50%]" />
          </DockItem>
        </div>
      </Dock>
    </nav>
  )
}
