// 地方栏：先选世界，再选世界里的东西（外层 #79 #80）。底下两块是双向开关——工作区 / 编辑台，两个平行的世界（纲领 P-15 P-16；主人：放顶上抢视觉）：
// 工作区有很多个、各有自己的对话与脊柱；编辑台是全局一个库、有自己的对话。开关上面那段只属于当前世界：工作区世界里是一块块封面
// （按名字稳定地挑，assets.coverOf），点即切换，末尾「新建」；编辑台世界里这段收掉——那里没有可切的东西，从结构上就切不了工作区。
// 宽屏常驻最左一列（reactbits Dock 改成竖排，靠近放大）；窄屏收进页眉的玻璃标记里，点开是一张清单（PlacesSheet）。
import { Blueprint, Flask, Folders, Plus } from '@phosphor-icons/react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'

import { coverOf } from '@/assets'
import { Dock, DockItem } from '@/components/reactbits/Dock'
import { GlassIcon } from '@/components/reactbits/GlassIcon'
import { cn } from '@/lib/utils'

import { newestFirst, type PlacesProps, worldOf } from './place'

const SWITCH = 'border transition-colors'
const ON = 'border-primary bg-primary text-primary-foreground'
const OFF = 'border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground'

export function Rail({ workspaces, place, onPick, onNew, onWorld }: PlacesProps) {
  const world = worldOf(place)
  const still = useReducedMotion() === true
  return (
    <nav aria-label="地方" className="flex w-[4.5rem] shrink-0 flex-col items-center border-r bg-sidebar">
      <div className="flex h-14 shrink-0 items-center">
        <GlassIcon icon={<Flask weight="fill" className="size-[1.05em]" />} label="AI4Science" />
      </div>
      <Dock label="工作区与编辑台" className="min-h-0 flex-1 self-stretch">
        <AnimatePresence initial={false}>
          {world === 'workspace' && (
            <motion.div key="workspaces" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        transition={{ duration: still ? 0 : 0.18 }}
                        className="flex min-h-0 flex-1 flex-col items-center gap-2.5 self-stretch overflow-y-auto pt-1 pb-3 [scrollbar-width:none]">
              {newestFirst(workspaces).map((w) => {
                const active = place.kind === 'workspace' && place.id === w.id
                return (
                  <DockItem key={w.id} label={w.title} active={active} onClick={() => onPick(w.id)}
                            className={cn('bg-muted', active ? 'ring-2 ring-primary ring-offset-2 ring-offset-sidebar' : 'opacity-85 hover:opacity-100')}>
                    <img src={coverOf(w.id).thumb} alt="" className="size-full object-cover" />
                  </DockItem>
                )
              })}
              <DockItem label="新建工作区" active={place.kind === 'door'} onClick={onNew}
                        className={cn('border border-dashed hover:border-primary hover:text-primary',
                                      place.kind === 'door' ? 'border-primary text-primary' : 'border-muted-foreground/50 text-muted-foreground')}>
                <Plus weight="bold" className="size-[42%]" />
              </DockItem>
            </motion.div>
          )}
        </AnimatePresence>
        {/* 编辑台世界里上面那段收掉了，开关照样沉在底下 */}
        {world === 'studio' && <span className="flex-1" />}
        <span aria-hidden="true" className="h-px w-6 shrink-0 bg-border" />
        <div className="flex shrink-0 flex-col items-center gap-2 pt-3 pb-4">
          <DockItem label="工作区" active={world === 'workspace'} onClick={() => onWorld('workspace')}
                    className={cn(SWITCH, world === 'workspace' ? ON : OFF)}>
            <Folders weight={world === 'workspace' ? 'fill' : 'regular'} className="size-[50%]" />
          </DockItem>
          <DockItem label="编辑台" active={world === 'studio'} onClick={() => onWorld('studio')}
                    className={cn(SWITCH, world === 'studio' ? ON : OFF)}>
            <Blueprint weight={world === 'studio' ? 'fill' : 'regular'} className="size-[50%]" />
          </DockItem>
        </div>
      </Dock>
    </nav>
  )
}
