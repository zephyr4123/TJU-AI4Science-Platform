// 一条画面横幅：顶栏、对话抽屉、编辑台的库都用它——图铺底、纱幕压字、内容浮在上面。
// 顶栏用 blur：封面糊成一抹颜色，换工作区顶栏就换色；抽屉与库用 foot：图露着，只把脚下压成纸色给字站。
import type { ReactNode } from 'react'

import type { Picture } from '@/assets'
import { Photo } from '@/components/Photo'
import { cn } from '@/lib/utils'

interface Props {
  picture: Picture
  veil: 'wash' | 'foot'
  blur?: boolean
  className?: string
  children?: ReactNode
}

export function Band({ picture, veil, blur = false, className, children }: Props) {
  return (
    <div className={cn('relative overflow-hidden', className)}>
      <Photo picture={picture} className={cn(blur && 'scale-125 blur-2xl')} />
      <div aria-hidden="true" className={cn('pointer-events-none absolute inset-0', veil === 'wash' ? 'veil-wash' : 'veil-foot')} />
      <div className="relative h-full">{children}</div>
    </div>
  )
}
