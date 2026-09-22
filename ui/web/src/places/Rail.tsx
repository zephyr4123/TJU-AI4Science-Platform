// 地方栏：先选世界，再选世界里的东西（外层 #79 #80）。底下两块是双向开关——主页面 / 编辑台，两个平行的世界（纲领 P-15 P-16；主人：放顶上抢视觉）：
// 主页面里是很多个工作区、各有自己的对话与看板；编辑台是全局一个库、有自己的对话。开关上面那段只属于当前世界：主页面世界里是一块块封面
// （按名字稳定地挑，assets.coverOf），点即切换，末尾「新建」；编辑台世界里这段收掉——那里没有可切的东西，从结构上就切不了工作区。
// 每段都带字（外层 #82，主人：没字用户不知道是啥）：列表顶上「工作区」，块底下「新建」「主页面」「编辑台」「设置」。
// 最底下是「设置」（P-25，外层 #134）：归人、全局一份，所以在这一层不在页眉；旁边一个点，有一项自检没过才亮。
// 宽屏常驻最左一列（reactbits Dock 改成竖排，靠近放大）；窄屏收进页眉的玻璃标记里，点开是一张清单（PlacesSheet）。
import { Blueprint, Flask, Folders, GearSix, Plus } from '@phosphor-icons/react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'

import { coverOf } from '@/assets'
import { Dock, DockItem } from '@/components/reactbits/Dock'
import { FoldText } from '@/components/reactbits/FoldText'
import { GlassIcon } from '@/components/reactbits/GlassIcon'
import { cn } from '@/lib/utils'

import { newestFirst, type PlacesProps, worldOf } from './place'

const SWITCH = 'border transition-colors'
const ON = 'border-primary bg-primary text-primary-foreground'
const OFF = 'border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground'

/** 块底下那两个字 */
function Caption({ active = false, children }: { active?: boolean; children: ReactNode }) {
  return <span className={cn('text-[0.6875rem] leading-none', active ? 'text-foreground' : 'text-muted-foreground')}>{children}</span>
}

export function Rail({ workspaces, place, onPick, onNew, onWorld, settingsOpen, settingsDot, onSettings }: PlacesProps) {
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
              <Caption><FoldText text="工作区" /></Caption>
              {newestFirst(workspaces).map((w) => {
                const active = place.kind === 'workspace' && place.id === w.id
                return (
                  <DockItem key={w.id} label={w.title} active={active} onClick={() => onPick(w.id)}
                            className={cn('bg-muted', active ? 'ring-2 ring-primary ring-offset-2 ring-offset-sidebar' : 'opacity-85 hover:opacity-100')}>
                    <img src={coverOf(w.id).thumb} alt="" className="size-full object-cover" />
                  </DockItem>
                )
              })}
              <div className="flex flex-col items-center gap-1.5">
                <DockItem label="新建工作区" active={place.kind === 'door'} onClick={onNew}
                          className={cn('border border-dashed hover:border-primary hover:text-primary',
                                        place.kind === 'door' ? 'border-primary text-primary' : 'border-muted-foreground/50 text-muted-foreground')}>
                  <Plus weight="bold" className="size-[42%]" />
                </DockItem>
                <Caption active={place.kind === 'door'}>新建</Caption>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {/* 编辑台世界里上面那段收掉了，开关照样沉在底下 */}
        {world === 'studio' && <span className="flex-1" />}
        <span aria-hidden="true" className="h-px w-6 shrink-0 bg-border" />
        <div className="flex shrink-0 flex-col items-center gap-3 pt-3 pb-3">
          <div className="flex flex-col items-center gap-1.5">
            <DockItem label="主页面" active={world === 'workspace'} onClick={() => onWorld('workspace')}
                      className={cn(SWITCH, world === 'workspace' ? ON : OFF)}>
              <Folders weight={world === 'workspace' ? 'fill' : 'regular'} className="size-[50%]" />
            </DockItem>
            <Caption active={world === 'workspace'}>主页面</Caption>
          </div>
          <div className="flex flex-col items-center gap-1.5">
            <DockItem label="编辑台" active={world === 'studio'} onClick={() => onWorld('studio')}
                      className={cn(SWITCH, world === 'studio' ? ON : OFF)}>
              <Blueprint weight={world === 'studio' ? 'fill' : 'regular'} className="size-[50%]" />
            </DockItem>
            <Caption active={world === 'studio'}>编辑台</Caption>
          </div>
          <div className="flex flex-col items-center gap-1.5 pt-1">
            {/* 设置是全局的一块，开着时整个右边都是它：填实，与主页面 / 编辑台开着时一个样 */}
            <DockItem label={settingsDot ? '设置：有一项没过检查' : '设置'} active={settingsOpen} onClick={onSettings}
                      className={cn(SWITCH, 'relative overflow-visible', settingsOpen ? ON : OFF)}>
              <GearSix weight={settingsOpen ? 'fill' : 'regular'} className="size-[50%]" />
              {settingsDot && <span aria-hidden="true" className="absolute -top-0.5 -right-0.5 size-2.5 rounded-full bg-wait ring-2 ring-sidebar" />}
            </DockItem>
            <Caption active={settingsOpen}>设置</Caption>
          </div>
        </div>
      </Dock>
    </nav>
  )
}
